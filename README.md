# xhshow

<div align="center">

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/xhshow/)
[![License](https://img.shields.io/github/license/panjianning/xhshow.svg)](https://github.com/panjianning/xhshow/blob/main/LICENSE)

小红书请求签名生成库 + 开箱即用的命令行工具 `xhs-cli`

生成 `x-s`、`x-s-common`、`x-rap-param` 等请求头；CLI 直接拉取首页推荐、搜索、笔记详情、评论，支持多账号轮询与 cookie 失效自动切换。

</div>

## 亮点

- **`xhs-cli` 命令行工具**：一条命令拉首页推荐 / 搜索 / 笔记详情 / 评论 / 用户主页
- **多账号 round-robin**：配置文件里每行一个 cookie = 一个账号，自动轮询分摊风控
- **cookie 失效自动处理**：检测到登录过期自动剔除该账号、换下一个有效账号；全部失效给出明确报错
- **细节友好**：`--json` 输出、链接自动提取 `xsec_token`、`xhs-cli set-cookie` 一条命令配好

---

## 安装

从 GitHub 直接安装（无需发布 PyPI）：

```bash
# 仅签名库
pip install "git+https://github.com/panjianning/xhshow.git"

# 带 xhs-cli 命令行工具（推荐）
pip install "git+https://github.com/panjianning/xhshow.git[cli]"
```

SSH 方式：

```bash
pip install "git+ssh://git@github.com/panjianning/xhshow.git[cli]"
```

从源码安装（开发）：

```bash
git clone https://github.com/panjianning/xhshow && cd xhshow
uv sync --extra cli
```

---

## 🚀 xhs-cli 快速开始

### 1. 配置 Cookie

```bash
xhs-cli set-cookie "<cookie 字符串>"
```

- Cookie 保存在 `~/.xhs-cli/cookie`（可用环境变量 `XHS_COOKIE_FILE` 覆盖路径）
- **多账号**：再执行一次 `set-cookie` 即可追加，请求自动 round-robin 轮询

```bash
xhs-cli cookie list        # 列出已保存账号（脱敏显示）
xhs-cli cookie remove 2    # 删除第 2 个账号
xhs-cli cookie clear       # 清空所有
```

> 也可通过 `--cookie` / `--cookie-file` / 环境变量 `XHS_COOKIE` 临时指定，优先级高于配置文件。

### 2. 常用命令

```bash
xhs-cli whoami                                  # 当前账号信息（验证 cookie）
xhs-cli homefeed --count 10                     # 首页推荐
xhs-cli search "咖啡" --limit 5                 # 搜索笔记
xhs-cli detail "<小红书链接>"                   # 笔记详情（自动提取 xsec_token）
xhs-cli comments "<小红书链接>"                  # 笔记评论
xhs-cli user-notes <user_id> --count 30         # 用户发布的笔记
xhs-cli user <user_id> --notes 5                # 用户信息 + 前 5 条笔记
```

示例输出：

```
$ xhs-cli search "咖啡" --limit 2
  1. ☕️咖啡明明不好喝，为啥还有人愿意喝?             是小童妈妈呀  ❤️52 💬30 📅2026-05-24 21:22
      id=6a12fb9b000000003701ceca
      xsec_token=AB2tBfZ81JYTvCyYUtVohq6ucGS-6fF7UDuHbOYIaaycs=
  2. 咖啡这样选，热量真的差很多🔥                  阿徐热量研究所  ❤️164 💬2 📅2026-07-06 14:18
      id=6a4b48a3000000000702e08f
      xsec_token=ABd6BXpxICdUafFiGCwpsWWUqTAYARf1Emn_i1BvPThLo=
```

### 3. 关键特性

#### 链接直接传，xsec_token 自动提取

`detail` / `comments` 支持传完整小红书链接（`/explore/{id}`、`/discovery/item/{id}`、`xhslink.com` 短链均可），自动解析出 `note_id` 与 `xsec_token`，无需手动复制：

```bash
xhs-cli detail "https://www.xiaohongshu.com/explore/6a12fb9b000000003701ceca?xsec_token=AB2tBfZ81JYTv...&xsec_source=pc_feed"
```

#### JSON 输出

所有命令支持 `--json` 输出原始数据（请求日志走 stderr，不污染 stdout）：

```bash
xhs-cli --json homefeed --count 5
xhs-cli search "咖啡" --json
```

`--cookie` / `--json` 放在命令前或命令后均可。

#### 多账号 & cookie 失效自动切换

配置多个账号后自动轮询；遇到"登录已过期"（code -100）时：

1. 提示并**自动从配置文件剔除**失效账号
2. **自动换下一个有效账号重试**当前请求
3. 全部账号失效则明确报错：`❌ 所有账号的 cookie 均已失效，请用 xhs-cli set-cookie '<新cookie>'`

### 4. 完整命令参考

| 命令 | 说明 |
|---|---|
| `xhs-cli set-cookie "<cookie>"` | 追加一个账号（可多次，round-robin） |
| `xhs-cli cookie list` / `remove <n>` / `clear` | 管理多账号 cookie（脱敏列出） |
| `xhs-cli whoami` | 当前登录账号信息 |
| `xhs-cli homefeed [--count N]` | 首页推荐流 |
| `xhs-cli search <关键词> [--page-size N] [--limit N] [--sort S] [--note-type T]` | 搜索笔记 |
| `xhs-cli detail <链接或ID> [--xsec-token T]` | 笔记详情（含正文/图片/互动/标签） |
| `xhs-cli comments <链接或ID> [--xsec-token T] [--no-sub] [--max-sub-pages N]` | 笔记评论（含楼中楼） |
| `xhs-cli user <user_id> [--notes N]` | 用户信息 + 前 N 条笔记 |
| `xhs-cli user-notes <user_id> [--count N]` | 用户发布的笔记 |

---

## Python 库用法

### 快速开始（签名）

```python
from xhshow import Xhshow
import requests

client = Xhshow()
cookies = {"a1": "...", "web_session": "...", "webId": "..."}

# uri 可传完整 URL 或 URI 路径，自动提取
headers = client.sign_headers_get(
    uri="https://edith.xiaohongshu.com/api/sns/web/v1/user_posted",
    cookies=cookies,
    params={"num": "30", "cursor": "", "user_id": "123"},
)

response = requests.get(
    "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted",
    params={"num": "30", "cursor": "", "user_id": "123"},
    headers=headers,
    cookies=cookies,
)
```

返回的 headers：

```python
{
    "x-s": "XYS_...",
    "x-s-common": "...",
    "x-t": "1234567890",
    "x-b3-traceid": "...",
    "x-xray-traceid": "...",
    "x-mns": "unload",
    "xy-direction": "42",
}
```

POST 请求使用 `sign_headers_post`，参数从 `params` 换成 `payload`：

```python
headers = client.sign_headers_post(
    uri="https://edith.xiaohongshu.com/api/sns/web/v1/login",
    cookies=cookies,
    payload={"username": "test", "password": "123456"},
)
```

### XHSClient（高级封装，同步/异步）

`XHSClient` 封装了签名、限速（1.2s/请求）、多账号轮询、cookie 自动刷新与失效处理。CLI 即基于它实现：

```python
from xhshow import XHSClient

client = XHSClient(["cookie_a", "cookie_b"])      # 多账号轮询

for note in client.search_notes("美食"):
    print(note.title, note.liked_count)

detail = client.get_note_detail(note)             # note 自带 xsec_token
for c in client.get_comments(note):
    print(c.user, c.content)
```

cookie 失效回调（登录过期时剔除账号并通知）：

```python
client = XHSClient(cookies, on_cookie_invalid=lambda c: print("失效账号:", c[:30]))
```

异步版本：`homefeed_async` / `search_notes_async` / `get_note_detail_async` / `get_comments_async` / `me_async`。

### x-rap-param

feed、搜索、笔记发布等接口需要额外的 `x-rap-param` 风控头。传入 `x_rap=True` 即可在签名 headers 中自动生成：

```python
headers = client.sign_headers_post(
    uri="https://edith.xiaohongshu.com/api/sns/web/v1/feed",
    cookies=cookies,
    payload={"source_note_id": "..."},
    x_rap=True,           # 生成 x-rap-param
    user_id="5ff...",     # 可选，用于计算 xy-direction 分片，省略则随机
)
```

- `x_rap`：是否生成 `x-rap-param`。算法基于请求 API 路径 + body 计算，GET/POST 均支持。
- `user_id`：传入则 `xy-direction` 由 user_id 经 MurmurHash3 算出，否则取随机值。

也可单独调用底层算法：

```python
from xhshow.core.xrap import x_rap_param

value = x_rap_param(
    "//edith.xiaohongshu.com/api/sns/web/v1/feed",
    {"source_note_id": "..."},
)
```

### 搜索与账号参数

```python
client.get_search_id()           # 搜索接口 search_id（base36）
client.get_search_request_id()   # 搜索接口 request_id："{random}-{ts_ms}"

Xhshow.generate_a1()             # 生成 a1 cookie（52 位）
Xhshow.generate_web_id(a1)       # 由 a1 生成 web_id（32 位 hex）
```

### 单独生成字段

```python
# x-s 签名（仅需 a1）
x_s = client.sign_xs_get(uri="/api/sns/web/v1/user_posted", a1_value="...", params={"num": "30"})
x_s = client.sign_xs_post(uri="/api/sns/web/v1/login", a1_value="...", payload={...})

# x-s-common（需完整 cookies，支持字典或字符串）
xs_common = client.sign_xsc(cookie_dict=cookies)

# 其他 headers 字段
x_t = client.get_x_t()                  # 毫秒时间戳
x_b3 = client.get_b3_trace_id()         # 16 位 trace id
x_xray = client.get_xray_trace_id()     # 32 位 trace id

# 统一时间戳（确保各字段时间一致）
import time
ts = time.time()
x_s = client.sign_xs_get(uri="...", a1_value="...", params={"num": "30"}, timestamp=ts)
x_t = client.get_x_t(timestamp=ts)
x_xray = client.get_xray_trace_id(timestamp=int(ts * 1000))
```

### 会话管理（实验性）

`SessionManager` 维护状态化签名参数（固定页面加载时间戳 + 单调递增计数器），模拟真实用户连续操作，可能提升长期稳定性。基于 [#86](https://github.com/Cloxl/xhshow/issues/86) 理论分析，实际效果待验证。

```python
from xhshow import Xhshow, SessionManager

client = Xhshow()
session = SessionManager()

headers = client.sign_headers_get(
    uri="/api/sns/web/v1/user_posted",
    cookies=cookies,
    params={"num": "30"},
    session=session,   # 同一 session 可跨多次请求复用
)
```

多账户时为每个账户创建独立 `SessionManager`，按账户匹配复用。

### 工具方法

```python
# 构建符合 xhs 平台的 GET 链接 / POST body
full_url = client.build_url(base_url="...", params={...})
json_body = client.build_json_body(payload={...})

# 解密
client.decode_x3("mns0101_...")   # 解密 x3 签名
client.decode_xs("XYS_...")       # 解密完整 XYS 签名
```

### 自定义配置

```python
from xhshow import CryptoConfig, Xhshow

config = CryptoConfig().with_overrides(
    X3_PREFIX="custom_",
    SEQUENCE_VALUE_MIN=20,
    SEQUENCE_VALUE_MAX=60,
)
client = Xhshow(config=config)
```

---

## 开发

```bash
# 安装 uv 后
git clone https://github.com/panjianning/xhshow && cd xhshow
uv sync --extra cli --extra dev

uv run pytest tests/ -v                                  # 测试
uv run ruff check src/ tests/ --ignore=UP036,E501        # 检查
uv run ruff format src/ tests/                           # 格式化
uv build                                                 # 构建
```

提交遵循 conventional commits 规范。

## 功能建议

如果您有任何功能建议或想法，欢迎在 [Issues](https://github.com/panjianning/xhshow/issues) 中提交。我们期待您的宝贵建议，共同打造更好的 xhshow！

## 社区

本项目分享于 [LINUX DO](https://linux.do) —— 真诚、友善、团结、专业的技术社区。欢迎来逛逛。

## License

[MIT](LICENSE)