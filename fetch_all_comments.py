"""全量抓取笔记评论 — 使用 XHSClient，零样板代码。"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from xhshow import XHSClient

cookie = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"

client = XHSClient(cookie)

# 从首页拿一篇笔记
notes = client.homefeed(count=1)
note = notes[0]

print(f"抓取笔记: {note.title} (id={note.note_id})")

all_comments = []
for comment in client.get_comments(note, expand_sub=True, max_sub_pages=5):
    all_comments.append({
        "user": comment.user,
        "content": comment.content,
        "like_count": comment.like_count,
        "subs": [{"user": s.user, "content": s.content, "like_count": s.like_count} for s in comment.sub_comments],
    })

total = sum(1 + len(c["subs"]) for c in all_comments)
print(f"完成: {len(all_comments)} 条主楼层, 含子评论共 {total} 条")

with open("all_comments.json", "w", encoding="utf-8") as f:
    json.dump(all_comments, f, ensure_ascii=False, indent=2)
print("已保存到 all_comments.json")
