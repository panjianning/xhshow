import sys
import os

# Insert src directory into path if it exists
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from xhshow import Xhshow
import requests
import json

cookie_str = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"

cookies = {}
for item in cookie_str.split("; "):
    if "=" in item:
        k, v = item.split("=", 1)
        cookies[k] = v

client = Xhshow()

# 试着请求主页推荐 feed，这样通常能取到实际数据
uri = "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed"
payload = {
    "cursor_score": "",
    "num": 20,
    "refresh_type": 1,
    "note_index": 0,
    "unread_begin_note_id": "",
    "unread_end_note_id": "",
    "unread_note_count": 0,
    "category": "homefeed_recommend"
}

# x_rap=True 对于 feed 等接口是必需的
headers = client.sign_headers_post(
    uri=uri,
    cookies=cookies,
    payload=payload,
    x_rap=True
)

res = requests.post(
    uri,
    json=payload,
    headers={**headers, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
    cookies=cookies,
)

print(f"Status Code: {res.status_code}")
try:
    data = res.json()
    print("Success:", data.get("success"))
    if data.get("data") and data["data"].get("items"):
        items = data["data"]["items"]
        print(f"\n成功获取到了 {len(items)} 条推荐笔记：")
        for i, item in enumerate(items[:5]):  # 打印前5条
            print(f"{i+1}. {item.get('note_card', {}).get('display_title', 'No Title')} (作者: {item.get('note_card', {}).get('user', {}).get('nickname', 'Unknown')})")
    else:
        print("\n返回了数据，但可能没有笔记:", json.dumps(data, indent=2, ensure_ascii=False)[:1000])
except Exception:
    print("Response:")
    print(res.text[:1000])
