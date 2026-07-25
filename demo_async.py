"""Async demo — 验证 httpx async + 多账号轮询。"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from xhshow import XHSClient

cookie = "xsecappid=xhs-pc-web; gid=yjd0WJWWf0hYyjd0WJWKY3FD2YIKDDJM3E474AySSTi3Fhq8VqKdWI888yK4YW48WqJqYj4y; x-rednote-datactry=CN; x-rednote-holderctry=CN; web_session=040069b7fe24666d3370a05b51384b09d97dc3; id_token=VjEAAA+IPdWG9o5ZOP45zz+IbaIuhzDmErsrTP0e/7CkQqtG8a2+87zthCp1YCblMjB/jml2AO/w5+W0lA456JzF4MbTwfE2RSdqyexjEkTOQkO0EO6mpojohsmrhufaHUI1WLZX; abRequestId=379b7b06-e748-5ba9-b265-1116d9a3580f; ets=1784947202434; webBuild=6.34.5; a1=19f9724d9a8ikzbskftkyflek6ot519srd9q215hy30000337327; webId=b129b6ee662a128dcc3731baef3dc5b9; acw_tc=0a0bb19e17849472028367163e6bb389637e505956821887656accde44ebbb; unread={%22ub%22:%226a5a0c00000000000e036a72%22%2C%22ue%22:%226a59061f000000000e03f000%22%2C%22uc%22:24}; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=03558791-398d-4537-9723-33292b3ed6b3; loadts=1784947953383"

async def main():
    client = XHSClient(cookie)

    notes = await client.homefeed_async(count=3)
    print("首页推荐 (async):")
    for n in notes:
        print(f"  {n.title[:40]:40s}  {n.author:12s}")

    note = notes[0]
    detail = await client.get_note_detail_async(note)
    print(f"\n详情: {detail.get('user', {}).get('nickname', '?')}")

    print("\n评论 (async):")
    i = 0
    async for c in client.get_comments_async(note, max_sub_pages=2):
        if i >= 3:
            break
        print(f"  [{i+1}] {c.user}: {c.content[:50]}")
        i += 1

    print("\n搜索 (async):")
    i = 0
    async for n in client.search_notes_async("咖啡"):
        if i >= 3:
            break
        print(f"  {n.title[:40]:40s}  ❤️{n.liked_count}")
        i += 1

    print("\n✅ async 全部跑通！")

asyncio.run(main())
