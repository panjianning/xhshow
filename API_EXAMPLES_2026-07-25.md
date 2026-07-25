# xhshow API 参考 & 已验证功能

> 小红书请求签名纯算库 v0.2.1。最后更新 2026-07-25。

---

## 一、已通过真实 API 验证的功能 ✅

下面每个接口都用你的 Cookie 跑通并返回了数据。

### 1. 首页推荐流 `homefeed`

```
POST https://edith.xiaohongshu.com/api/sns/web/v1/homefeed
```

```python
from xhshow import Xhshow
import requests

client = Xhshow()
headers = client.sign_headers_post(
    uri='/api/sns/web/v1/homefeed',
    cookies=cookie_str,
    payload={'num': 10, 'cursor_score': ''},
    x_rap=True,
)
resp = requests.post('https://edith.xiaohongshu.com/api/sns/web/v1/homefeed',
                     json={'num': 10, 'cursor_score': ''},
                     headers=headers, cookies=cookie_dict)
# → items[].note_card.display_title / user.nickname / interact_info.liked_count ...
```

### 2. 用户信息 `user/me`

```
GET https://edith.xiaohongshu.com/api/sns/web/v1/user/me
```

```python
headers = client.sign_headers_get(
    uri='/api/sns/web/v1/user/me',
    cookies=cookie_str,
    params={},
)
# → nickname, user_id, red_id, desc, images ...
```

### 3. 用户发布的笔记 `user_posted`

```
GET https://edith.xiaohongshu.com/api/sns/web/v1/user_posted
```

```python
headers = client.sign_headers_get(
    uri='/api/sns/web/v1/user_posted',
    cookies=cookie_str,
    params={'num': '30', 'cursor': '', 'user_id': '...'},
)
# → notes[].display_title / note_id / interact_info.liked_count ...
```

**注意**：这个接口需要 `sign_format="xyw"`（XYS_ 会 406）。

### 4. 搜索笔记 `search/notes` ⭐

```
POST https://so.xiaohongshu.com/api/sns/web/v2/search/notes
```

| 注意点 | 说明 |
|---|---|
| **Host** | `so.xiaohongshu.com`（不是 edith！） |
| **版本** | `v2`（不是 v1） |
| **分页** | `page` 参数，返回 `data.has_more` |

```python
search_id = client.get_search_id()
headers = client.sign_headers_post(
    uri='/api/sns/web/v2/search/notes',
    cookies=cookie_str,
    payload={
        'keyword': '美食', 'page': 1, 'page_size': 20,
        'search_id': search_id, 'sort': 'general', 'note_type': 0,
        'source': 'web_search_result_notes',
    },
    x_rap=True,
)
resp = requests.post('https://so.xiaohongshu.com/api/sns/web/v2/search/notes',
                     json=payload, headers=headers, cookies=cookie_dict)
# → data.items[].note_card / data.has_more
```

实测：一次跑 50 页 1012 条，零封号。

### 5. 笔记详情 `feed`（单篇）

```
POST https://edith.xiaohongshu.com/api/sns/web/v1/feed
```

```python
headers = client.sign_headers_post(
    uri='/api/sns/web/v1/feed',
    cookies=cookie_str,
    payload={'source_note_id': note_id, 'xsec_token': token},
    x_rap=True,
)
# → items[0].note_card（标题、正文、图片、互动数据、标签等）
```

⚠️ **`xsec_token` 必须传**，否则返回 `code: 300031`（当前笔记暂时无法浏览）。token 从搜索结果的 `item.xsec_token` 获取。

### 6. 评论列表 `comment/page`

```
GET https://edith.xiaohongshu.com/api/sns/web/v2/comment/page
```

```python
headers = client.sign_headers_get(
    uri='/api/sns/web/v2/comment/page',
    cookies=cookie_str,
    params={'note_id': note_id, 'cursor': '', 'xsec_token': xsec_token},
)
resp = requests.get(
    'https://edith.xiaohongshu.com/api/sns/web/v2/comment/page',
    params=params, headers=headers, cookies=cookie_dict,
)
# → data.comments[] (user_info.nickname, content, like_count, sub_comments)
# → data.has_more / data.cursor (翻页用)
```

