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

# 1. 验证翻页
print("--- 1. 验证翻页功能 ---")
uri_page = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
params_page1 = {"note_id": note_id, "cursor": "", "xsec_token": xsec_token}
headers_page1 = client.sign_headers_get(uri=uri_page, cookies=cookies, params=params_page1)
res_page1 = requests.get(uri_page, headers={**headers_page1, 'User-Agent': ua}, cookies=cookies, params=params_page1).json()

cursor_p1 = res_page1.get("data", {}).get("cursor", "")
has_more_p1 = res_page1.get("data", {}).get("has_more", False)
print(f"第一页抓取完毕，获取了 {len(res_page1.get('data', {}).get('comments', []))} 条评论。是否有下一页: {has_more_p1}, 下一页Cursor: {cursor_p1}")

if has_more_p1:
    time.sleep(1)
    params_page2 = {"note_id": note_id, "cursor": cursor_p1, "xsec_token": xsec_token}
    headers_page2 = client.sign_headers_get(uri=uri_page, cookies=cookies, params=params_page2)
    res_page2 = requests.get(uri_page, headers={**headers_page2, 'User-Agent': ua}, cookies=cookies, params=params_page2).json()
    print(f"第二页抓取完毕，获取了 {len(res_page2.get('data', {}).get('comments', []))} 条评论。")

# 2. 验证二级评论抓取
print("\n--- 2. 验证二级评论完整抓取 ---")
# 寻找一个有更多二级评论的根评论
root_comment_id = None
sub_comment_cursor = ""
for c in res_page1.get("data", {}).get("comments", []):
    if c.get("sub_comment_has_more"):
        root_comment_id = c.get("id")
        sub_comment_cursor = c.get("sub_comment_cursor", "")
        print(f"找到含有较多二级评论的主评论：{c.get('user_info', {}).get('nickname')} -> '{c.get('content')}'")
        print(f"主评论预览里仅包含 {len(c.get('sub_comments', []))} 条回复，更多回复的 cursor={sub_comment_cursor}")
        break

if root_comment_id:
    uri_sub = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page"
    # 小红书二级评论接口参数一般是 note_id, root_comment_id, num, cursor
    params_sub = {
        "note_id": note_id,
        "root_comment_id": root_comment_id,
        "num": 10,
        "cursor": sub_comment_cursor,
        "xsec_token": xsec_token
    }
    time.sleep(1)
    headers_sub = client.sign_headers_get(uri=uri_sub, cookies=cookies, params=params_sub)
    res_sub = requests.get(uri_sub, headers={**headers_sub, 'User-Agent': ua}, cookies=cookies, params=params_sub).json()
    
    sub_data = res_sub.get("data", {})
    sub_comments = sub_data.get("comments", [])
    print(f"\n成功调用二级评论接口，拉取到了 {len(sub_comments)} 条额外的二级回复！展示前 3 条：")
    for i, sc in enumerate(sub_comments[:3]):
        print(f"  ↳ {sc.get('user_info', {}).get('nickname')}: {sc.get('content')}")
else:
    print("当前第一页的评论中没有折叠的超长二级评论。")
