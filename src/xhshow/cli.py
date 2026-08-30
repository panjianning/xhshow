"""xhs-cli — 小红书 Web API 命令行工具。

基于 `XHSClient` 提供 homefeed / search / detail / comments / user /
user-notes / whoami / set-cookie / cookie 命令, 支持 text 与 JSON (`--json`)
两种输出。多账号时按 round-robin 轮询(底层 XHSClient 内置)。

用例::

    xhs-cli set-cookie "<Cookie 字符串>"       # 追加一个账号, 可多次调用
    xhs-cli cookie list                        # 列出已保存的账号(脱敏)
    xhs-cli cookie remove 2                    # 删除第 2 个账号
    xhs-cli whoami
    xhs-cli homefeed --count 5
    xhs-cli search "咖啡" --limit 10
    xhs-cli detail "https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy"
    xhs-cli comments <note_id> --xsec-token <token>
    xhs-cli user-notes <user_id> --count 30
    xhs-cli user <user_id> --notes 5

cookie 加载优先级: ``--cookie`` > ``--cookie-file`` > 环境变量 ``XHS_COOKIE``
> ``--cookie-api`` / 环境变量 ``XHS_COOKIE_API`` (远端接口)
> ``~/.xhs-cli/cookie`` (每行一个 cookie = 一个账号, 由 set-cookie 追加写入)。

远端 Cookie API 约定::

    GET  {base}/cookies                    -> [{"id": 1, "cookie": "..."}, ...]
    POST {base}/cookies/{id}/invalidate    -> 标记失效(cookie 带 id 时)
    POST {base}/cookies/invalidate         -> 标记失效(无 id, body: {"cookie": "..."})

接口需要鉴权时用 ``--cookie-api-auth <key>``(或环境变量 ``XHS_COOKIE_API_AUTH``),
请求会带上 ``Authorization: Bearer <key>`` 头(拉取与失效回调均携带)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

COOKIE_FILE = Path(os.environ.get("XHS_COOKIE_FILE", str(Path.home() / ".xhs-cli" / "cookie")))

__all__ = ["main"]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _fmt_time(ts: Any) -> str:
    """时间戳(秒或毫秒) → 人类可读时间, 兼容字符串输入。"""
    try:
        t = int(ts)
        if t < 10**12:  # 秒 → 毫秒
            t *= 1000
        return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(ts) if ts else ""


def _note_dict(n: Any) -> dict[str, Any]:
    """NoteItem → dict, 去掉体积巨大的 raw 字段。"""
    d = asdict(n)
    d.pop("raw", None)
    return d


def _print_notes(notes: list[Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps([_note_dict(n) for n in notes], ensure_ascii=False, indent=2))
        return
    for i, n in enumerate(notes, 1):
        line = f"{i:>3}. {n.title[:40]:<42} {n.author[:10]:<12}"
        line += f" ❤️{n.liked_count} 💬{n.comment_count} 📅{_fmt_time(n.posted_at)}"
        print(line)
        print(f"      id={n.note_id}")
        if n.xsec_token:
            print(f"      xsec_token={n.xsec_token}")


def _parse_note_ref(ref: str) -> tuple[str, str | None]:
    """把 note_id 或小红书链接解析为 (note_id, xsec_token)。

    支持 ``/explore/{id}``、``/discovery/item/{id}`` 链接(自动提取 query 里的
    xsec_token), 也支持 xhslink.com 短链(自动跟随重定向)。
    """
    if not ref.startswith("http"):
        return ref, None
    url = ref
    if "xhslink.com" in url:
        try:
            import httpx

            resp = httpx.get(url, follow_redirects=True, timeout=15)
            url = str(resp.url)
        except Exception:
            pass
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    token = qs.get("xsec_token", [None])[0]
    parts = [p for p in parsed.path.split("/") if p]
    note_id: str | None = None
    for i, p in enumerate(parts):
        if p in ("explore", "item") and i + 1 < len(parts):
            note_id = parts[i + 1]
            break
    if not note_id and parts:
        note_id = parts[-1]
    if not note_id:
        raise SystemExit(f"无法从链接解析 note_id: {ref}")
    return note_id, token


def _require_token(args: argparse.Namespace, ref: str) -> tuple[str, str]:
    note_id, token = _parse_note_ref(ref)
    token = token or args.xsec_token
    if not token:
        raise SystemExit(
            "需要 xsec_token: 用 --xsec-token 传入, 或直接传带 xsec_token 的小红书"
            "链接(https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy)"
        )
    return note_id, token


def _mask_cookie(cookie: str) -> str:
    """脱敏 cookie: 保留 a1 / web_session 前 8 位, 其余打码。"""
    parts: list[str] = []
    for item in cookie.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        if k in ("a1", "web_session", "webId", "customerClientId") and len(v) > 8:
            parts.append(f"{k}={v[:8]}...")
        elif k in ("a1", "web_session"):
            parts.append(f"{k}=***")
        else:
            parts.append(k)
    return "; ".join(parts) if parts else f"{cookie[:20]}..."


def _remove_cookie_from_file(cookie: str) -> None:
    """从配置文件删除指定 cookie 行(供失效自动剔除用)。"""
    lines = _load_cookie_lines(COOKIE_FILE)
    if cookie in lines:
        lines.remove(cookie)
        COOKIE_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"⚠️ 账号 cookie 已失效, 已自动移除: {_mask_cookie(cookie)} (剩余 {len(lines)} 个)", file=sys.stderr)


def _api_headers(auth: str | None) -> dict[str, str]:
    """Cookie API 的公共请求头(带鉴权时加 Bearer token)。"""
    return {"Authorization": f"Bearer {auth}"} if auth else {}


def _fetch_remote_cookies(api_base: str, auth: str | None = None) -> list[dict[str, Any]]:
    """从远端 Cookie API 拉取账号列表。

    ``GET {api_base}/cookies`` 需返回 JSON, 支持以下格式:
    - ``{"cookies": [{"id": 1, "cookie": "..."}, ...]}``
    - ``[{"id": 1, "cookie": "..."}, ...]``
    - ``["cookie 字符串", ...]`` (无 id, 失效时按字符串匹配)

    ``auth`` 非空时携带 ``Authorization: Bearer <auth>`` 头。
    """
    try:
        import httpx
    except ModuleNotFoundError as e:
        if e.name == "httpx":
            raise SystemExit("缺少依赖 httpx, 请安装: pip install 'xhshow[client]' 或 'xhshow[cli]'") from None
        raise
    url = api_base.rstrip("/") + "/cookies"
    try:
        resp = httpx.get(url, headers=_api_headers(auth), timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise SystemExit(f"从 Cookie API 拉取失败: {url} ({e})") from None
    items = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit(f"Cookie API 返回格式不符: {url} (期望 cookies 列表)")
    accounts: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, str) and it.strip():
            accounts.append({"id": None, "cookie": it.strip()})
        elif isinstance(it, dict) and it.get("cookie"):
            accounts.append({"id": it.get("id"), "cookie": it["cookie"]})
    if not accounts:
        raise SystemExit(f"Cookie API 返回空账号列表: {url}")
    return accounts


def _make_api_invalidate(api_base: str, accounts: list[dict[str, Any]], auth: str | None = None) -> Any:
    """构造远端模式的 cookie 失效回调: 通知 API 标记该账号失效。

    带 id 的账号回调 ``POST {base}/cookies/{id}/invalidate``;
    无 id 时回调 ``POST {base}/cookies/invalidate``, body 为 {"cookie": "..."}。
    网络异常不打断请求流程(下次拉取仍会拿到该账号, 由远端负责清理)。
    """
    id_map = {a["cookie"]: a["id"] for a in accounts}
    base = api_base.rstrip("/")
    headers = _api_headers(auth)

    def _invalidate(cookie: str) -> None:
        try:
            import httpx

            cid = id_map.get(cookie)
            if cid is not None:
                httpx.post(f"{base}/cookies/{cid}/invalidate", headers=headers, timeout=15)
            else:
                httpx.post(f"{base}/cookies/invalidate", json={"cookie": cookie}, headers=headers, timeout=15)
        except Exception:
            pass
        print(f"⚠️ 账号 cookie 已失效, 已通知远端 API: {_mask_cookie(cookie)}", file=sys.stderr)

    return _invalidate


def _build_client(cookies: list[str], on_cookie_invalid: Any = None) -> Any:
    try:
        from .api import XHSClient
    except ModuleNotFoundError as e:
        if e.name == "httpx":
            raise SystemExit("缺少依赖 httpx, 请安装: pip install 'xhshow[client]' 或 'xhshow[cli]'") from None
        raise
    return XHSClient(cookies, on_cookie_invalid=on_cookie_invalid or _remove_cookie_from_file)


def _load_cookie_lines(path: Path) -> list[str]:
    """从文件读取 cookie, 每行一个(自动过滤空行)。"""
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _resolve_cookie(args: argparse.Namespace) -> tuple[list[str], Any]:
    """返回 (cookie 列表, 失效回调或 None)。

    优先级: --cookie > --cookie-file > XHS_COOKIE > --cookie-api / XHS_COOKIE_API > COOKIE_FILE。
    """
    if args.cookie:
        return [args.cookie], None
    if args.cookie_file:
        p = Path(args.cookie_file)
        if not p.exists():
            raise SystemExit(f"cookie 文件不存在: {p}")
        cookies = _load_cookie_lines(p)
        if not cookies:
            raise SystemExit(f"cookie 文件为空: {p}")
        return cookies, None
    env = os.environ.get("XHS_COOKIE")
    if env:
        return [env], None
    api_base = getattr(args, "cookie_api", None) or os.environ.get("XHS_COOKIE_API")
    if api_base:
        api_auth = getattr(args, "cookie_api_auth", None) or os.environ.get("XHS_COOKIE_API_AUTH")
        accounts = _fetch_remote_cookies(api_base, auth=api_auth)
        return [a["cookie"] for a in accounts], _make_api_invalidate(api_base, accounts, auth=api_auth)
    cookies = _load_cookie_lines(COOKIE_FILE)
    if not cookies:
        raise SystemExit(
            "未找到 cookie。请先运行: xhs-cli set-cookie '<cookie>'\n"
            "或通过 --cookie / --cookie-file / --cookie-api / 环境变量 XHS_COOKIE 提供。"
        )
    return cookies, None


# ---------------------------------------------------------------------------
# 各子命令
# ---------------------------------------------------------------------------


def cmd_set_cookie(args: argparse.Namespace) -> int:
    """追加一个 cookie 到配置文件(支持多账号)。"""
    cookie = args.cookie_value.strip()
    if not cookie:
        raise SystemExit("cookie 不能为空")
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    existed = _load_cookie_lines(COOKIE_FILE)
    if cookie in existed:
        print(f"⚠️ cookie 已存在, 未重复添加 (共 {len(existed)} 个账号)")
        return 0
    lines = existed + [cookie]
    COOKIE_FILE.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(COOKIE_FILE, 0o600)
    except OSError:
        pass
    print(f"✅ 已添加账号 #{len(lines)} -> {COOKIE_FILE} (共 {len(lines)} 个账号, round-robin 轮询)")
    return 0


def cmd_cookie(args: argparse.Namespace) -> int:
    """管理多账号 cookie: list / remove N / clear。"""
    cookies = _load_cookie_lines(COOKIE_FILE)
    if args.action == "list":
        if not cookies:
            print("(空, 用 xhs-cli set-cookie '<cookie>' 添加)")
            return 0
        for i, c in enumerate(cookies, 1):
            print(f"#{i}: {_mask_cookie(c)}")
        print(f"\n共 {len(cookies)} 个账号, 存于 {COOKIE_FILE}")
        return 0
    if args.action == "clear":
        COOKIE_FILE.write_text("")
        print(f"✅ 已清空所有 cookie ({len(cookies)} 个)")
        return 0
    if args.action == "remove":
        if not args.index:
            raise SystemExit("用法: xhs-cli cookie remove <序号>")
        idx = args.index - 1
        if not 0 <= idx < len(cookies):
            raise SystemExit(f"序号无效: {args.index} (共 {len(cookies)} 个)")
        removed = cookies.pop(idx)
        COOKIE_FILE.write_text("\n".join(cookies) + ("\n" if cookies else ""))
        print(f"✅ 已删除 #{args.index}: {_mask_cookie(removed)} (剩 {len(cookies)} 个)")
        return 0
    raise SystemExit(f"未知操作: {args.action}")


def cmd_whoami(args: argparse.Namespace, client: Any) -> None:
    data = client.me()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"昵称    : {data.get('nickname', '?')}")
    print(f"user_id : {data.get('user_id', '?')}")
    print(f"小红书号 : {data.get('red_id', '?')}")
    if data.get("desc"):
        print(f"简介    : {data['desc']}")


def cmd_homefeed(args: argparse.Namespace, client: Any) -> None:
    notes = client.homefeed(count=args.count)
    _print_notes(notes, args.json)


def cmd_search(args: argparse.Namespace, client: Any) -> None:
    notes: list[Any] = []
    for n in client.search_notes(args.keyword, page_size=args.page_size, sort=args.sort, note_type=args.note_type):
        notes.append(n)
        if args.limit and len(notes) >= args.limit:
            break
    _print_notes(notes, args.json)


def _detail_to_json(card: dict[str, Any], note_id: str, xsec_token: str) -> dict[str, Any]:
    """把详情 card 归一化为固定 schema 的 dict。

    字段对齐外部消费方约定的结构:
    note_id / xsec_token / title / desc / type / url /
    author / author_id / likes / comments / collects / shares /
    tags / images / created_time / last_update_time / ip_location
    """
    from .api import _extract_image_urls

    user = card.get("user") or {}
    inter = card.get("interact_info") or {}
    tags = [t.get("name", "") for t in (card.get("tag_list") or []) if t.get("name")]
    images = _extract_image_urls(card)

    def _ms(ts: Any) -> int:
        """时间戳(秒或毫秒) → 毫秒, 取不到返回 0。"""
        try:
            t = int(ts)
            if t and t < 10**12:
                t *= 1000
            return t
        except (TypeError, ValueError):
            return 0

    def _str(n: Any) -> str:
        return str(n) if n is not None else "0"

    url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source="

    return {
        "note_id": card.get("note_id", note_id),
        "xsec_token": xsec_token,
        "title": card.get("title") or "",
        "desc": card.get("desc") or "",
        "type": card.get("type") or "",
        "url": url,
        "author": user.get("nickname", "") or "",
        "author_id": user.get("user_id", "") or "",
        "likes": _str(inter.get("liked_count", 0)),
        "comments": _str(inter.get("comment_count", 0)),
        "collects": _str(inter.get("collected_count", 0)),
        "shares": _str(inter.get("share_count", 0)),
        "tags": tags,
        "images": images,
        "created_time": _ms(card.get("time")),
        "last_update_time": _ms(card.get("last_update_time")),
        "ip_location": card.get("ip_location") or "",
    }


def cmd_detail(args: argparse.Namespace, client: Any) -> None:
    from .api import _extract_image_urls

    note_id, token = _require_token(args, args.note)
    card = client.get_note_detail(note_id, xsec_token=token)
    if not card:
        raise SystemExit("未获取到详情(可能被风控或链接失效)")
    if args.json:
        print(json.dumps(_detail_to_json(card, note_id, token or ""), ensure_ascii=False, indent=2))
        return
    user = card.get("user") or {}
    inter = card.get("interact_info") or {}
    tags = [t.get("name", "") for t in (card.get("tag_list") or [])]
    print(f"标题   : {card.get('title') or ''}")
    print(f"作者   : {user.get('nickname', '?')}  (id={user.get('user_id', '')})")
    print(f"笔记ID : {card.get('note_id', '')}   IP={card.get('ip_location', '') or '未知'}")
    print(f"发布   : {_fmt_time(card.get('time'))}   更新: {_fmt_time(card.get('last_update_time'))}")
    print(
        f"互动   : ❤️{inter.get('liked_count', 0)}  ⭐{inter.get('collected_count', 0)}  "
        f"💬{inter.get('comment_count', 0)}  🔗{inter.get('share_count', 0)}"
    )
    print(f"图片   : {len(card.get('image_list') or [])} 张   类型: {card.get('type', '')}")
    if tags:
        print("标签   : " + ", ".join(tags))
    if args.images:
        urls = _extract_image_urls(card)
        if urls:
            print("图片链接:")
            for i, url in enumerate(urls, 1):
                print(f"  [{i}] {url}")
    desc = (card.get("desc") or "").strip()
    if desc:
        print("\n" + desc)


def cmd_comments(args: argparse.Namespace, client: Any) -> None:
    note_id, token = _require_token(args, args.note)
    items = list(
        client.get_comments(
            note_id, xsec_token=token, expand_sub=not args.no_sub, max_sub_pages=args.max_sub_pages
        )
    )
    if args.json:
        print(json.dumps([asdict(c) for c in items], ensure_ascii=False, indent=2))
        return
    if not items:
        print("(无评论)")
        return
    for i, c in enumerate(items, 1):
        print(f"[{i}] {c.user}: {c.content}")
        print(f"     👍{c.like_count}  🕒{_fmt_time(c.create_time)}  id={c.comment_id}")
        for sc in c.sub_comments:
            print(f"     ↳ {sc.user}: {sc.content}  👍{sc.like_count}  id={sc.comment_id}")


def cmd_user(args: argparse.Namespace, client: Any) -> None:
    info = client.get_user_info(args.user_id) or {}
    notes = client.get_user_notes(args.user_id, count=args.notes) if args.notes else []
    if args.json:
        out: dict[str, Any] = {"info": info}
        if notes:
            out["notes"] = [_note_dict(n) for n in notes]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if info:
        user = info.get("user") or {}
        print(f"昵称    : {user.get('nickname') or info.get('nickname') or '?'}")
        print(f"user_id : {args.user_id}")
        if info.get("note_count") is not None:
            print(f"笔记数  : {info['note_count']}")
    if notes:
        print()
        _print_notes(notes, False)


def cmd_user_notes(args: argparse.Namespace, client: Any) -> None:
    notes = client.get_user_notes(args.user_id, count=args.count)
    _print_notes(notes, args.json)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # 主 parser 和子 parser 的公共选项使用不同 dest,
    # 规避 argparse bpo-9351(子 parser 默认值覆盖父 parser 实参)的问题,
    # main() 里再合并, 因此 --cookie / --json / --cookie-file 放子命令前或后均可。
    common_main = argparse.ArgumentParser(add_help=False)
    common_main.add_argument("--cookie", dest="cookie", help="Cookie 字符串")
    common_main.add_argument("--cookie-file", dest="cookie_file", help="从文件读取 Cookie")
    common_main.add_argument(
        "--cookie-api", dest="cookie_api", help="远端 Cookie API 地址(如 http://host:8080/api/xhs)"
    )
    common_main.add_argument(
        "--cookie-api-auth",
        dest="cookie_api_auth",
        help="远端 Cookie API 的鉴权密钥(Authorization: Bearer <key>, 或环境变量 XHS_COOKIE_API_AUTH)",
    )
    common_main.add_argument("--json", dest="json", action="store_true", help="以 JSON 格式输出")

    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument("--cookie", dest="sub_cookie", help="Cookie 字符串")
    common_sub.add_argument("--cookie-file", dest="sub_cookie_file", help="从文件读取 Cookie")
    common_sub.add_argument(
        "--cookie-api", dest="sub_cookie_api", help="远端 Cookie API 地址(如 http://host:8080/api/xhs)"
    )
    common_sub.add_argument(
        "--cookie-api-auth",
        dest="sub_cookie_api_auth",
        help="远端 Cookie API 的鉴权密钥(Authorization: Bearer <key>)",
    )
    common_sub.add_argument("--json", dest="sub_json", action="store_true", help="以 JSON 格式输出")

    parser = argparse.ArgumentParser(
        prog="xhs-cli",
        description="小红书 Web API 命令行工具 (基于 XHSClient)",
        parents=[common_main],
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    p = sub.add_parser("set-cookie", help="追加一个 Cookie 到配置文件(可多次, 多账号轮询)")
    p.add_argument("cookie_value", metavar="COOKIE", help='Cookie 字符串, 如 a1=...; web_session=...')
    p.set_defaults(func=cmd_set_cookie)

    p = sub.add_parser("cookie", help="管理多账号 cookie: list / remove / clear")
    p.add_argument("action", choices=["list", "remove", "clear"], help="要执行的操作")
    p.add_argument("index", nargs="?", type=int, help="remove 时指定序号(1-based)")
    p.set_defaults(func=cmd_cookie)

    p = sub.add_parser("whoami", parents=[common_sub], help="当前登录账号信息")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("homefeed", parents=[common_sub], help="首页推荐流")
    p.add_argument("--count", type=int, default=20, help="拉取条数(默认 20)")
    p.set_defaults(func=cmd_homefeed)

    p = sub.add_parser("search", parents=[common_sub], help="搜索笔记")
    p.add_argument("keyword", help="搜索关键词")
    p.add_argument("--page-size", type=int, default=20, help="每页条数(默认 20)")
    p.add_argument("--limit", type=int, default=20, help="最多返回条数(默认 20, 0=不限翻完所有页)")
    p.add_argument("--sort", default="general", help='排序: general/time_descending(默认 general)')
    p.add_argument("--note-type", type=int, default=0, help="笔记类型: 0=综合 1=视频 2=图文(默认 0)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("detail", parents=[common_sub], help="笔记详情(需要 xsec_token)")
    p.add_argument("note", help="笔记 id 或小红书链接(自动提取 xsec_token)")
    p.add_argument("--xsec-token", help="xsec_token(传链接时可省略)")
    p.add_argument("--images", action="store_true", help="列出图片链接(WB_DFT 默认场景图)")
    p.set_defaults(func=cmd_detail)

    p = sub.add_parser("comments", parents=[common_sub], help="笔记评论(需要 xsec_token)")
    p.add_argument("note", help="笔记 id 或小红书链接")
    p.add_argument("--xsec-token", help="xsec_token(传链接时可省略)")
    p.add_argument("--no-sub", action="store_true", help="不展开折叠的回复")
    p.add_argument("--max-sub-pages", type=int, default=5, help="每条主评论最多展开页数(默认 5)")
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser("user", parents=[common_sub], help="用户信息 + 前 N 条笔记")
    p.add_argument("user_id", help="用户 user_id")
    p.add_argument("--notes", type=int, default=0, metavar="N", help="同时拉前 N 条笔记(默认 0 不拉)")
    p.set_defaults(func=cmd_user)

    p = sub.add_parser("user-notes", parents=[common_sub], help="用户发布的笔记")
    p.add_argument("user_id", help="用户 user_id")
    p.add_argument("--count", type=int, default=30, help="拉取条数(默认 30)")
    p.set_defaults(func=cmd_user_notes)

    return parser


def _merge_common(args: argparse.Namespace) -> None:
    """合并主 parser 与子 parser 解析到的公共选项(子命令后优先)。"""
    if getattr(args, "sub_cookie", None):
        args.cookie = args.sub_cookie
    if getattr(args, "sub_cookie_file", None):
        args.cookie_file = args.sub_cookie_file
    if getattr(args, "sub_cookie_api", None):
        args.cookie_api = args.sub_cookie_api
    if getattr(args, "sub_cookie_api_auth", None):
        args.cookie_api_auth = args.sub_cookie_api_auth
    if getattr(args, "sub_json", False):
        args.json = True


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _merge_common(args)

    # set-cookie / cookie 管理命令不需要 client
    if args.cmd in ("set-cookie", "cookie"):
        return args.func(args)

    try:
        cookies, on_invalid = _resolve_cookie(args)
        if not cookies:
            raise SystemExit("cookie 为空")
        client = _build_client(cookies, on_cookie_invalid=on_invalid)
        args.func(args, client)
    except KeyboardInterrupt:
        print("(中断)", file=sys.stderr)
        return 130
    except Exception as e:
        # XHSVerifyError / AllCookiesInvalidError 不带入顶层 import(保持 cli 无 httpx 依赖), 用类名判断
        if type(e).__name__ == "AllCookiesInvalidError":
            print("❌ 所有账号的 cookie 均已失效(登录已过期)", file=sys.stderr)
            print("   请用 xhs-cli set-cookie '<新cookie>' 添加有效账号", file=sys.stderr)
            return 1
        if type(e).__name__ == "XHSVerifyError":
            print(f"⚠️ 触发小红书验证码风控: {e}", file=sys.stderr)
            print("   请刷新 Cookie 后重试 (xhs-cli set-cookie '<新cookie>')", file=sys.stderr)
            return 1
        raise
    return 0



if __name__ == "__main__":
    sys.exit(main())
