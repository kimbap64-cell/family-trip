"""키즈 오토캠핑장(편도 65분 이내) 발굴 + 근거 수집.  결과: data/camping/raw.json (점수화는 pilot_score.py --scope camping)

네이버 플레이스 '캠핑,야영장' x 지역 검색 -> 사전필터 -> 이동시간(OSRM) -> 상세(네이버)·카카오 검증/별점/리뷰 -> (캡 여유가 있으면) 블로그 본문.
캡(블로그 등)이 소진되면 해당 부분만 건너뛰고 저장 -> 캡이 풀린 뒤 같은 명령을 다시 실행하면 캐시로 빠르게 이어서 채운다.
사용: python tools/camp_collect.py [--top 25] [--blogs 2]
"""
import argparse, json, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import geo
from collect import collect_one

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "camping")
os.makedirs(OUT, exist_ok=True)

REGIONS = ["하남", "남양주", "가평", "양평", "광주", "구리", "이천", "여주", "용인", "포천", "파주", "강화", "시흥"]
# 네이버는 '○○ 캠핑장' 검색에 숙박 형식(AccommodationSearchItem, 별점·리뷰·최저요금 포함)으로 응답한다 -> naver_place.list_places 가 파싱
QUERIES = [f"{r} 캠핑장" for r in REGIONS] + ["키즈 캠핑장", "오토캠핑", "캠핑장 계곡", "글램핑 키즈 수영장"]
CAMP_RE = re.compile(r"캠핑|야영|글램핑|카라반")
EXCL_RE = re.compile(r"용품|장비|제조|판매|쇼핑|렌탈|대여|정비|수리|마트|의류|낚시용품|가구")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--blogs", type=int, default=2)
    ap.add_argument("--max-drive", type=float, default=65)
    a = ap.parse_args()
    hx, hy = geo.home()
    t0 = time.time()
    cands = {}
    try:
        for q in QUERIES:
            for it in npl.list_places(q, hx, hy):
                cat = it.get("category") or ""
                if it.get("id") and CAMP_RE.search(cat + " " + (it.get("name") or "")) and not EXCL_RE.search(cat + " " + (it.get("name") or "")) and "부속시설" not in cat:
                    c = cands.setdefault(it["id"], {**it, "queries": [], "seeds": []})
                    c["queries"].append("q:" + q)
            print(f"  발굴 '{q}': 누적 {len(cands)}", flush=True)
    except npl.NaverBlocked as e:
        print("[중단] 네이버 차단 신호:", e); return
    except qg.QuotaExceeded as e:
        print("[캡]", e)
    print(f"[1] 캠핑장 후보 {len(cands)}개 ({time.time()-t0:.0f}s)")

    from camp_types import camp_type
    pool = []
    for c in cands.values():
        c["straight_m"] = round(geo.haversine_m(hx, hy, c["x"], c["y"]))
        if c["straight_m"] <= 55000 and (c.get("visitor_review_count") or 0) + (c.get("blog_review_count") or 0) // 10 >= 40:
            c["ctype"] = camp_type(c["name"], c.get("promo") or "", c.get("category") or "")
            pool.append(c)
    rk = lambda c: -((c.get("visitor_review_count") or 0) + (c.get("blog_review_count") or 0) // 10)
    # 사용자 요청은 '키즈 오토캠핑장' — 리뷰순으로만 뽑으면 예약이 쉬운 글램핑이 앞서므로 유형별로 나눠 뽑는다(오토캠핑 최대 30 + 그 외 20)
    auto = sorted([c for c in pool if c["ctype"] == "오토캠핑"], key=rk)[:30]
    rest = sorted([c for c in pool if c["ctype"] != "오토캠핑"], key=rk)[:20]
    pool = auto + rest
    print(f"[2] 직선 55km·리뷰 기준 통과 {len(pool)}개 (오토캠핑 {len(auto)} · 글램핑/카라반 등 {len(rest)})")

    near = []
    for c in pool:
        try:
            c["drive"] = geo.drive(c["x"], c["y"])
        except qg.QuotaExceeded as e:
            print("[캡]", e); break
        if c["drive"]["min"] <= a.max_drive:
            near.append(c)
    print(f"[3] 차량 {a.max_drive:.0f}분 이내 {len(near)}개 ({time.time()-t0:.0f}s)")

    # 수집 대상: 오토캠핑을 우선(최대 top*0.6), 나머지로 채움
    n_auto = int(a.top * 0.6)
    near = [c for c in near if c["ctype"] == "오토캠핑"][:n_auto] + [c for c in near if c["ctype"] != "오토캠핑"]
    print(f"    수집 대상 순서: 오토캠핑 {sum(1 for c in near[:a.top] if c['ctype'] == '오토캠핑')}곳 포함")
    results, rawp = [], os.path.join(OUT, "raw.json")
    for i, c in enumerate(near[: a.top], 1):
        try:
            rec = collect_one(c, "camping", blogs_per_place=a.blogs)
        except npl.NaverBlocked as e:
            print("[중단] 네이버 차단:", e); break
        except qg.QuotaExceeded as e:
            print("[캡] 상세 조회 캡 — 저장 후 중단:", e); break
        results.append(rec)
        print(f"  [{i}/{min(a.top, len(near))}] {c['name'][:18]:<18} ★N{c.get('visitor_review_score')}/K{rec['kakao'].get('rating')} {c['drive']['min']}분 "
              f"블로그 {len(rec['blogs_read'])}편 {'|'.join(rec['notes'])[:30]} ({time.time()-t0:.0f}s)", flush=True)
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "home": [hx, hy], "places": results}, open(rawp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[완료] {len(results)}곳 수집, {time.time()-t0:.0f}s")
    for c_, u in qg.usage().items():
        if u["today"]:
            print(f"  캡 {c_:<18} {u['today']}/{u['daily_cap']}")


if __name__ == "__main__":
    main()
