from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from .client import Xhshow
from .session import SessionManager

__all__ = ["XHSClient", "NoteItem", "CommentItem", "XHSVerifyError"]


class XHSVerifyError(Exception):
    """Raised when XHS returns a verification challenge (HTTP 461)."""

    def __init__(self, status_code: int, verify_type: str, verify_uuid: str) -> None:
        self.status_code = status_code
        self.verify_type = verify_type
        self.verify_uuid = verify_uuid
        super().__init__(
            f"Verification required (HTTP {status_code}, verify_type={verify_type}, "
            f"verify_uuid={verify_uuid}). Please refresh your cookie."
        )


# ---- Data models ----

@dataclass
class NoteItem:
    """A single note from feed/search/user_posted."""

    note_id: str
    title: str = ""
    desc: str = ""
    author: str = ""
    author_id: str = ""
    liked_count: int = 0
    collected_count: int = 0
    comment_count: int = 0
    xsec_token: str = ""
    image_count: int = 0
    posted_at: int = 0  # 发布时间，Unix 毫秒时间戳（由 note_id 前 8 位解析）
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class CommentItem:
    """A single comment (top-level or sub)."""

    comment_id: str
    user: str
    content: str
    like_count: int
    create_time: int = 0
    sub_comments: list[CommentItem] = field(default_factory=list)
    sub_comment_count: int = 0


# ---- Internal per-account state ----

class _Account:
    __slots__ = ("cookies", "session", "_cookie_str", "_http")

    def __init__(self, cookie_str: str) -> None:
        self._cookie_str = cookie_str
        self.cookies = _parse_cookies(cookie_str)
        self.session = SessionManager()
        # 持久化 cookie jar：自动从 Set-Cookie 响应更新
        self._http: httpx.AsyncClient | None = None

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            jar = httpx.Cookies()
            for k, v in self.cookies.items():
                jar.set(k, v, domain="xiaohongshu.com")
            self._http = httpx.AsyncClient(timeout=30, cookies=jar)
        return self._http

    def _sync_cookies(self) -> None:
        """将 cookie jar 的更新同步回 _cookie_str 和 cookies dict。"""
        if self._http is not None and not self._http.is_closed:
            new: dict[str, str] = {}
            for cookie in self._http.cookies.jar:
                if cookie.name:
                    new[cookie.name] = cookie.value
            if new:
                self.cookies.update(new)
                # 重建 _cookie_str
                parts = [f"{k}={v}" for k, v in self.cookies.items()]
                self._cookie_str = "; ".join(parts)


def _parse_cookies(cookie_str: str) -> dict[str, str]:
    return {k: v for item in cookie_str.split("; ") if "=" in item for k, v in [item.split("=", 1)]}


# ---- Main client ----