⚠️ **`xsec_token` 必须传**，从搜索结果 / homefeed 的 `item.xsec_token` 获取。

### 7. 子评论翻页（折叠回复展开）`comment/sub/page`

```
GET https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page
```

```python
# 当主评论 sub_comment_has_more=True 时，用 sub_comment_cursor 翻页拉取
headers = client.sign_headers_get(
    uri='/api/sns/web/v2/comment/sub/page',
    cookies=cookie_str,
    params={
        'note_id': note_id,
        'root_comment_id': root_comment_id,
        'num': 10,
        'cursor': sub_comment_cursor,
        'xsec_token': xsec_token,
    },
)
resp = requests.get(
    'https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page',
    params=params, headers=headers, cookies=cookie_dict,
)
# → data.comments[] / data.has_more / data.cursor
```

### 8. x-rap-param 风控头

```python
headers = client.sign_headers_post(..., x_rap=True)
# → headers 中自动包含 'x-rap-param'
```

搜索、feed、笔记详情接口都需要。

---

## 二、已跑通但未验证真实 API 的功能

### sign_xyw（XYW_ 签名格式）

```python
xyw = client.sign_xyw('GET', '/api/sns/web/v1/user_posted', a1_value, xsec_appid, {'num': '30'})
# → "XYW_eyJzaWduU3ZuIjoiNTYi..."
```

用于部分数据接口（user_posted 等），替代 XYS_ 避免 406。

### SessionManager

```python
session = SessionManager()
headers = client.sign_headers_get(..., session=session)
```

维护固定时间戳 + 单调递增计数器，模拟真实用户连续浏览。

### 解密

```python
client.decode_xs('XYS_...')   # → {'x0': '4.3.5', 'x4': 'object', ...}
client.decode_x3('mns0301_...')  # → bytearray
```

### CryptoConfig 自定义

```python
config = CryptoConfig().with_overrides(X3_PREFIX='custom_', SEQUENCE_VALUE_MIN=10)
client = Xhshow(config=config)
```

---

## 三、尚不支持 / 受限 ❌

| 功能 | 状态 | 原因 |
|---|---|---|
| **登录** | ❌ | 登录接口被网关保护 + 需滑块验证码 |
| **发布笔记** | ❌ | 未测试，需上传图片 + 风控校验 |
| **用户搜索** | ❌ | 未定位到端点 |

---

## 四、Headers 字段说明

| Header | 方法 | 说明 |
|---|---|---|
| `x-s` | `sign_headers_get/post` | 核心签名（XYS_ 或 XYW_ 格式） |
| `x-s-common` | 自动 | Cookie 签名 |
| `x-t` | `get_x_t()` | 毫秒时间戳 |
| `x-b3-traceid` | `get_b3_trace_id()` | 16 位 hex |
| `x-xray-traceid` | `get_xray_trace_id()` | 32 位 hex |
| `x-mns` | 固定 `"unload"` | - |
| `xy-direction` | `get_sharding_key(user_id)` | 用户分片值 |
| `x-rap-param` | `x_rap=True` | 风控头 |

---

## 五、关键常量 / 方法速查

```python
# Cookie 生成（自产账号）
Xhshow.generate_a1()                    # 52 位 a1
Xhshow.generate_web_id(a1)              # 32 位 hex web_id

# 搜索辅助
client.get_search_id()                  # base36
client.get_search_request_id()          # "{random}-{ts_ms}"

# URL 工具
client.build_url(base, params)          # 构建带参数 URL
client.build_json_body(payload)         # 紧凑 JSON

# 时间戳
client.get_x_t(timestamp=ts)            # 毫秒
client.get_b3_trace_id()
client.get_xray_trace_id(timestamp=ms)
```

---

## 六、签名算法详解

> 每次请求小红书 API 需要生成 8 个请求头，由 4 条独立算法链路生成。

### 架构总览

