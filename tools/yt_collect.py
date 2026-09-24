"""유튜브 실수집기 (키 불필요, yt-dlp 기반).

단계
  search      지역 x 테마 검색어로 후보 영상 수집         -> data/sources/yt_candidates.json
  enrich      상위 후보의 업로드일/설명/챕터/자막여부 보강 -> data/sources/yt_enriched.json
  transcripts 선별 영상의 한국어 자막(타임스탬프 포함) 저장 -> data/sources/transcripts/<id>.json

사용:  python tools/yt_collect.py search [--per 10]
       python tools/yt_collect.py enrich [--top 250] [--since 20230101]
       python tools/yt_collect.py transcripts [--ids a,b,c | --from-enriched N]
"""
import argparse, json, math, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
import yt_dlp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "sources")
os.makedirs(os.path.join(SRC, "transcripts"), exist_ok=True)

# 하남 미사 기준 약 1시간~1시간 30분권
REGIONS = ["하남 미사", "남양주", "구리", "경기 광주 퇴촌", "곤지암", "양평", "가평", "용인", "이천", "여주",
           "포천", "파주", "인천 송도", "인천 영종도", "시흥", "강화", "춘천"]
# (theme_key, 검색어 접미)
THEMES = [
    ("day_trip", "아이랑 당일치기 나들이"),
    ("animal_nature", "아이와 가볼만한곳 동물 먹이주기 자연체험"),
    ("barrier_free", "부모님 모시고 평지 무장애 걷기 편한 가족여행"),
    ("food", "아이랑 가족 맛집 식당"),
    ("cafe", "아이랑 카페 베이커리 잔디"),
    ("camping", "키즈 오토캠핑장 아이랑"),
]


def _search(query, per):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as y:
        r = y.extract_info(f"ytsearch{per}:{query}", download=False)
    return query, r.get("entries", []) or []


