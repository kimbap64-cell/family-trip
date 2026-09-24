"""파일럿 2단계: 유튜브(공식 API)에서 동네 맛집/카페 영상을 찾아 신뢰도(S)를 매기고, 파일럿 장소가 언급된 지점을 찾는다.

- 검색 4회(=400 유닛, 검색 캡 4/40), 영상 상세·채널 통계·상위 영상 댓글 (모두 quota_guard 경유)
- 언급 탐지: 제목/설명(타임스탬프 목차 포함)/상위 댓글에서 장소 핵심명 매칭 -> 링크는 watch?v=ID&t=초
결과: data/pilot/misa_youtube.json
"""
import json, math, os, re, sys, time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import yt_api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "pilot")
SPONSOR_RE = re.compile(r"(유료\s*광고|광고\s*포함|협찬|제공\s*받|제공받|원고료|체험단|소정의|서포터즈|PPL|sponsored|#ad\b|파트너십|초청)", re.I)
QUERIES = ["하남 미사 맛집", "미사 카페 추천", "하남 미사 아이랑 맛집 가족 외식", "하남 미사 부모님 모시고 맛집"]
QUERY_SETS = {
    "local": QUERIES,
    "daytrip": ["서울 근교 아이랑 당일치기 체험 경기도", "남양주 가평 양평 아이랑 가볼만한곳", "인천 송도 영종도 강화 아이랑 당일치기",
                "시흥 광주 용인 이천 아이와 가볼만한곳", "부모님 모시고 평지 산책 당일치기 경기도", "동물 먹이주기 체험 수목원 아이랑",
                "아이랑 자연체험 숲놀이터 무장애 나들이", "하남 미사 출발 당일치기 드라이브 나들이"],
    "camping": ["경기도 키즈 오토캠핑장 추천", "하남 남양주 가평 양평 키즈캠핑", "아이랑 캠핑장 계곡 수영장 방방이", "부모님과 함께 편한 오토캠핑장 평지"],
}


def core_name(name):
    n = re.sub(r"\(.*?\)", "", name or "").strip()
    n = re.sub(r"\s*(하남|미사|풍산|덕풍|망월|감일|위례|하남미사)?\s*\S*(본점|점|지점)$", "", n).strip()
    return n


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def months_since(iso):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - d).days / 30.4