class XHSClient:
    """小红书 Web API 客户端，支持多账号轮询 + 同步/异步双模式。

    Usage::

        # 单账号
        client = XHSClient(cookie_string)

        # 多账号轮询
        client = XHSClient([cookie_a, cookie_b, cookie_c])

        # 同步
        for note in client.search_notes("美食"):
            print(note.title)

        # 异步 (FastAPI 等)
        async for note in client.search_notes_async("美食"):
            print(note.title)
    """

    BASE_HOST = "https://edith.xiaohongshu.com"
    SEARCH_HOST = "https://so.xiaohongshu.com"  # v2 搜索专用域名
    UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    # 浏览器级别请求头，避免被反爬识别
    BROWSER_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Priority": "u=1, i",
    }
    _REQUEST_INTERVAL = 1.2
    _last_request: float = 0.0  # class-level: shared across all instances
    _rate_lock = asyncio.Lock()  # guards _last_request across async coroutines

    def __init__(self, cookies: str | list[str]) -> None:
        if isinstance(cookies, str):
            cookies = [cookies]
        if not cookies:
            raise ValueError("At least one cookie string is required")
        self._accounts = [_Account(c) for c in cookies]
        self._idx = 0
        self._signer = Xhshow()
        self._lock = asyncio.Lock()  # for async round-robin

    # ---- account rotation ----

    def _next(self) -> _Account:
        """Round-robin to next account (sync)."""
        acct = self._accounts[self._idx]
        self._idx = (self._idx + 1) % len(self._accounts)
        return acct

    async def _next_async(self) -> _Account:
        """Round-robin to next account (async, thread-safe)."""
        async with self._lock:
            acct = self._accounts[self._idx]
            self._idx = (self._idx + 1) % len(self._accounts)
        return acct

    # ---- rate limiting ----

    @classmethod
    def _wait(cls) -> None:
        elapsed = time.time() - cls._last_request
        if elapsed < cls._REQUEST_INTERVAL:
            time.sleep(cls._REQUEST_INTERVAL - elapsed)
        cls._last_request = time.time()

    @classmethod
    async def _wait_async(cls) -> None:
        async with cls._rate_lock:
            elapsed = time.time() - cls._last_request
            if elapsed < cls._REQUEST_INTERVAL:
                await asyncio.sleep(cls._REQUEST_INTERVAL - elapsed)
            cls._last_request = time.time()

    # ---- response checking ----

    @staticmethod
    def _check_response(resp: httpx.Response) -> None:
        """Raise XHSVerifyError if the response indicates a verification challenge."""
        if resp.status_code == 461:
            raise XHSVerifyError(
                status_code=resp.status_code,
                verify_type=resp.headers.get("verifytype", ""),
                verify_uuid=resp.headers.get("verifyuuid", ""),
            )
        resp.raise_for_status()

    @staticmethod
    def _log(method: str, path: str, status: int, elapsed_ms: float) -> None:
        print(f"  {method:4s} {path} → {status} ({elapsed_ms:.0f}ms)", file=sys.stderr, flush=True)

    # ---- HTTP helpers (sync) ----

    def _get(self, path: str, params: dict[str, Any], sign_format: Literal["xys", "xyw"] = "xys") -> dict[str, Any]:
        acct = self._next()
        uri = f"{self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_get(
            uri=uri, cookies=acct.cookies, params=params, sign_format=sign_format, session=acct.session,
        )
        self._wait()
        t0 = time.time()
        with httpx.Client(timeout=30) as http:
            resp = http.get(uri, headers={**headers, "User-Agent": self.UA}, params=params, cookies=acct.cookies)
        self._log("GET", path, resp.status_code, (time.time() - t0) * 1000)
        self._check_response(resp)
        return resp.json()

    def _post(self, path: str, payload: dict[str, Any], x_rap: bool = False, sign_format: Literal["xys", "xyw"] = "xys", *, host: str | None = None) -> dict[str, Any]:
        acct = self._next()
        uri = f"{host or self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_post(
            uri=uri, cookies=acct.cookies, payload=payload, sign_format=sign_format, session=acct.session, x_rap=x_rap,
        )
        headers.update(self.BROWSER_HEADERS)
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["Cookie"] = acct._cookie_str
        self._wait()
        t0 = time.time()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with httpx.Client(timeout=30) as http:
            resp = http.post(uri, headers={**headers, "User-Agent": self.UA}, content=body)
        self._log("POST", path, resp.status_code, (time.time() - t0) * 1000)
        self._check_response(resp)
        return resp.json()

    # ---- HTTP helpers (async) ----

    async def _get_async(self, path: str, params: dict[str, Any], sign_format: Literal["xys", "xyw"] = "xys") -> dict[str, Any]:
        acct = await self._next_async()
        uri = f"{self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_get(
            uri=uri, cookies=acct.cookies, params=params, sign_format=sign_format, session=acct.session,
        )
        await self._wait_async()
        t0 = time.time()
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(uri, headers={**headers, "User-Agent": self.UA}, params=params, cookies=acct.cookies)
        self._log("GET", path, resp.status_code, (time.time() - t0) * 1000)
        self._check_response(resp)
        return resp.json()

    async def _post_async(self, path: str, payload: dict[str, Any], x_rap: bool = False, sign_format: Literal["xys", "xyw"] = "xys", *, host: str | None = None) -> dict[str, Any]:
        acct = await self._next_async()
        uri = f"{host or self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_post(
            uri=uri, cookies=acct.cookies, payload=payload, sign_format=sign_format, session=acct.session, x_rap=x_rap,
        )
        headers.update(self.BROWSER_HEADERS)
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["Cookie"] = acct._cookie_str
        await self._wait_async()
        t0 = time.time()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http = acct._get_http()
        resp = await http.post(uri, headers={**headers, "User-Agent": self.UA}, content=body)
        acct._sync_cookies()
        self._log("POST", path, resp.status_code, (time.time() - t0) * 1000)
        self._check_response(resp)
        return resp.json()

    # ==================================================================
    # Public API — sync
    # ==================================================================

    def homefeed(self, count: int = 20) -> list[NoteItem]:
        data = self._post("/api/sns/web/v1/homefeed", {
            "cursor_score": "", "num": count, "refresh_type": 1,
            "note_index": 0, "unread_begin_note_id": "", "unread_end_note_id": "",
            "unread_note_count": 0, "category": "homefeed_recommend",
        }, x_rap=True)
        return _parse_note_list(data)

    def search_notes(self, keyword: str, page_size: int = 20, sort: str = "general", note_type: int = 0) -> Generator[NoteItem, None, None]:
        """搜索笔记；统一使用浏览器实际使用的 so.xiaohongshu.com v2 接口。"""
        yield from self.search_notes_v2(keyword, page_size, sort, note_type)

    def search_notes_v2(self, keyword: str, page_size: int = 20, sort: str = "general", note_type: int = 0) -> Generator[NoteItem, None, None]:
        """v2 搜索 (so.xiaohongshu.com)，推荐使用，默认启用。"""
        import uuid
        page = 1
        has_more = True
        session_id = str(uuid.uuid4())
        search_id = self._signer.get_search_id()
        while has_more:
            payload = {
                "keyword": keyword, "page": page, "page_size": page_size,
                "search_id": search_id,
                "sort": sort, "note_type": note_type,
                "ext_flags": [],
                "geo": "",
                "image_formats": ["jpg", "webp", "avif"],
                "message_id": "sending",
                "session_id": session_id,
            }
            data = self._post(
                "/api/sns/web/v2/search/notes", payload, x_rap=True, host=self.SEARCH_HOST,
            )
            items = _parse_note_list(data)
            for item in items:
                yield item
            has_more = bool((data.get("data") or {}).get("has_more", False)) and bool(items)
            page += 1

    def get_note_detail(self, note: NoteItem | str, xsec_token: str | None = None) -> dict[str, Any]:
        note_id, token = _resolve_note(note, xsec_token)
        data = self._post("/api/sns/web/v1/feed", {
            "source_note_id": note_id, "xsec_token": token, "xsec_source": "pc_feed",
        }, x_rap=True)
        try:
            return data["data"]["items"][0]["note_card"]
        except (KeyError, IndexError, TypeError):
            return {}

    def get_comments(self, note: NoteItem | str, xsec_token: str | None = None, *, expand_sub: bool = True, max_sub_pages: int = 5) -> Generator[CommentItem, None, None]:
        note_id, token = _resolve_note(note, xsec_token)
        cursor = ""
        has_more = True
        while has_more:
            data = self._get("/api/sns/web/v2/comment/page", {"note_id": note_id, "cursor": cursor, "xsec_token": token})
            cd = data.get("data") or {}
            for c in cd.get("comments", []):
                item = _parse_comment(c)
                if expand_sub and c.get("sub_comment_has_more"):
                    item.sub_comments = list(self._expand_sub_comments(note_id, c["id"], c.get("sub_comment_cursor", ""), token, max_sub_pages))
                yield item
            has_more = cd.get("has_more", False)
            cursor = cd.get("cursor", "")

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        return self._get("/api/sns/web/v1/user/otherinfo", {"target_user_id": user_id}).get("data", {})

    def get_user_notes(self, user_id: str, count: int = 30) -> list[NoteItem]:
        data = self._get("/api/sns/web/v1/user_posted", {"num": str(count), "cursor": "", "user_id": user_id}, sign_format="xyw")
        return _parse_note_list(data)

    # ==================================================================
    # Public API — async
    # ==================================================================

    async def homefeed_async(self, count: int = 20) -> list[NoteItem]:
        data = await self._post_async("/api/sns/web/v1/homefeed", {
            "cursor_score": "", "num": count, "refresh_type": 1,
            "note_index": 0, "unread_begin_note_id": "", "unread_end_note_id": "",
            "unread_note_count": 0, "category": "homefeed_recommend",
        }, x_rap=True)
        return _parse_note_list(data)

    async def search_notes_async(self, keyword: str, page_size: int = 20, sort: str = "general", note_type: int = 0) -> AsyncGenerator[NoteItem, None]:
        """异步搜索；统一使用 v2 接口。"""
        async for item in self.search_notes_v2_async(keyword, page_size, sort, note_type):
            yield item

    async def search_notes_v2_async(self, keyword: str, page_size: int = 20, sort: str = "general", note_type: int = 0) -> AsyncGenerator[NoteItem, None]:
        """v2 搜索 (so.xiaohongshu.com)，推荐使用，默认启用。"""
        import uuid
        page = 1
        has_more = True
        session_id = str(uuid.uuid4())
        search_id = self._signer.get_search_id()
        while has_more:
            payload = {
                "keyword": keyword, "page": page, "page_size": page_size,
                "search_id": search_id,
                "sort": sort, "note_type": note_type,
                "ext_flags": [],
                "geo": "",
                "image_formats": ["jpg", "webp", "avif"],
                "message_id": "sending",
                "session_id": session_id,
            }
            data = await self._post_async(
                "/api/sns/web/v2/search/notes", payload, x_rap=True, host=self.SEARCH_HOST,
            )
            items = _parse_note_list(data)
            for item in items:
                yield item
            has_more = bool((data.get("data") or {}).get("has_more", False)) and bool(items)
            page += 1

    async def get_note_detail_async(self, note: NoteItem | str, xsec_token: str | None = None) -> dict[str, Any]:
        note_id, token = _resolve_note(note, xsec_token)
        data = await self._post_async("/api/sns/web/v1/feed", {
            "source_note_id": note_id, "xsec_token": token, "xsec_source": "pc_feed",
        }, x_rap=True)
        try:
            return data["data"]["items"][0]["note_card"]
        except (KeyError, IndexError, TypeError):
            return {}

    async def get_comments_async(self, note: NoteItem | str, xsec_token: str | None = None, *, expand_sub: bool = True, max_sub_pages: int = 5) -> AsyncGenerator[CommentItem, None]:
        note_id, token = _resolve_note(note, xsec_token)
        cursor = ""
        has_more = True
        while has_more:
            data = await self._get_async("/api/sns/web/v2/comment/page", {"note_id": note_id, "cursor": cursor, "xsec_token": token})
            cd = data.get("data") or {}
            for c in cd.get("comments", []):
                item = _parse_comment(c)
                if expand_sub and c.get("sub_comment_has_more"):
                    item.sub_comments = [s async for s in self._expand_sub_comments_async(note_id, c["id"], c.get("sub_comment_cursor", ""), token, max_sub_pages)]
                yield item
            has_more = cd.get("has_more", False)
            cursor = cd.get("cursor", "")

    async def get_user_info_async(self, user_id: str) -> dict[str, Any]:
        data = await self._get_async("/api/sns/web/v1/user/otherinfo", {"target_user_id": user_id})
        return (data.get("data") or {})

    async def get_user_notes_async(self, user_id: str, count: int = 30) -> list[NoteItem]:
        data = await self._get_async("/api/sns/web/v1/user_posted", {"num": str(count), "cursor": "", "user_id": user_id}, sign_format="xyw")
        return _parse_note_list(data)

    # ---- sub-comment expanders ----

    def _expand_sub_comments(self, note_id: str, root_id: str, cursor: str, xsec_token: str, max_pages: int) -> Generator[CommentItem, None, None]:
        page = 1
        has_more = bool(cursor)
        while has_more and page <= max_pages:
            data = self._get("/api/sns/web/v2/comment/sub/page", {
                "note_id": note_id, "root_comment_id": root_id, "num": 10, "cursor": cursor, "xsec_token": xsec_token,
            })
            for sc in (data.get("data") or {}).get("comments", []):
                yield _parse_comment(sc)
            has_more = (data.get("data") or {}).get("has_more", False)
            cursor = (data.get("data") or {}).get("cursor", "")
            page += 1

    async def _expand_sub_comments_async(self, note_id: str, root_id: str, cursor: str, xsec_token: str, max_pages: int) -> AsyncGenerator[CommentItem, None]:
        page = 1
        has_more = bool(cursor)
        while has_more and page <= max_pages:
            data = await self._get_async("/api/sns/web/v2/comment/sub/page", {
                "note_id": note_id, "root_comment_id": root_id, "num": 10, "cursor": cursor, "xsec_token": xsec_token,
            })
            for sc in (data.get("data") or {}).get("comments", []):
                yield _parse_comment(sc)
            has_more = (data.get("data") or {}).get("has_more", False)
            cursor = (data.get("data") or {}).get("cursor", "")
            page += 1


