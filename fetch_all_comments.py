import sys
import os
import requests
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from xhshow import Xhshow

# ================= 配置部分 =================
cookie_str = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"
cookies = {k: v for k, v in (item.split("=", 1) for item in cookie_str.split("; ") if "=" in item)}

client = Xhshow()
ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

note_id = "6a5f5d7a000000001b01f986"
xsec_token = "ABf6G1ssq_0_QtIRWlINCIX09U8dMQdRfUC-vEAdNqmyo="

MAX_MAIN_PAGES = 3
MAX_SUB_PAGES = 5

def log(msg):
    print(msg, flush=True)

def fetch_main_comments(cursor=""):
    uri = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
    params = {"note_id": note_id, "cursor": cursor, "xsec_token": xsec_token}
    headers = client.sign_headers_get(uri=uri, cookies=cookies, params=params)
    res = requests.get(uri, headers={**headers, 'User-Agent': ua}, cookies=cookies, params=params, timeout=30)
    return res.json()

def fetch_sub_comments(root_comment_id, cursor=""):
    uri = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/sub/page"
    params = {"note_id": note_id, "root_comment_id": root_comment_id, "num": 10, "cursor": cursor, "xsec_token": xsec_token}
    headers = client.sign_headers_get(uri=uri, cookies=cookies, params=params)
    res = requests.get(uri, headers={**headers, 'User-Agent': ua}, cookies=cookies, params=params, timeout=30)
    return res.json()

def scrape_all_comments():
    log(f"开始全量抓取笔记 {note_id} 的评论数据...")
    
    all_comments_data = []
    main_cursor = ""
    main_has_more = True
    main_page = 1
    
    while main_has_more and main_page <= MAX_MAIN_PAGES:
        log(f"[主评论] 正在抓取第 {main_page} 页...")
        res = fetch_main_comments(main_cursor)
        
        if not res.get("success"):
            log(f"获取主评论失败: {json.dumps(res, ensure_ascii=False)}")
            break
            
        data = res.get("data", {})
        comments = data.get("comments", [])
        log(f"  本页获取到 {len(comments)} 条评论")
        
        for c in comments:
            comment_item = {
                "id": c.get("id"),
                "user": c.get("user_info", {}).get("nickname"),
                "user_id": c.get("user_info", {}).get("user_id"),
                "content": c.get("content"),
                "like_count": c.get("like_count"),
                "create_time": c.get("create_time"),
                "sub_comments": []
            }
            
            if c.get("sub_comments"):
                for sc in c.get("sub_comments"):
                    comment_item["sub_comments"].append({
                        "id": sc.get("id"),
                        "user": sc.get("user_info", {}).get("nickname"),
                        "content": sc.get("content"),
                        "like_count": sc.get("like_count")
                    })
            
            sub_has_more = c.get("sub_comment_has_more", False)
            sub_cursor = c.get("sub_comment_cursor", "")
            sub_page = 1
            
            while sub_has_more and sub_page <= MAX_SUB_PAGES:
                log(f"    -> 展开 [{comment_item['user']}] 的回复 (第{sub_page}页)...")
                sub_res = fetch_sub_comments(c.get("id"), sub_cursor)
                
                if not sub_res.get("success"):
                    log(f"    获取二级评论失败: {sub_res}")
                    break
                    
                sub_data = sub_res.get("data", {})
                for sc in sub_data.get("comments", []):
                    comment_item["sub_comments"].append({
                        "id": sc.get("id"),
                        "user": sc.get("user_info", {}).get("nickname"),
                        "content": sc.get("content"),
                        "like_count": sc.get("like_count")
                    })
                
                sub_has_more = sub_data.get("has_more", False)
                sub_cursor = sub_data.get("cursor", "")
                sub_page += 1
                time.sleep(1.2)
                
            all_comments_data.append(comment_item)
            
        main_has_more = data.get("has_more", False)
        main_cursor = data.get("cursor", "")
        main_page += 1
        time.sleep(1.5)
        
    log(f"\n抓取完成！{len(all_comments_data)} 条主楼层。")
    total = sum(1 + len(c['sub_comments']) for c in all_comments_data)
    log(f"含二级评论共 {total} 条评论。")
    
    with open("all_comments.json", "w", encoding="utf-8") as f:
        json.dump(all_comments_data, f, ensure_ascii=False, indent=2)
    log(f"已保存至 all_comments.json")

if __name__ == "__main__":
    scrape_all_comments()
