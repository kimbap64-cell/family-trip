"""YouTube Data API v3 클라이언트 (공식 API, 하드캡 적용).

모든 호출은 quota_guard 를 통과한다: 허용 목록 검사 -> 유닛 비용만큼 일/월 한도 차감 -> 호출.
구글 무료 한도(일 10,000 유닛, 검색 일 100회) 안에서, 우리 캡(config/limits.json)이 더 낮게 막는다.
403 quotaExceeded 를 받으면 즉시 QuotaExceeded 를 던지고 재시도하지 않는다.
"""
import os, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
from common import load_env, need

load_env()
BASE = "https://www.googleapis.com/youtube/v3"


def _call(endpoint, params, search=False):
    qg.require_google_api("youtube")
    cost = qg._cfg()["unit_costs"]["youtube"][endpoint]
    qg.charge("youtube_api_units", cost)
    if search:
        qg.charge("youtube_api_search", 1)
    r = requests.get(f"{BASE}/{endpoint.split('.')[0]}", params={**params, "key": need("YOUTUBE_API_KEY")}, timeout=25)
    if r.status_code == 403 and "quota" in r.text.lower():
        raise qg.QuotaExceeded("구글 쪽 일일 할당량 초과(403 quotaExceeded) — 재시도하지 않음")
    if r.status_code != 200:
        raise RuntimeError(f"YouTube API {r.status_code}: {r.text[:200]}")
    return r.json()


def search(q, max_results=10, published_after=None, order="relevance"):
    """영상 검색 (100 유닛). published_after 예: '2025-09-01T00:00:00Z'"""
    p = {"part": "snippet", "type": "video", "q": q, "maxResults": max_results, "regionCode": "KR",
         "relevanceLanguage": "ko", "order": order, "videoDuration": "any"}
    if published_after:
        p["publishedAfter"] = published_after
    return _call("search.list", p, search=True).get("items", [])


def videos(ids):
    """영상 상세·통계 (50개당 1 유닛). ids: list"""
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        out += _call("videos.list", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)}).get("items", [])
    return out


def channels(ids):
    """채널 구독자 등 (50개당 1 유닛)."""
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        out += _call("channels.list", {"part": "snippet,statistics", "id": ",".join(chunk)}).get("items", [])
    return out


def comments(video_id, max_results=30, order="relevance"):
    """상위 댓글 (1 유닛). 댓글이 막힌 영상은 빈 리스트."""
    try:
        j = _call("commentThreads.list", {"part": "snippet", "videoId": video_id, "maxResults": max_results,
                                          "order": order, "textFormat": "plainText"})
    except RuntimeError as e:
        if "commentsDisabled" in str(e) or "403" in str(e):
            return []
        raise
    return [{"text": it["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
             "likes": it["snippet"]["topLevelComment"]["snippet"]["likeCount"],
             "published": it["snippet"]["topLevelComment"]["snippet"]["publishedAt"]} for it in j.get("items", [])]
