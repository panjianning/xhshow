"""XHSClient demo — 对比旧脚本，所有样板代码全部消除。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from xhshow import XHSClient

cookie = "gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; webBuild=6.34.5; websectiga=3fff3a6f9f07284b62c0f2ebf91a3b10193175c06e4f71492b60e056edcdebb2; sec_poison_id=a60bbb65-deae-4abf-a73c-afcb91bef028; xsecappid=xhs-pc-web; acw_tc=0a4aea7717849708709346948ea2999254ddd63850f6786ee784de97f32f37; unread={%22ub%22:%226a5a1394000000000f02a206%22%2C%22ue%22:%226a45b144000000001c027433%22%2C%22uc%22:26}; loadts=1784970887808"

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
