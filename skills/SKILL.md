---
name: xhs-cli
description: 拉取小红书数据的命令行工具与 Python 库（搜索/笔记详情/评论/用户笔记/首页推荐）。当用户需要获取小红书笔记内容、图片链接、评论数据，或要求使用 xhs-cli / xhshow 时使用本 skill。
---

# xhs-cli — 小红书数据拉取工具

基于 xhshow 签名库的命令行工具与 Python 客户端。核心能力：

- **笔记详情 / 评论 / 搜索 / 用户笔记 / 首页推荐**一条命令搞定
- **多账号 round-robin** 轮询，cookie 失效自动剔除换号
- 笔记链接自动提取 `xsec_token`，支持 `--json` 输出

## 1. 安装

从 GitHub 直接安装（未发布 PyPI，**不要** `pip install xhshow`，那是上游包没有 CLI）：

```bash
# 带 xhs-cli 命令行工具（推荐）
pip install "git+https://github.com/panjianning/xhshow.git[cli]"

# SSH 方式
pip install "git+ssh://git@github.com/panjianning/xhshow.git[cli]"

# 仅签名库（不含 CLI）
pip install "git+https://github.com/panjianning/xhshow.git"
```

开发模式（本仓库内）：

```bash
uv sync --extra cli --extra dev
# 本地开发时命令直接可用: .venv/bin/xhs-cli ... 或 python -m xhshow.cli ...
```

## 2. 配置 Cookie（必须先做）

Cookie 从浏览器登录小红书后复制（F12 → Application → Cookies），必须包含 `a1`、`web_session`。

```bash
# 添加账号（可多次执行 = 多账号，请求自动轮询）
xhs-cli set-cookie "a1=xxx; web_session=yyy; webId=zzz; ..."

# 管理
xhs-cli cookie list          # 列出（脱敏）
xhs-cli cookie remove 2      # 删除第 2 个账号
xhs-cli cookie clear         # 清空

# 验证 cookie 是否有效
xhs-cli whoami
```

- 存储位置：`~/.xhs-cli/cookie`，**每行一个 cookie = 一个账号**（环境变量 `XHS_COOKIE_FILE` 可覆盖）
- 临时指定：`--cookie "<str>"` / `--cookie-file <path>` / 环境变量 `XHS_COOKIE`，优先级高于配置文件
- **失效自动处理**：请求返回 `code=-100`（登录已过期）时自动从配置文件剔除该账号、换下一个有效账号重试；全部失效报错 `❌ 所有账号的 cookie 均已失效`（exit 1），此时需重新 `set-cookie`

## 3. 命令参考

| 命令 | 说明 |
|---|---|
| `xhs-cli set-cookie "<cookie>"` | 追加一个账号 |
| `xhs-cli cookie list` / `remove <n>` / `clear` | 管理多账号 |
| `xhs-cli whoami` | 当前账号信息（验证 cookie） |
| `xhs-cli homefeed [--count N]` | 首页推荐流 |
| `xhs-cli search <关键词> [--limit N] [--page-size N] [--sort S] [--note-type T]` | 搜索笔记（S: general/time_descending；T: 0综合/1视频/2图文） |
| `xhs-cli detail <链接或ID> [--xsec-token T] [--images]` | 笔记详情（标题/正文/互动/标签） |
| `xhs-cli comments <链接或ID> [--xsec-token T] [--no-sub] [--max-sub-pages N]` | 评论（含楼中楼展开） |
| `xhs-cli user <user_id> [--notes N]` | 用户信息 + 前 N 条笔记 |
| `xhs-cli user-notes <user_id> [--count N]` | 用户发布的笔记 |

全局选项（放命令前或后均可）：

- `--json`：JSON 输出原始数据（请求日志走 stderr，不污染 stdout）
- `--cookie` / `--cookie-file`：临时 cookie

## 4. 关键机制：xsec_token

小红书详情/评论接口必须带 `xsec_token`，否则返回 `code=300031`（当前笔记暂时无法浏览）。token 只能从**列表接口**（搜索/推荐/用户笔记）的返回里拿。