# ---- helpers ----

def _resolve_note(note: NoteItem | str, xsec_token: str | None) -> tuple[str, str]:
    if isinstance(note, NoteItem):
        token = note.xsec_token or xsec_token
        if not token:
            raise ValueError("xsec_token is required")
        return note.note_id, token
    if not xsec_token:
        raise ValueError("xsec_token is required when passing note_id directly")
    return note, xsec_token


def _parse_comment(c: dict[str, Any]) -> CommentItem:
    ui = c.get("user_info", {}) or {}
    return CommentItem(
        comment_id=c.get("id", ""),
        user=ui.get("nickname", ""),
        content=c.get("content", ""),
        like_count=c.get("like_count", 0),
        create_time=c.get("create_time", 0),
        sub_comments=[_parse_comment(sc) for sc in (c.get("sub_comments") or [])],
        sub_comment_count=c.get("sub_comment_count", 0),
    )


def _note_id_timestamp_ms(note_id: str) -> int:
    """从小红书笔记 ID 前 8 位解析精确发布时间。"""
    try:
        return int(note_id[:8], 16) * 1000
    except (TypeError, ValueError):
        return 0


def _parse_note_list(data: dict[str, Any]) -> list[NoteItem]:
    items = []
    for item in (data.get("data") or {}).get("items", []) or (data.get("data") or {}).get("notes", []):
        card = item.get("note_card", {}) or item
        info = card.get("interact_info", {}) or {}
        user = card.get("user", {}) or {}
        items.append(NoteItem(
            note_id=item.get("id") or card.get("note_id", ""),
            title=card.get("display_title") or card.get("title", ""),
            desc=card.get("desc", ""),
            author=user.get("nickname", ""),
            author_id=user.get("user_id", ""),
            liked_count=info.get("liked_count", 0),
            collected_count=info.get("collected_count", 0),
            comment_count=info.get("comment_count", 0),
            xsec_token=item.get("xsec_token", ""),
            image_count=len(card.get("image_list", []) or []),
            posted_at=_note_id_timestamp_ms(item.get("id") or card.get("note_id", "")),
            raw=card,
        ))
    return items