```
sign_headers_get/post()
├── 1. x-s          → sign_xs() 或 sign_xyw()      【核心签名】
├── 2. x-s-common   → sign_xs_common()              【Cookie + 指纹签名】
├── 3. x-rap-param  → x_rap_param()  (可选)         【风控头】
└── 4. 辅助头        → x-t / x-b3 / x-xray / xy-direction / x-mns
```

---

### 6.1 `x-s` — 核心签名

有两种格式，通过 `sign_format` 参数切换：

#### XYS_ 格式（默认，`sign_xs`）

```
输入: URI + 请求参数/body
         │
         ▼
  拼接成 content_string
  GET:  /path?k=v&...
  POST: /path + JSON body (紧凑格式)
         │
         ▼
  d_value = MD5(content_string)
  m_value = MD5(path)              ← 仅 POST，GET 时 m = d
         │
         ▼
  build_payload_array(d, m, a1, xsec_appid, content_string, timestamp)
  → 生成 144 字节 payload 数组
         │
    ┌────┴──────────────────────────────────────┐
    │ 结构 (144 字节):                            │
    │  [0:4]    版本头 = [121, 104, 96, 41]      │
    │  [4:8]    随机种子 (u32 LE)                 │
    │  [8:16]   毫秒时间戳 (u64 LE)               │
    │  [16:24]  页面加载时间 (带随机偏移 10-50s)   │
    │  [24:28]  sequence_value (随机 15-50)       │
    │  [28:32]  window_props_length (随机 1k-1.2k)│
    │  [32:36]  uri_length (UTF-8 字节数)         │
    │  [36:44]  MD5 前 8 字节 XOR 种子字节        │
    │  [44:97]  a1 cookie (52B + 长度头)          │
    │  [97:108] app_id = "xhs-pc-web" (10B+长度头)│
    │  [108:124] 环境指纹 (env_table XOR checks)  │
    │  [124:144] a3 = custom_hash_v2(ts+MD5) + 前缀│
    └──────────────────────────────────────────┘
         │
         ▼
  xor_transform_array(payload)     ← 与固定 144 字节 HEX_KEY 做 XOR
         │
         ▼
  encode_x3(payload[:144])         ← 自定义 X3 Base64 编码
         │
         ▼
  包装成 JSON:
  {"x0":"4.3.5", "x1":"xhs-pc-web", "x2":"Windows",
   "x3":"mns0301_...", "x4":"object"}
         │
         ▼
  Base64 编码 → 前缀 "XYS_" →  最终 x-s
```

#### XYW_ 格式（`sign_xyw`，数据接口用）

XYS_ 被 406 拒绝的接口（如 `user_posted`）需要切到此格式：

```
输入: URI + a1 + timestamp_ms
         │
         ▼
  x1 = MD5("url=" + full_uri)
  message = "x1={x1};x2={env_flags};x3={a1};x4={ts_ms};"
         │
         ▼
  PKCS7 填充 → AES-128-CBC 加密
  key = "7cc4adla5ay0701v" (16B)
  iv  = "4uzjr7mbsibcaldp" (16B)
         │
         ▼
  hex 编码 → 包装:
  {"signSvn":"56", "signType":"x2", "appId":"xhs-pc-web",
   "signVersion":"1", "payload":"<hex>"}
         │
         ▼
  Base64 编码 → 前缀 "XYW_"
```

---

### 6.2 `x-s-common` — Cookie + 浏览器指纹签名

```
输入: cookies (必须有 a1)
         │
         ▼
  生成浏览器指纹:
    fingerprint = generate(cookies, user_agent)  ← 模拟浏览器环境
    b1 = generate_b1(fingerprint)                ← AES + Base64 + B1_SECRET_KEY
         │
         ▼
  组装签名 JSON:
  {
    "s0": 3,           ← 协议版本
    "x0": "1",
    "x1": "4.3.7",     ← SDK 版本
    "x2": "Mac OS",    ← 操作系统
    "x3": "xhs-pc-web",← 应用标识
    "x4": "6.34.5",    ← webBuild 版本
    "x5": "<a1>",      ← a1 cookie 原文
    "x8": "<b1>",      ← 加密指纹
    "x9": CRC32(b1),   ← 指纹 CRC32 校验
    "x10": 0,
    "x11": "normal",
    "x12": ""          ← 可选 dsllt;tiga 安全运行时状态
  }
         │
         ▼
  Base64 编码 → x-s-common
```

