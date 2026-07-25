import sys
import os
import requests
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from xhshow import Xhshow

cookie_str = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"

cookies = {}
for item in cookie_str.split("; "):
    if "=" in item:
        k, v = item.split("=", 1)
        cookies[k] = v

client = Xhshow()
results = {}

def req_wrapper(name, method, uri, **kwargs):
    headers_kwargs = {"uri": uri, "cookies": cookies}
    if method == "GET":
        headers_kwargs["params"] = kwargs.get("params", {})
        headers_func = client.sign_headers_get
        req_func = requests.get
    else:
        headers_kwargs["payload"] = kwargs.get("json", {})
        if "x_rap" in kwargs:
            headers_kwargs["x_rap"] = kwargs.pop("x_rap")
        headers_func = client.sign_headers_post
        req_func = requests.post

    headers = headers_func(**headers_kwargs)
    
    # 模拟真实浏览器UA
    ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    res = req_func(uri, headers={**headers, 'User-Agent': ua}, cookies=cookies, **kwargs)
    try:
        data = res.json()
        results[name] = {
            "HTTP状态": res.status_code, 
            "成功": data.get("success"), 
            "Code": data.get("code"),
            "Msg": data.get("msg", "")
        }
        return data
    except Exception as e:
        results[name] = {"HTTP状态": res.status_code, "错误": "解析异常", "响应": res.text[:200]}
        return None

# 1. 搜索笔记 (Search API - POST + x_rap)
search_payload = {
    "keyword": "猫咪",
    "page": 1,
    "page_size": 20,
    "search_id": client.get_search_id(),
    "sort": "general",
    "note_type": 0
}
req_wrapper("搜索笔记", "POST", "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes", json=search_payload, x_rap=True)
time.sleep(1)

# 2. 获取其他用户信息 (GET)
# 使用一个随机的或者已知的 user_id，比如小红书官方号等，这里随便填一个合法的 user_id
req_wrapper("查询用户信息", "GET", "https://edith.xiaohongshu.com/api/sns/web/v1/user/otherinfo", params={"target_user_id": "5ff1645e0000000001008400"})
time.sleep(1)

# 3. 获取首页 Feed 用于拿到真实的 note_id
homefeed_payload = {"cursor_score": "", "num": 5, "refresh_type": 1, "note_index": 0, "unread_begin_note_id": "", "unread_end_note_id": "", "unread_note_count": 0, "category": "homefeed_recommend"}
feed_data = req_wrapper("首页推荐Feed", "POST", "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed", json=homefeed_payload, x_rap=True)

note_id = None
if feed_data and feed_data.get("data") and feed_data["data"].get("items"):
    note_id = feed_data["data"]["items"][0].get("id")

if note_id:
    time.sleep(1)
    # 4. 笔记详情 (POST feed API + x_rap)
    req_wrapper("笔记详情", "POST", "https://edith.xiaohongshu.com/api/sns/web/v1/feed", json={"source_note_id": note_id}, x_rap=True)
    time.sleep(1)
    
    # 5. 笔记评论列表 (GET)
    req_wrapper("笔记评论区", "GET", "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page", params={"note_id": note_id, "cursor": ""})
else:
    results["笔记详情"] = {"错误": "未获取到 note_id，跳过"}
    results["笔记评论区"] = {"错误": "未获取到 note_id，跳过"}

print(json.dumps(results, indent=2, ensure_ascii=False))
