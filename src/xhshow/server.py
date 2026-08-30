"""xhs-serve - 把 XHSClient 封装成 HTTP 服务(FastAPI)。

复用 `XHSClient` 的多账号轮询、cookie 失效自动切换与全局限速(1.2s/请求),
所有接口返回 JSON。

所有 ``/api`` 接口均为 POST + JSON body, cookie 与长参数(如完整笔记链接)
放 body 而非 URL/Header, 避免多账号时超 Header 大小限制。

cookie 提供优先级::

    1. body ``cookies`` 数组(推荐, 服务无状态): 每个元素一个账号 cookie,
       由调用方后端统一存储管理; 失效时接口返回 401, 调用方据此更新存储。
    2. 请求头 ``X-XHS-Cookie``(兼容旧调用方式, 多账号用 ``;;`` 分隔)。
    3. 服务端池(可选): 环境变量 ``XHS_COOKIES`` / ``XHS_COOKIE`` /
       ``XHS_COOKIE_API`` / ``~/.xhs-cli/cookie``(与 xhs-cli 共享),
       前两者均未提供时使用; 全部失效返回 503。

用例::

    # 启动(需安装 serve extra: pip install "xhshow[serve]")
    xhs-serve --host 0.0.0.0 --port 8080
    # 或
    uvicorn xhshow.server:app --port 8080

    # 调用(body 传 cookie)
    curl -X POST http://127.0.0.1:8080/api/search \\
         -H "Content-Type: application/json" \\
         -d '{"cookies": ["a1=...; web_session=..."], "keyword": "咖啡", "limit": 5}'

环境变量::

    XHS_COOKIES          服务端池: 多账号 cookie, 用换行或 ;; 分隔(可选)
    XHS_COOKIE           服务端池: 单账号 cookie(可选)
    XHS_COOKIE_API       服务端池: 远端 Cookie API 地址(约定同 xhs-cli)
    XHS_COOKIE_API_AUTH  远端 Cookie API 的 Bearer 密钥
    XHS_COOKIE_FILE      本地 cookie 文件路径(默认 ~/.xhs-cli/cookie, 每行一个账号)
    XHS_API_KEY          设置后所有 /api 接口要求 Authorization: Bearer <key>

注意: 全局限速 1.2s/请求 为类级别共享(保护账号避免风控), 并发请求会排队;
需要更高吞吐请传入更多 cookie 账号。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__
from .api import AllCookiesInvalidError, XHSClient, XHSVerifyError
from .cli import (
    COOKIE_FILE,
    _build_client,
    _detail_to_json,
    _fetch_remote_cookies,
    _load_cookie_lines,
    _make_api_invalidate,
    _note_dict,
    _parse_note_ref,
    _remove_cookie_from_file,
)

__all__ = ["app", "create_app", "main"]

# 请求级 cookie 的客户端缓存上限(按 cookie 串去重, LRU 淘汰)
_CLIENT_CACHE_MAX = 64


# ---------------------------------------------------------------------------
# 服务端 cookie 池(可选)
# ---------------------------------------------------------------------------


def _load_pool_cookies() -> tuple[list[str], Any]:
    """加载服务端池的 cookie 列表与失效回调, 找不到返回空列表。

    优先级: ``XHS_COOKIES``(多账号) > ``XHS_COOKIE`` > ``XHS_COOKIE_API``(远端)
    > ``~/.xhs-cli/cookie``(每行一个, 与 xhs-cli set-cookie 共享)。
    """
    env_multi = os.environ.get("XHS_COOKIES", "")
    if env_multi.strip():
        cookies = [c.strip() for c in env_multi.replace(";;", "\n").splitlines() if c.strip()]
        if cookies:
            return cookies, None
    env = os.environ.get("XHS_COOKIE", "")
    if env.strip():
        return [env.strip()], None
    api_base = os.environ.get("XHS_COOKIE_API", "")
    if api_base:
        api_auth = os.environ.get("XHS_COOKIE_API_AUTH")
        accounts = _fetch_remote_cookies(api_base, auth=api_auth)
        return [a["cookie"] for a in accounts], _make_api_invalidate(api_base, accounts, auth=api_auth)
    cookies = _load_cookie_lines(COOKIE_FILE)
    if cookies:
        return cookies, _remove_cookie_from_file
    return [], None


def _check_auth(authorization: str | None = Header(default=None)) -> None:
    """设置了 XHS_API_KEY 时, 要求请求携带 Authorization: Bearer <key>。"""
    key = os.environ.get("XHS_API_KEY", "")
    if key and authorization != f"Bearer {key}":
        raise HTTPException(status_code=401, detail="无效或缺少 API key (Authorization: Bearer <key>)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cookies, on_invalid = _load_pool_cookies()
    # 服务端池可选: 为空则纯请求级 cookie 模式
    app.state.client = _build_client(cookies, on_cookie_invalid=on_invalid) if cookies else None
    app.state.cookie_count = len(cookies)
    app.state.client_cache: dict[str, XHSClient] = {}
    app.state.client_cache_lock = asyncio.Lock()
    if cookies:
        print(
            f"✅ xhs-serve 已就绪: 服务端池 {len(cookies)} 个账号 + 请求级 cookie 模式, 全局限速 1.2s/请求",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            "✅ xhs-serve 已就绪: 纯请求级 cookie 模式(请求体 cookies 字段必传), 全局限速 1.2s/请求",
            file=sys.stderr,
            flush=True,
        )
    yield


# ---------------------------------------------------------------------------
# 请求级 cookie -> XHSClient(带 LRU 缓存)
# ---------------------------------------------------------------------------


@dataclass
class _ClientCtx:
    """一次请求使用的客户端及其来源。"""

    client: XHSClient
    per_request: bool  # True = 来自 body/header 的请求级 cookie(失效回 401); False = 服务端池(失效回 503)


def _log_invalid_cookie(cookie: str) -> None:
    """请求级 cookie 失效回调: 只打日志, 不动服务端任何存储。"""
    masked = cookie[:20] + "..." if len(cookie) > 20 else cookie
    print(f"⚠️ 请求级 cookie 已失效(登录过期): {masked}", file=sys.stderr, flush=True)


async def _client_from_cookies(request: Request, cookies: list[str]) -> _ClientCtx:
    """按 cookie 串查/建客户端(LRU 缓存), 标记为请求级来源。"""
    key = ";;".join(cookies)
    cache: dict[str, XHSClient] = request.app.state.client_cache
    async with request.app.state.client_cache_lock:
        client = cache.pop(key, None)
        if client is None:
            client = _build_client(cookies, on_cookie_invalid=_log_invalid_cookie)
        cache[key] = client  # 重新插入 = 移到 MRU 端
        while len(cache) > _CLIENT_CACHE_MAX:
            cache.pop(next(iter(cache)))  # 淘汰最久未用(不关连接, 交给 GC)
    request.state.cookie_cache_key = key
    request.state.client_per_request = True
    return _ClientCtx(client, per_request=True)


async def _resolve_ctx(
    request: Request,
    body_cookies: list[str] | None,
    x_xhs_cookie: str | None,
) -> _ClientCtx:
    """解析本次请求的 XHSClient, 优先级: body cookies > X-XHS-Cookie 头 > 服务端池。

    有请求级 cookie -> 按 cookie 串查/建客户端(LRU 缓存); 都没有 -> 用服务端池(未配置则 400)。
    """
    cookies: list[str] = []
    if body_cookies is not None:
        cookies = [c.strip() for c in body_cookies if c and c.strip()]
        if not cookies:
            raise HTTPException(status_code=400, detail="cookies 字段不能为空(每个元素一个账号的 cookie 串)")
    elif x_xhs_cookie and x_xhs_cookie.strip():
        cookies = [c.strip() for c in x_xhs_cookie.split(";;") if c.strip()]
        if not cookies:
            raise HTTPException(status_code=400, detail="X-XHS-Cookie 头无效")
    if cookies:
        return await _client_from_cookies(request, cookies)

    pool: XHSClient | None = request.app.state.client
    if pool is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "未提供 cookie: 请在请求体 cookies 字段(或 X-XHS-Cookie 头)传入, 或在服务端配置 XHS_COOKIES 等环境变量"
            ),
        )
    request.state.client_per_request = False
    return _ClientCtx(pool, per_request=False)


# ---------------------------------------------------------------------------
# 请求体模型
# ---------------------------------------------------------------------------


class _CookiesBody(BaseModel):
    """公共字段: 请求级 cookie(可选, 不传走服务端池)。"""

    cookies: list[str] | None = Field(
        None, description="账号 cookie 列表, 每个元素一个账号, 多账号参与轮询; 不传则用服务端池"
    )


class WhoamiBody(_CookiesBody):
    pass


class HomefeedBody(_CookiesBody):
    count: int = Field(20, ge=1, le=100, description="拉取条数")


class SearchBody(_CookiesBody):
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    limit: int = Field(20, ge=1, le=200, description="最多返回条数")
    page_size: int = Field(20, ge=1, le=50, description="每页条数(上游接口)")
    sort: str = Field("general", description="general / time_descending / popularity_descending")
    note_type: int = Field(0, description="0 全部 / 1 视频 / 2 图文")


class DetailBody(_CookiesBody):
    note: str = Field(..., description="小红书链接(自动提取 xsec_token)或 note_id")
    xsec_token: str | None = Field(None, description="note 为纯 ID 时必传")


class CommentsBody(_CookiesBody):
    note: str = Field(..., description="小红书链接(自动提取 xsec_token)或 note_id")
    xsec_token: str | None = Field(None, description="note 为纯 ID 时必传")
    expand_sub: bool = Field(True, description="是否展开楼中楼")
    max_sub_pages: int = Field(5, ge=1, le=20, description="楼中楼最大翻页数")


class UserBody(_CookiesBody):
    notes: int = Field(0, ge=0, le=100, description="附带笔记数, 0 不带")


class UserNotesBody(_CookiesBody):
    count: int = Field(30, ge=1, le=100, description="拉取条数")


# ---------------------------------------------------------------------------
# 异常映射与公共工具
# ---------------------------------------------------------------------------


def _http_error(request: Request, e: Exception) -> HTTPException:
    """XHSClient 异常 -> HTTP 状态码; 请求级 cookie 失效时同步剔除缓存。"""
    if isinstance(e, AllCookiesInvalidError):
        if getattr(request.state, "cookie_cache_key", None):
            request.app.state.client_cache.pop(request.state.cookie_cache_key, None)
        if getattr(request.state, "client_per_request", False):
            return HTTPException(status_code=401, detail="传入的 cookie 已失效(登录过期), 请更新后重试")
        return HTTPException(status_code=503, detail="服务端池的所有 cookie 均已失效, 请更新后重启服务")
    if isinstance(e, XHSVerifyError):
        return HTTPException(status_code=429, detail=f"触发风控验证(verify_type={e.verify_type}), 请更换/更新 cookie")
    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=502, detail=f"上游请求失败: {e}")


async def _resolve_note(note: str, xsec_token: str | None) -> tuple[str, str]:
    """note 参数(链接或 note_id) -> (note_id, xsec_token)。

    `_parse_note_ref` 内部对短链会发同步 HTTP 请求, 放线程池避免阻塞事件循环。
    """
    try:
        note_id, token = await asyncio.to_thread(_parse_note_ref, note)
    except SystemExit as e:
        msg = str(e.code) if isinstance(e.code, str) else "无法解析笔记链接"
        raise HTTPException(status_code=400, detail=msg) from None
    token = token or xsec_token
    if not token:
        raise HTTPException(
            status_code=400,
            detail="需要 xsec_token: 传带 xsec_token 的完整链接, 或额外指定 xsec_token 字段",
        )
    return note_id, token


# ---------------------------------------------------------------------------
# 路由(全部 POST + JSON body, cookie 与长参数放 body 避免 URL/Header 超限)
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", dependencies=[Depends(_check_auth)])


@router.post("/whoami", summary="当前登录账号信息")
async def whoami(
    request: Request,
    payload: WhoamiBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        return await ctx.client.me_async()
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/homefeed", summary="首页推荐流")
async def homefeed(
    request: Request,
    payload: HomefeedBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        notes = await ctx.client.homefeed_async(count=payload.count)
        return {"notes": [_note_dict(n) for n in notes]}
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/search", summary="搜索笔记")
async def search(
    request: Request,
    payload: SearchBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        notes = []
        async for n in ctx.client.search_notes_async(
            payload.keyword, page_size=payload.page_size, sort=payload.sort, note_type=payload.note_type
        ):
            notes.append(_note_dict(n))
            if len(notes) >= payload.limit:
                break
        return {"keyword": payload.keyword, "count": len(notes), "notes": notes}
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/detail", summary="笔记详情(支持完整链接或 note_id + xsec_token)")
async def detail(
    request: Request,
    payload: DetailBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        note_id, token = await _resolve_note(payload.note, payload.xsec_token)
        card = await ctx.client.get_note_detail_async(note_id, xsec_token=token)
        if not card:
            raise HTTPException(status_code=404, detail="未获取到详情(可能被风控或链接失效)")
        return _detail_to_json(card, note_id, token)
    except HTTPException:
        raise
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/comments", summary="笔记评论(含楼中楼)")
async def comments(
    request: Request,
    payload: CommentsBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        note_id, token = await _resolve_note(payload.note, payload.xsec_token)
        items = [
            item
            async for item in ctx.client.get_comments_async(
                note_id, xsec_token=token, expand_sub=payload.expand_sub, max_sub_pages=payload.max_sub_pages
            )
        ]
        return {"note_id": note_id, "count": len(items), "comments": items}
    except HTTPException:
        raise
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/user/{user_id}", summary="用户信息(+可选前 N 条笔记)")
async def user(
    request: Request,
    user_id: str,
    payload: UserBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        info = await ctx.client.get_user_info_async(user_id) or {}
        out: dict[str, Any] = {"info": info}
        if payload.notes:
            out["notes"] = [_note_dict(n) for n in await ctx.client.get_user_notes_async(user_id, count=payload.notes)]
        return out
    except Exception as e:
        raise _http_error(request, e) from None


@router.post("/user/{user_id}/notes", summary="用户发布的笔记")
async def user_notes(
    request: Request,
    user_id: str,
    payload: UserNotesBody,
    x_xhs_cookie: str | None = Header(default=None, alias="X-XHS-Cookie"),
) -> dict[str, Any]:
    ctx = await _resolve_ctx(request, payload.cookies, x_xhs_cookie)
    try:
        items = await ctx.client.get_user_notes_async(user_id, count=payload.count)
        return {"user_id": user_id, "count": len(items), "notes": [_note_dict(n) for n in items]}
    except Exception as e:
        raise _http_error(request, e) from None


# ---------------------------------------------------------------------------
# app 工厂与入口
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="xhshow API",
        description=(
            "小红书数据接口(多账号轮询 / cookie 失效自动切换 / 全局限速 1.2s/请求)。\n\n"
            "所有 `/api` 接口均为 POST + JSON body: cookie 通过请求体 `cookies` 数组传入"
            "(推荐, 服务无状态, 失效返回 401; 也兼容 `X-XHS-Cookie` 头), "
            "或不传走服务端环境变量池(失效返回 503)。"
        ),
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/health", summary="健康检查(不带鉴权)")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "accounts": getattr(app.state, "cookie_count", 0)}

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(prog="xhs-serve", description="xhshow HTTP 服务(FastAPI)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址(默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="监听端口(默认 8080)")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
