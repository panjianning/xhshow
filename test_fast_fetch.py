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
ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

note_id = "6a5f5d7a000000001b01f986"
xsec_token = "ABf6G1ssq_0_QtIRWlINCIX09U8dMQdRfUC-vEAdNqmyo="

all_comments = []

uri = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
params = {
    "note_id": note_id,
    "cursor": "",
    "xsec_token": xsec_token
}

headers = client.sign_headers_get(uri=uri, cookies=cookies, params=params)

try:
    res = requests.get(uri, headers={**headers, 'User-Agent': ua}, cookies=cookies, params=params, timeout=10)
    data = res.json()
    
    if not data.get("success"):
        print(f"请求失败: {json.dumps(data, ensure_ascii=False)}")
    else:
        comments = data.get("data", {}).get("comments", [])
        print(f"成功获取第一页，共 {len(comments)} 条顶级评论。")
        for i, c in enumerate(comments):
            user_info = c.get("user_info", {})
            nickname = user_info.get("nickname", "未知")
            content = c.get("content", "")
            like_count = c.get("like_count", 0)
            
            print(f"[{i+1}] {nickname}: {content} (👍 {like_count})")
            
            sub_comments = c.get("sub_comments", [])
            for j, sc in enumerate(sub_comments):
                sc_user = sc.get("user_info", {}).get("nickname", "未知")
                sc_content = sc.get("content", "")
                print(f"    ↳ [{i+1}.{j+1}] {sc_user}: {sc_content} (👍 {sc.get('like_count', 0)})")
except Exception as e:
    print("发生错误:", e)