def cmd_search(a):
    jobs = [(f"{reg} {suffix}", reg, key) for reg in REGIONS for key, suffix in THEMES]
    cand = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_search, q, a.per): (q, reg, key) for q, reg, key in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            q, reg, key = futs[f]
            try:
                _, entries = f.result()
            except Exception as e:
                print(f"[실패] {q}: {e}", flush=True)
                continue
            for rank, e in enumerate(entries):
                vid = e.get("id")
                if not vid:
                    continue
                c = cand.setdefault(vid, {
                    "video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
                    "view_count": e.get("view_count"), "duration": e.get("duration"),
                    "matches": []})
                c["matches"].append({"query": q, "region": reg, "theme": key, "rank": rank})
            if i % 10 == 0:
                print(f"  진행 {i}/{len(jobs)} | 누적 후보 {len(cand)} | {time.time()-t0:.0f}s", flush=True)
    out = sorted(cand.values(), key=lambda c: -len(c["matches"]))
    json.dump({"collected_at": time.strftime("%Y-%m-%d"), "queries": len(jobs), "videos": out},
              open(os.path.join(SRC, "yt_candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[완료] 후보 영상 {len(out)}개 저장 ({time.time()-t0:.0f}s)")


def _score(c):
    views = c.get("view_count") or 0
    return len(c["matches"]) * 2 + math.log10(views + 10)


CACHE = os.path.join(ROOT, "data", "cache", "yt")
os.makedirs(CACHE, exist_ok=True)

# 광고/협찬 힌트: 제목+설명에서 탐지 (신뢰도 감점 근거로 사용)
SPONSOR_RE = re.compile(r"(유료\s*광고|광고\s*포함|협찬|제공\s*받|제공받|원고료|체험단|소정의|서포터즈|PPL|sponsored|#ad\b|파트너십|초청)", re.I)


class BotBlocked(Exception):
    pass


def _enrich_one(vid):
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as y:
        try:
            i = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        except Exception as e:
            if "not a bot" in str(e) or "Please sign in" in str(e):
                raise BotBlocked(str(e)[:80])
            raise
    text = (i.get("title") or "") + "\n" + (i.get("description") or "")
    return {
        "video_id": vid, "fetched_at": time.strftime("%Y-%m-%d"),
        "upload_date": i.get("upload_date"), "description": (i.get("description") or "")[:3000],
        "chapters": [{"start": c.get("start_time"), "title": c.get("title")} for c in (i.get("chapters") or [])],
        "has_ko_auto_caption": "ko" in (i.get("automatic_captions") or {}),
        "has_ko_manual_caption": "ko" in (i.get("subtitles") or {}),
        "view_count": i.get("view_count"), "like_count": i.get("like_count"), "comment_count": i.get("comment_count"),
        "channel_id": i.get("channel_id"), "channel": i.get("channel"),
        "channel_follower_count": i.get("channel_follower_count"),
        "duration": i.get("duration"), "tags": (i.get("tags") or [])[:15],
        "sponsored_hint": sorted({m.group(0) for m in SPONSOR_RE.finditer(text)}),
    }


def cmd_enrich(a):
    data = json.load(open(os.path.join(SRC, "yt_candidates.json"), encoding="utf-8"))
    vids = [c for c in data["videos"]
            if 180 <= (c.get("duration") or 0) <= 3000 and (c.get("view_count") or 0) >= a.min_views]
    vids.sort(key=_score, reverse=True)
    vids = vids[: a.top]
    print(f"보강 대상 {len(vids)}개 (3~50분, 조회수>={a.min_views}) | 캐시 {len(os.listdir(CACHE))}개", flush=True)
    t0, consecutive_block, blocked_rounds = time.time(), 0, 0
    for n, c in enumerate(vids, 1):
        p = os.path.join(CACHE, f"{c['video_id']}.json")
        if os.path.exists(p):
            continue
        while True:
            try:
                info = _enrich_one(c["video_id"])
                json.dump(info, open(p, "w", encoding="utf-8"), ensure_ascii=False)
                consecutive_block = 0
                break
            except BotBlocked:
                consecutive_block += 1
                if consecutive_block >= 3:
                    blocked_rounds += 1
                    if blocked_rounds > a.max_backoffs:
                        print("[중단] 봇 차단 지속 - 나중에 다시 실행하면 캐시 이어서 진행", flush=True)
                        vids = []
                        break
                    print(f"[차단감지] {a.backoff}s 대기 후 재시도 (#{blocked_rounds})", flush=True)
                    time.sleep(a.backoff)
                    consecutive_block = 0
                else:
                    time.sleep(10)
            except Exception as e:
                print(f"[실패] {c['video_id']}: {str(e)[:70]}", flush=True)
                json.dump({"video_id": c["video_id"], "error": str(e)[:120]}, open(p, "w", encoding="utf-8"))
                break
        if not vids:
            break
        if n % 10 == 0:
            print(f"  진행 {n}/{len(vids)} | {time.time()-t0:.0f}s", flush=True)
        time.sleep(random.uniform(a.sleep_min, a.sleep_max))

    # 캐시에서 병합
    done = []
    for c in vids or []:
        p = os.path.join(CACHE, f"{c['video_id']}.json")
        if not os.path.exists(p):
            continue
        info = json.load(open(p, encoding="utf-8"))
        if info.get("error"):
            continue
        c.update(info)
        if (c.get("upload_date") or "0") >= a.since:
            done.append(c)
    done.sort(key=_score, reverse=True)
    json.dump({"since": a.since, "videos": done}, open(os.path.join(SRC, "yt_enriched.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[완료] {a.since} 이후 영상 {len(done)}개 저장 (캐시 {len(os.listdir(CACHE))}개)")


def cmd_transcripts(a):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    if a.ids:
        ids = a.ids.split(",")
    else:
        en = json.load(open(os.path.join(SRC, "yt_enriched.json"), encoding="utf-8"))["videos"]
        ids = [v["video_id"] for v in en[: a.from_enriched]]
    ok = fail = skip = 0
    for vid in ids:
        p = os.path.join(SRC, "transcripts", f"{vid}.json")
        if os.path.exists(p):
            skip += 1
            continue
        try:
            t = api.fetch(vid, languages=["ko"])
            raw = t.to_raw_data()
            json.dump({"video_id": vid, "language": "ko", "snippets": raw}, open(p, "w", encoding="utf-8"),
                      ensure_ascii=False)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[자막없음/실패] {vid}: {type(e).__name__}", flush=True)
        time.sleep(1.0)  # 과도한 요청 방지
    print(f"[완료] 저장 {ok} / 실패 {fail} / 기존 {skip}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search"); s.add_argument("--per", type=int, default=10); s.set_defaults(f=cmd_search)
    e = sp.add_parser("enrich"); e.add_argument("--top", type=int, default=250)
    e.add_argument("--since", default="20230101"); e.add_argument("--min-views", type=int, default=500)
    e.add_argument("--sleep-min", type=float, default=2.0); e.add_argument("--sleep-max", type=float, default=4.5)
    e.add_argument("--backoff", type=int, default=300); e.add_argument("--max-backoffs", type=int, default=3)
    e.set_defaults(f=cmd_enrich)
    t = sp.add_parser("transcripts"); t.add_argument("--ids"); t.add_argument("--from-enriched", type=int, default=50)
    t.set_defaults(f=cmd_transcripts)
    a = ap.parse_args()
    a.f(a)
