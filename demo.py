"""XHSClient demo — 对比旧脚本，所有样板代码全部消除。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from xhshow import XHSClient

cookie = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"

client = XHSClient(cookie)

# ---- 1. 首页推荐 ----
print("=" * 50)
print("首页推荐")
notes = client.homefeed(count=5)
for n in notes:
    print(f"  {n.title[:40]:40s}  {n.author:12s}  ❤️{n.liked_count}")

# ---- 2. 用第一篇笔记看详情 + 评论 ----
note = notes[0]
print(f"\n📄 笔记详情: {note.title}")
detail = client.get_note_detail(note)
print(f"  作者: {detail.get('user', {}).get('nickname', '?')}")
print(f"  正文: {(detail.get('desc') or '')[:100]}")

print(f"\n💬 前 3 条评论:")
for i, c in enumerate(client.get_comments(note, max_sub_pages=2)):
    if i >= 3:
        break
    print(f"  [{i+1}] {c.user}: {c.content[:50]}  👍{c.like_count}")
    for sc in c.sub_comments[:2]:
        print(f"      ↳ {sc.user}: {sc.content[:40]}  👍{sc.like_count}")

# ---- 3. 搜索 ----
print("\n🔍 搜索 '咖啡' (前 3 条):")
for i, n in enumerate(client.search_notes("咖啡")):
    if i >= 3:
        break
    print(f"  {n.title[:40]:40s}  {n.author:12s}  ❤️{n.liked_count}")

print("\n✅ 全部跑通！")
