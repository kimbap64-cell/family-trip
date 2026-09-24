"""YouTube Data API 키 + 하드캡 동작 확인 (실제 1회 호출 = 1 유닛)."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import yt_api
from common import mask

print("키:", mask(os.environ.get("YOUTUBE_API_KEY")))
items = yt_api.videos(["kBEihWxDht8", "ohKMea-RB-Q"])
for it in items:
    st, sn = it["statistics"], it["snippet"]
    print(f"- {it['id']} | {sn['channelTitle']} | 조회 {st.get('viewCount')} | 좋아요 {st.get('likeCount')} | 댓글 {st.get('commentCount')}")
print("\n[사용량 장부]")
for c, u in qg.usage().items():
    print(f"  {c:<20} 오늘 {u['today']:>5}/{u['daily_cap']:<5} | 이번달 {u['month']:>6}/{u['monthly_cap']}")
