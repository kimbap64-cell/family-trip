"""장소별 맞춤 유튜브 근거 수집 (공식 API, quota_guard 경유).

추천·조건부 상위 장소마다 '<이름> 후기'로 검색 -> 제목/설명에 그 장소 이름이 있는 영상만 채택 -> 영상 신뢰도(S)·타임스탬프 링크를
기존 youtube.json 에 병합(영상 id 중복 제거). 이후 pilot_score 가 mentions 를 독립 출처로 센다.

  python tools/yt_place_search.py --places data/daytrip/places.json --yt data/daytrip/youtube.json --n 12 --suffix 후기
결과 캐시: data/cache/ytps/<place_id>.json (같은 장소는 다시 API 를 부르지 않는다). 검색 1회 = 100유닛, 일 검색 캡(40)·유닛 캡(3000) 적용.
"""
import argparse, json, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import yt_api
from pilot_youtube import core_name, norm, source_score, parse_dur

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "ytps")
os.makedirs(CACHE, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--places", required=True)
    ap.add_argument("--yt", required=True)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--suffix", default="후기")
    ap.add_argument("--since", default="2024-09-01T00:00:00Z")
    a = ap.parse_args()
    P = lambda x: os.path.join(ROOT, x)
    places = json.load(open(P(a.places), encoding="utf-8"))["places"]
    tops = [p for p in places if p["scores"]["tier"] in ("추천", "조건부", "근거부족") and len(norm(core_name(p["name"]))) >= 3]
    order = {"추천": 0, "조건부": 1, "근거부족": 2}
    tops.sort(key=lambda p: (order[p["scores"]["tier"]], -p["scores"]["total"]))
    tops = tops[: a.n]
    yt = json.load(open(P(a.yt), encoding="utf-8")) if os.path.exists(P(a.yt)) else {"videos": [], "mentions": [], "queries": []}
    have = {v["id"] for v in yt["videos"]}
    added_v, added_m, spent = 0, 0, 0
    for p in tops:
        pid = p["naver"]["place_id"]
        cp = os.path.join(CACHE, f"{pid}.json")
        core = core_name(p["name"])
        if os.path.exists(cp):
            found = json.load(open(cp, encoding="utf-8"))
        else:
            try:
                qg.ensure_available("youtube_api_search")
                items = yt_api.search(f"{core} {a.suffix}", max_results=6, published_after=a.since)
                ids = [it["id"]["videoId"] for it in items]
                vids = yt_api.videos(ids) if ids else []
                chs = {c["id"]: c for c in yt_api.channels(sorted({v["snippet"]["channelId"] for v in vids}))} if vids else {}
            except (qg.QuotaExceeded, qg.ForbiddenAPI) as e:
                print(f"[캡] {e} — 여기까지 저장"); break
            spent += 1
            found = {"query": f"{core} {a.suffix}", "videos": vids, "channels": chs}
            json.dump(found, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
        n_here = 0
        for v in found["videos"]:
            sn = v["snippet"]
            text = sn["title"] + "\n" + sn.get("description", "")
            if norm(core) not in norm(text):
                continue
            ch = (found["channels"] or {}).get(sn["channelId"])
            hits_in_desc = 1 + sum(1 for x in tops if x is not p and norm(core_name(x["name"])) in norm(text))
            rec = {"id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}", "title": sn["title"], "channel": sn["channelTitle"],
                   "channel_id": sn["channelId"], "published": sn["publishedAt"][:10], "duration_s": parse_dur(v["contentDetails"]["duration"]),
                   "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0)),
                   "comments": int(v["statistics"].get("commentCount", 0)),
                   "subscribers": int(((ch or {}).get("statistics") or {}).get("subscriberCount", 0) or 0),
                   "credibility": source_score(v, ch, hits_in_desc), "mentioned_places": [pid], "via": "place-search"}
            if v["id"] not in have:
                yt["videos"].append(rec); have.add(v["id"]); added_v += 1
            else:
                for x in yt["videos"]:
                    if x["id"] == v["id"] and pid not in x["mentioned_places"]:
                        x["mentioned_places"].append(pid)
            # 타임스탬프 목차에서 시점 추출
            t_sec, quote = None, "(제목/설명에 언급)"
            for ln in sn.get("description", "").split("\n"):
                if norm(core) in norm(ln):
                    quote = ln.strip()[:120]
                    m = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", ln)
                    if m:
                        t1, t2, t3 = m.groups()
                        t_sec = int(t1) * 3600 + int(t2) * 60 + int(t3) if t3 else int(t1) * 60 + int(t2)
                    break
            if not any(m["place_id"] == pid and m["video_id"] == v["id"] for m in yt["mentions"]):
                yt["mentions"].append({"place_id": pid, "video_id": v["id"], "t": t_sec, "quote": quote, "where": "description",
                                       "link": rec["url"] + (f"&t={t_sec}" if t_sec is not None else "")})
                added_m += 1
                n_here += 1
        print(f"  {p['name'][:14]:<14} [{p['scores']['tier']}] 채택 영상 {n_here}개", flush=True)
    yt["generated"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(yt, open(P(a.yt), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[완료] 신규 영상 {added_v} · 신규 언급 {added_m} · API 검색 {spent}회")
    for c, u in qg.usage().items():
        if c.startswith("youtube_api") and u["today"]:
            print(f"  캡 {c:<20} {u['today']}/{u['daily_cap']}")


if __name__ == "__main__":
    main()
