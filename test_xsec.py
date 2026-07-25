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

def req_wrapper(method, uri, **kwargs):
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
    ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    res = req_func(uri, headers={**headers, 'User-Agent': ua}, cookies=cookies, **kwargs)
    return res.json()

# 1. 获取首页 Feed 用于拿到 note_id 和 xsec_token
homefeed_payload = {"cursor_score": "", "num": 5, "refresh_type": 1, "note_index": 0, "unread_begin_note_id": "", "unread_end_note_id": "", "unread_note_count": 0, "category": "homefeed_recommend"}
feed_data = req_wrapper("POST", "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed", json=homefeed_payload, x_rap=True)

if feed_data and feed_data.get("data") and feed_data["data"].get("items"):
    item = feed_data["data"]["items"][0]
    note_id = item.get("id")
    xsec_token = item.get("xsec_token")
    
    print(f"找到笔记 ID: {note_id}")
    print(f"找到 xsec_token: {xsec_token}")
    
    if note_id and xsec_token:
        time.sleep(1)
        # 尝试带上 xsec_token 和 xsec_source 请求详情
        detail_payload = {
            "source_note_id": note_id,
            "xsec_token": xsec_token,
            "xsec_source": "pc_feed"
        }
        detail_data = req_wrapper("POST", "https://edith.xiaohongshu.com/api/sns/web/v1/feed", json=detail_payload, x_rap=True)
        print("\n笔记详情带 xsec_token 请求结果:")
        print(json.dumps({"Code": detail_data.get("code"), "Msg": detail_data.get("msg"), "Success": detail_data.get("success")}, indent=2, ensure_ascii=False))
        
        # 尝试带上 xsec_token 请求评论区
        time.sleep(1)
        comment_params = {
            "note_id": note_id,
            "cursor": "",
            "xsec_token": xsec_token
        }
        comment_data = req_wrapper("GET", "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page", params=comment_params)
        print("\n笔记评论带 xsec_token 请求结果:")
        print(json.dumps({"Code": comment_data.get("code"), "Msg": comment_data.get("msg"), "Success": comment_data.get("success")}, indent=2, ensure_ascii=False))