**最简单的方式：直接传完整链接**，CLI 自动解析出 `note_id` + `xsec_token`（支持 `/explore/{id}`、`/discovery/item/{id}`、`xhslink.com` 短链）：

```bash
xhs-cli detail "https://www.xiaohongshu.com/explore/6a12fb9b000000003701ceca?xsec_token=AB2tBfZ...&xsec_source=pc_feed"
```

只有裸 note_id 时必须手动补 token：`xhs-cli detail <note_id> --xsec-token <token>`。

## 5. 实战示例

### 5.1 搜索 → 详情 → 评论 全链路

```bash
# 1) 搜索（输出自带 xsec_token）
xhs-cli search "咖啡" --limit 3
#   1. ☕️咖啡明明不好喝...   ❤️52 💬30
#       id=6a12fb9b000000003701ceca
#       xsec_token=AB2tBfZ81JYTvCyYUtVohq6ucGS-6fF7UDuHbOYIaaycs=

# 2) 详情（链接带 token 直接传）
xhs-cli detail "https://www.xiaohongshu.com/explore/6a12fb9b000000003701ceca?xsec_token=AB2tBfZ81JYTvCyYUtVohq6ucGS-6fF7UDuHbOYIaaycs="

# 3) 评论（含楼中楼）
xhs-cli comments "https://www.xiaohongshu.com/explore/6a12fb9b000000003701ceca?xsec_token=AB2tBfZ81JYTvCyYUtVohq6ucGS-6fF7UDuHbOYIaaycs="
```

### 5.2 笔记详情 + 图片链接下载

```bash
xhs-cli detail "<链接>" --images
#   图片   : 3 张   类型: normal
#   图片链接:
#     [1] https://sns-na-i1.xhscdn.com/19bdbc5a-...?sign=...
#     [2] https://sns-na-i1.xhscdn.com/notes_pre_post/...?sign=...

# 批量下载图片
xhs-cli --json detail "<链接>" | jq -r '.image_list[] | .url' | xargs -I{} curl -sO {}
```

### 5.3 JSON 输出做二次处理

```bash
# 提取标题+点赞，存 CSV
xhs-cli --json search "咖啡" --limit 20 \
  | jq -r '.[] | [.note_id, .title, .liked_count] | @csv' > notes.csv

# 只看正文
xhs-cli --json detail "<链接>" | jq -r '.desc'
```

### 5.4 Python 库调用（需要编程式使用时）

```python
from xhshow import XHSClient

client = XHSClient(["cookie_1", "cookie_2"])   # 多账号轮询

# 搜索 → 详情 → 评论
notes = list(client.search_notes("咖啡"))       # 返回 NoteItem 列表
note = notes[0]                                 # 自带 xsec_token
detail = client.get_note_detail(note)           # note_card dict: title/desc/image_list/interact_info
for c in client.get_comments(note):             # CommentItem: user/content/like_count/sub_comments
    print(c.user, c.content)

# 异步
import asyncio
async def main():
    client = XHSClient("cookie")
    for n in await client.homefeed_async(count=10):
        print(n.title)
asyncio.run(main())
```

NoteItem 常用字段：`note_id`、`title`、`desc`、`author`、`author_id`、`liked_count`、`collected_count`、`comment_count`、`xsec_token`、`image_urls`、`posted_at`。

## 6. 注意事项

- **限速**：内置 1.2 秒/请求（所有账号共享），大量拉取请耐心等待，勿自行并发
- **风控**：HTTP 461 = 触发验证码，CLI 会提示刷新 cookie；连续大量请求易触发，适度使用
- **图片链接有时效**：CDN 链接带 `sign`/`t` 参数，过期后失效，需要时再拉取
- **user_posted 接口登录校验较严**：`user`/`user-notes` 命令要求 cookie 登录态有效，过期会返回"登录已过期"（会被自动剔除换号）
- Cookie 是敏感凭据：配置文件权限 600，勿提交到代码库
