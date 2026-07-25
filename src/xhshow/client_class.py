from __future__ import annotations

import json
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import requests

from .client import Xhshow

__all__ = ["XHSClient", "NoteItem", "CommentItem"]


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


# ---- Main client ----

class XHSClient:
    """小红书 Web API 客户端，封装签名 + cookie + 常用接口。

    Usage::

        client = XHSClient(cookie_string)
        for note in client.search_notes("美食"):
            print(note.title)
            detail = client.get_note_detail(note)
            for comment in client.get_comments(note):
                print(comment.user, comment.content)
    """

    BASE_HOST = "https://edith.xiaohongshu.com"
    UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    _REQUEST_INTERVAL = 1.2  # seconds between API calls

    def __init__(self, cookie_str: str) -> None:
        self._cookie_str = cookie_str
        self._cookies = self._parse_cookies(cookie_str)
        self._signer = Xhshow()
        self._last_request = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def homefeed(self, count: int = 20) -> list[NoteItem]:
        """首页推荐流。"""
        payload = {
            "cursor_score": "",
            "num": count,
            "refresh_type": 1,
            "note_index": 0,
            "unread_begin_note_id": "",
            "unread_end_note_id": "",
            "unread_note_count": 0,
            "category": "homefeed_recommend",
        }
        data = self._post("/api/sns/web/v1/homefeed", payload, x_rap=True)
        return self._parse_note_list(data)

    def search_notes(
        self,
        keyword: str,
        page_size: int = 20,
        sort: str = "general",
        note_type: int = 0,
    ) -> Generator[NoteItem, None, None]:
        """搜索笔记（分页生成器）。"""
        page = 1
        has_more = True
        while has_more:
            payload = {
                "keyword": keyword,
                "page": page,
                "page_size": page_size,
                "search_id": self._signer.get_search_id(),
                "sort": sort,
                "note_type": note_type,
            }
            data = self._post("/api/sns/web/v1/search/notes", payload, x_rap=True)
            items = self._parse_note_list(data)
            yield from items
            has_more = data.get("data", {}).get("has_more", False)
            page += 1

    def get_note_detail(self, note: NoteItem | str, xsec_token: str | None = None) -> dict[str, Any]:
        """获取单篇笔记详情。

        Args:
            note: NoteItem 或 note_id 字符串
            xsec_token: 如果传 note_id 则必须提供
        """
        if isinstance(note, NoteItem):
            note_id = note.note_id
            xsec_token = note.xsec_token or xsec_token
        else:
            note_id = note
        if not xsec_token:
            raise ValueError("xsec_token is required for note detail")

        payload = {
            "source_note_id": note_id,
            "xsec_token": xsec_token,
            "xsec_source": "pc_feed",
        }
        data = self._post("/api/sns/web/v1/feed", payload, x_rap=True)
        try:
            return data["data"]["items"][0]["note_card"]
        except (KeyError, IndexError, TypeError):
            return {}

    def get_comments(
        self,
        note: NoteItem | str,
        xsec_token: str | None = None,
        *,
        expand_sub: bool = True,
        max_sub_pages: int = 5,
    ) -> Generator[CommentItem, None, None]:
        """获取笔记所有评论（分页生成器，自动展开子评论）。

        Yields CommentItem with sub_comments populated.
        """
        if isinstance(note, NoteItem):
            note_id = note.note_id
            xsec_token = note.xsec_token or xsec_token
        else:
            note_id = note
        if not xsec_token:
            raise ValueError("xsec_token is required")

        cursor = ""
        has_more = True
        while has_more:
            params = {"note_id": note_id, "cursor": cursor, "xsec_token": xsec_token}
            data = self._get("/api/sns/web/v2/comment/page", params)
            comments_data = data.get("data", {})
            for c in comments_data.get("comments", []):
                item = self._parse_comment(c)
                if expand_sub and c.get("sub_comment_has_more"):
                    item.sub_comments = list(
                        self._expand_sub_comments(note_id, c["id"], c.get("sub_comment_cursor", ""), xsec_token, max_sub_pages)
                    )
                yield item
            has_more = comments_data.get("has_more", False)
            cursor = comments_data.get("cursor", "")

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取用户信息。"""
        data = self._get("/api/sns/web/v1/user/otherinfo", {"target_user_id": user_id})
        return data.get("data", {})

    def get_user_notes(self, user_id: str, count: int = 30) -> list[NoteItem]:
        """获取用户发布的笔记列表。"""
        params = {"num": str(count), "cursor": "", "user_id": user_id}
        data = self._get("/api/sns/web/v1/user_posted", params, sign_format="xyw")
        return self._parse_note_list(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cookies(cookie_str: str) -> dict[str, str]:
        return {k: v for item in cookie_str.split("; ") if "=" in item for k, v in [item.split("=", 1)]}

    def _wait(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._REQUEST_INTERVAL:
            time.sleep(self._REQUEST_INTERVAL - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, params: dict[str, Any], sign_format: str = "xys") -> dict[str, Any]:
        uri = f"{self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_get(
            uri=uri,
            cookies=self._cookies,
            params=params,
            sign_format=sign_format,
        )
        self._wait()
        resp = requests.get(uri, headers={**headers, "User-Agent": self.UA}, cookies=self._cookies, params=params, timeout=30)
        return resp.json()

    def _post(self, path: str, payload: dict[str, Any], x_rap: bool = False, sign_format: str = "xys") -> dict[str, Any]:
        uri = f"{self.BASE_HOST}{path}"
        headers = self._signer.sign_headers_post(
            uri=uri,
            cookies=self._cookies,
            payload=payload,
            sign_format=sign_format,
            x_rap=x_rap,
        )
        self._wait()
        resp = requests.post(uri, headers={**headers, "User-Agent": self.UA}, cookies=self._cookies, json=payload, timeout=30)
        return resp.json()

    def _expand_sub_comments(
        self,
        note_id: str,
        root_comment_id: str,
        sub_cursor: str,
        xsec_token: str,
        max_pages: int,
    ) -> Generator[CommentItem, None, None]:
        page = 1
        has_more = bool(sub_cursor)
        while has_more and page <= max_pages:
            params = {
                "note_id": note_id,
                "root_comment_id": root_comment_id,
                "num": 10,
                "cursor": sub_cursor,
                "xsec_token": xsec_token,
            }
            data = self._get("/api/sns/web/v2/comment/sub/page", params)
            sub_data = data.get("data", {})
            for sc in sub_data.get("comments", []):
                yield self._parse_comment(sc)
            has_more = sub_data.get("has_more", False)
            sub_cursor = sub_data.get("cursor", "")
            page += 1

    @staticmethod
    def _parse_comment(c: dict[str, Any]) -> CommentItem:
        user_info = c.get("user_info", {}) or {}
        sub_comments = [
            CommentItem(
                comment_id=sc.get("id", ""),
                user=(sc.get("user_info", {}) or {}).get("nickname", ""),
                content=sc.get("content", ""),
                like_count=sc.get("like_count", 0),
            )
            for sc in (c.get("sub_comments") or [])
        ]
        return CommentItem(
            comment_id=c.get("id", ""),
            user=user_info.get("nickname", ""),
            content=c.get("content", ""),
            like_count=c.get("like_count", 0),
            create_time=c.get("create_time", 0),
            sub_comments=sub_comments,
            sub_comment_count=c.get("sub_comment_count", 0),
        )

    @staticmethod
    def _parse_note_list(data: dict[str, Any]) -> list[NoteItem]:
        items = []
        for item in data.get("data", {}).get("items", []) or data.get("data", {}).get("notes", []):
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
                raw=card,
            ))
        return items
