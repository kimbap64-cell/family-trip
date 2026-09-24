"""나들이 장소 주변 식당 1·2·3순위 / 카페 1·2순위 조합 (간이 검증: 네이버 목록 별점·리뷰 + 카카오 존재 확인).

- 1순위: 종합 최고(별점·리뷰·거리)  2순위: 아이 입맛(면·돈까스·파스타·분식·피자)  3순위: 속 편한 한식(두부·솥밥·국밥·곰탕·백반·샤브 등)
- 카페 1순위: 종합 최고  2순위: 정원·잔디·베이커리 성격 또는 차순위
- 상세(메뉴 가격·블로그 본문·카카오 별점)는 '간이 검증' 단계에서는 읽지 않는다 → tier '간이'. 이후 pilot 파이프라인으로 승급 가능.
결과: data/daytrip/courses.json     사용: python tools/daytrip_courses.py [--n 10]
"""
import argparse, json, math, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import kakao_local as kl
import geo
from pilot_local import kind_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "daytrip")
KIDS_CAT = re.compile(r"면|국수|돈까스|돈가스|파스타|스파게티|분식|피자|우동|라멘|쫄면|떡볶이|햄버거|양식|칼국수")
SOFT_CAT = re.compile(r"두부|순두부|솥밥|국밥|곰탕|설렁탕|백반|한정식|샤브|죽|백숙|전골|찌개|탕|찜|비빔밥|쌈밥|한식")
GARDEN = re.compile(r"정원|가든|잔디|베이커리|브런치|대형|숲|뷰|리버|호수")


def sigungu(addr):
    m = re.search(r"([가-힣]+)(시|군)", addr or "")
    return m.group(1) if m else ""


def rank(c, cx, cy):
    r, n = c.get("visitor_review_score"), c.get("visitor_review_count") or 0
    bay = ((r or 4.2) * n + 4.2 * 100) / (n + 100)
    dist = geo.haversine_m(cx, cy, c["x"], c["y"]) / 1000
    return round(bay * 10 + math.log10(n + 10) * 2 - dist * 1.2, 2), dist


def pick(cs, pred, used):
    for c in cs:
        if c["id"] not in used and pred(c):
            used.add(c["id"])
            return c
    return None


def slim(c, dist, kv):
    return {"place_id": c["id"], "name": c["name"], "category": c.get("category"), "road_address": c.get("road_address"),
            "x": c["x"], "y": c["y"], "score": c.get("visitor_review_score"), "reviews": c.get("visitor_review_count"),
            "blog_reviews": c.get("blog_review_count"), "dist_km": round(dist, 1), "phone": c.get("phone"),
            "kakao": {"found": kv.get("found"), "kakao_id": kv.get("kakao_id"), "kakao_url": kv.get("kakao_url"), "dist_m": kv.get("dist_m")},
            "nav": npl.nav_links(c["name"], c["x"], c["y"], c["id"]), "tier": "간이"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    places = json.load(open(os.path.join(OUT, "places.json"), encoding="utf-8"))["places"]
    tops = [p for p in places if p["scores"]["tier"] in ("추천", "조건부")][: a.n]
    courses, t0 = [], time.time()
    for p in tops:
        cx, cy = p["naver"]["x"], p["naver"]["y"]
        sg = sigungu(p["naver"]["road_address"])
        pool = {}
        try:
            for q in (f"{sg} 맛집", f"{sg} 한식 두부 국밥", f"{sg} 카페"):
                for it in npl.list_places(q, cx, cy):
                    k = kind_of(it["category"])
                    if k and it.get("id") and (it.get("visitor_review_count") or 0) >= 200:
                        it["kind"] = k
                        pool[it["id"]] = it
        except (npl.NaverBlocked, qg.QuotaExceeded) as e:
            print("[중단]", e); break
        cand = {"restaurant": [], "cafe": []}
        for c in pool.values():
            sc, dist = rank(c, cx, cy)
            r = c.get("visitor_review_score")
            if dist <= 9 and (r is None or r >= 4.3):
                cand[c["kind"]].append((sc, dist, c))
        for k in cand:
            cand[k].sort(key=lambda t: -t[0])
        rs, cf = [t[2] for t in cand["restaurant"]], [t[2] for t in cand["cafe"]]
        dmap = {t[2]["id"]: t[1] for k in cand for t in cand[k]}
        used = set()
        m1 = pick(rs, lambda c: True, used)
        m2 = pick(rs, lambda c: KIDS_CAT.search(c.get("category") or ""), used)
        m3 = pick(rs, lambda c: SOFT_CAT.search((c.get("category") or "") + c["name"]), used)
        c1 = pick(cf, lambda c: True, used)
        c2 = pick(cf, lambda c: GARDEN.search(c.get("category", "") + c["name"]), used) or pick(cf, lambda c: True, used)
        meals, cafes = [], []
        for role, c in (("1순위 대표", m1), ("2순위 아이 입맛", m2), ("3순위 속 편한 한식", m3)):
            if c:
                try:
                    kv = kl.verify(c["name"], c["x"], c["y"])
                except qg.QuotaExceeded:
                    kv = {"found": False}
                meals.append({"role": role, **slim(c, dmap[c["id"]], kv)})
        for role, c in (("1순위 전망·베이커리", c1), ("2순위 정원·잔디", c2)):
            if c:
                try:
                    kv = kl.verify(c["name"], c["x"], c["y"])
                except qg.QuotaExceeded:
                    kv = {"found": False}
                cafes.append({"role": role, **slim(c, dmap[c["id"]], kv)})
        courses.append({"attraction_id": p["naver"]["place_id"], "attraction": p["name"], "region": sg, "drive_min": (p.get("drive") or {}).get("min"),
                        "meals": meals, "cafes": cafes})
        print(f"  {p['name'][:12]:<12} 식당 {[m['name'][:8] for m in meals]} 카페 {[c['name'][:8] for c in cafes]} ({time.time()-t0:.0f}s)", flush=True)
    json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "note": "간이 검증(네이버 목록 별점·리뷰 + 카카오 존재 확인). 상세·블로그 본문은 미확인", "courses": courses},
              open(os.path.join(OUT, "courses.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[완료] 코스 {len(courses)}개")


if __name__ == "__main__":
    main()