def parse_dur(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    h, mi, s = (int(x or 0) for x in (m.groups() if m else (0, 0, 0)))
    return h * 3600 + mi * 60 + s


def source_score(v, ch, n_place_mentions):
    """docs/SCORING.md §3 : 최신성25 + 반응25 + 채널20 + 정보밀도20 + 광고감점(-10)"""
    cfg = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))["source_score"]
    sn, st = v["snippet"], v["statistics"]
    mo = months_since(sn["publishedAt"])
    rec = 0
    for lim, pts in cfg["recency_points_months"]:
        if mo <= lim:
            rec = pts
            break
    views, likes, cmts = int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), int(st.get("commentCount", 0))
    eng = 10 * min(1, math.log10(views + 1) / 6) + 8 * min(1, cmts / 200) + 7 * min(1, (likes / views / 0.03) if views else 0)
    subs = int(((ch or {}).get("statistics") or {}).get("subscriberCount", 0) or 0)
    vids = int(((ch or {}).get("statistics") or {}).get("videoCount", 0) or 0)
    chn = 10 * min(1, math.log10(subs + 1) / 6) + 10 * min(1, vids / 200)
    desc = sn.get("description", "")
    dens = (6 if len(desc) >= 500 else 3 if len(desc) >= 150 else 0) + (6 if len(re.findall(r"\b\d{1,2}:\d{2}\b", desc)) >= 3 else 0) \
        + (8 if n_place_mentions >= 3 else 4 if n_place_mentions >= 1 else 0)
    spon = SPONSOR_RE.findall(sn.get("title", "") + "\n" + desc)
    pen = cfg["sponsor_penalty"] if spon else 0
    total = round(rec + min(25, eng) + min(20, chn) + min(20, dens) + pen, 1)
    return {"total": total, "recency": rec, "engagement": round(min(25, eng), 1), "channel": round(min(20, chn), 1),
            "info_density": dens, "sponsor": pen, "sponsored_hint": sorted(set(spon)), "months_old": round(mo, 1)}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/pilot/misa_raw.json")
    ap.add_argument("--out", default="data/pilot/misa_youtube.json")
    ap.add_argument("--cache", default="data/cache/yt_pilot_raw.json")
    ap.add_argument("--set", default="local")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    qg.ensure_available("youtube_api_units")
    raw = json.load(open(os.path.join(ROOT, a.raw), encoding="utf-8"))["places"]
    places = [{"id": p["naver"]["id"], "name": p["naver"]["name"], "core": core_name(p["naver"]["name"])} for p in raw]
    places = [p for p in places if len(norm(p["core"])) >= 3]
    print(f"매칭 대상 장소 {len(places)}곳")

    # 원본 API 응답 캐시: 재실행(장소 목록이 바뀐 재매칭)은 API를 다시 부르지 않는다. --refresh 로만 재수집.
    rawp = os.path.join(ROOT, a.cache)
    if os.path.exists(rawp) and not a.refresh:
        cache = json.load(open(rawp, encoding="utf-8"))
        vids, chs, comments_by = cache["vids"], cache["chs"], cache["comments"]
        print(f"캐시 사용: 영상 {len(vids)}개 (API 호출 0)")
    else:
        since = "2024-09-24T00:00:00Z"
        ids, seen = [], set()
        for q in QUERY_SETS[a.set]:
            for it in yt_api.search(q, max_results=15, published_after=since):
                vid = it["id"]["videoId"]
                if vid not in seen:
                    seen.add(vid); ids.append(vid)
            print(f"  검색 '{q}' -> 누적 영상 {len(ids)}")
        vids = yt_api.videos(ids)
        chs = {c["id"]: c for c in yt_api.channels(sorted({v["snippet"]["channelId"] for v in vids}))}
        # 댓글: 지역 관련(미사/하남) 영상 중 조회수 상위 12개만 (장소와 무관하게 고정 -> 캐시 안정)
        rel = [v for v in vids if a.set != "local" or re.search(r"미사|하남", v["snippet"]["title"] + v["snippet"].get("description", "")[:300])]
        rel.sort(key=lambda v: -int(v["statistics"].get("viewCount", 0)))
        comments_by = {}
        for v in rel[:12]:
            try:
                comments_by[v["id"]] = yt_api.comments(v["id"], max_results=40)
            except (qg.QuotaExceeded, qg.ForbiddenAPI) as e:
                print("[캡]", e); break
        json.dump({"fetched": time.strftime("%Y-%m-%d %H:%M"), "vids": vids, "chs": chs, "comments": comments_by},
                  open(rawp, "w", encoding="utf-8"), ensure_ascii=False)

    out_videos, mentions = [], []
    for v in vids:
        sn = v["snippet"]
        text = sn["title"] + "\n" + sn.get("description", "")
        nt = norm(text)
        hits = [p for p in places if norm(p["core"]) in nt]
        s = source_score(v, chs.get(sn["channelId"]), len(hits))
        dur = parse_dur(v["contentDetails"]["duration"])
        rec = {"id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}", "title": sn["title"], "channel": sn["channelTitle"],
               "channel_id": sn["channelId"], "published": sn["publishedAt"][:10], "duration_s": dur,
               "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0)),
               "comments": int(v["statistics"].get("commentCount", 0)),
               "subscribers": int(((chs.get(sn["channelId"]) or {}).get("statistics") or {}).get("subscriberCount", 0) or 0),
               "credibility": s, "mentioned_places": [p["id"] for p in hits]}
        out_videos.append(rec)
        # 타임스탬프 목차에서 시점 추출
        lines = sn.get("description", "").split("\n")
        for p in hits:
            t_sec, quote = None, None
            for ln in lines:
                if norm(p["core"]) in norm(ln):
                    m = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", ln)
                    quote = ln.strip()[:120]
                    if m:
                        t1, t2, t3 = m.groups()
                        t_sec = int(t1) * 3600 + int(t2) * 60 + int(t3) if t3 else int(t1) * 60 + int(t2)
                    break
            if quote is None:
                i = nt.find(norm(p["core"]))
                quote = "(제목/설명에 언급)"
            mentions.append({"place_id": p["id"], "video_id": v["id"], "t": t_sec, "quote": quote,
                             "link": f"{rec['url']}" + (f"&t={t_sec}" if t_sec is not None else ""), "where": "description"})

    # 캐시된 댓글에서 추가 언급/폐업 신호
    vmap = {r["id"]: r for r in out_videos}
    for vid_, cm in comments_by.items():
        r = vmap.get(vid_)
        if not r:
            continue
        r["top_comments_n"] = len(cm)
        for c in cm:
            nc = norm(c["text"])
            for p in places:
                if norm(p["core"]) in nc:
                    mentions.append({"place_id": p["id"], "video_id": r["id"], "t": None, "quote": c["text"][:140].replace("\n", " "),
                                     "link": r["url"], "where": "comment", "comment_date": c["published"][:10], "likes": c["likes"]})

    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "queries": QUERY_SETS[a.set], "videos": out_videos, "mentions": mentions},
              open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[완료] 영상 {len(out_videos)}개, 장소 언급 {len(mentions)}건 (장소 {len({m['place_id'] for m in mentions})}곳)")
    for c, u in qg.usage().items():
        if c.startswith("youtube_api") and u["today"]:
            print(f"  캡 사용 {c:<20} {u['today']}/{u['daily_cap']}")


if __name__ == "__main__":
    main()