---

### 6.3 `x-rap-param` — 风控头

feed、搜索、笔记详情等接口必需，算法最为复杂：

```
输入: API 路径 + 请求 body
         │
         ▼
  构建 30+ 字段的 TLV 结构体:
    - 时间戳 (tag 1000, u64)
    - 随机 nonce (tag 1001, u32)
    - 16B session key → SM4 加密后嵌入 (tag 1002)
    - XXH32(api + json_body) 哈希 (tag 1003)
    - 能力标志位 × 20+ (布尔, tags 1051-1074)
    - 运行计时 (tags 1075-1077)
    - interaction_trace 字节块 (tag 1078)
    - environment_snapshot 字节块 (tag 1088)
         │
         ▼
  后 128 字节做 XOR 混淆 (单字节 mask, 随机 1-255)
         │
         ▼
  Gzip 压缩 (OS 字节改为 0x03 模拟浏览器)
         │
         ▼
  循环 XOR 16B encrypt_key
         │
         ▼
  SM4 变体加密 (自定义 S-box + 10 轮预计算轮密钥)
         │
         ▼
  包装 envelope:
    [header 40B] + [salt] + [encrypted_session_key] + [ciphertext] + [XXH32 校验]
         │
         ▼
  Base64 编码 → x-rap-param
```

**关键常量：**
- 协议版本: `sdk_version = 10300`
- encrypt_key: 随机 16B ASCII（可固定）
- session_key: 随机 16B ASCII（可固定）
- gzip level: 6

---

### 6.4 辅助头

| Header | 生成方式 |
|--------|----------|
| `x-t` | `int(time.time() * 1000)` — 毫秒时间戳 |
| `x-b3-traceid` | 16 位随机 hex |
| `x-xray-traceid` | 32 位 hex，前 16 位 = 时间戳(ms) + 序列号(23bit) 混合 |
| `xy-direction` | `MurmurHash3(user_id) % 100`；无 user_id 则随机 0-99 |
| `x-mns` | 固定 `"unload"` |

---

### 6.5 各接口所需 Headers 速查

| 接口 | sign_format | x_rap | xsec_token |
|------|:-----------:|:-----:|:----------:|
| homefeed | xys (默认) | ✅ | ❌ |
| user/me | xys | ❌ | ❌ |
| user_posted | **xyw** | ❌ | ❌ |
| search/notes | xys | ✅ | ❌ |
| feed (笔记详情) | xys | ✅ | ✅ |
| comment/page | xys | ❌ | ✅ |
| comment/sub/page | xys | ❌ | ✅ |

---

## 七、已知 API 端点汇总

| 功能 | Method | Host | Path | x_rap |
|---|---|---|---|---|
| 首页推荐 | POST | edith | `/api/sns/web/v1/homefeed` | ✅ |
| 用户信息 | GET | edith | `/api/sns/web/v1/user/me` | ❌ |
| 用户笔记 | GET | edith | `/api/sns/web/v1/user_posted` | ❌ |
| 搜索笔记 | POST | **so** | `/api/sns/web/v2/search/notes` | ✅ |
| 笔记详情 | POST | edith | `/api/sns/web/v1/feed` | ✅ |
| 评论列表 | GET | edith | `/api/sns/web/v2/comment/page` | ❌ (需 xsec_token) |
| 子评论 | GET | edith | `/api/sns/web/v2/comment/sub/page` | ❌ (需 xsec_token) |
| 搜索筛选 | GET | edith | `/api/sns/web/v1/search/filter` | ❌ |
| 搜索推荐 | GET | edith | `/api/sns/web/v1/search/recommend` | ❌ |
