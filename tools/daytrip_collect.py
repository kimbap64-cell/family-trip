"""당일 나들이(편도 90분 이내) 체험·나들이 장소 발굴 + 근거 수집.  결과: data/daytrip/raw.json (점수화는 pilot_score.py --scope day_trip)

발굴 소스: ① 네이버 플레이스 카테고리x지역 검색 ② 1차본 22선 이름(후보 단서로만) ③ 유튜브 영상에서 반복 언급된 장소
모두 네이버 플레이스/카카오로 실존·좌표 재검증. 캐시·quota_guard 캡 적용, 차단 신호면 즉시 중단(저장분 보존).
사용: python tools/daytrip_collect.py [--top 30] [--blogs 1]
"""
import argparse, json, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import geo
from collect import collect_one

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "daytrip")
os.makedirs(OUT, exist_ok=True)

QUERIES = [
    "남양주 아이와 가볼만한곳", "가평 아이와 가볼만한곳", "양평 아이와 가볼만한곳", "곤지암 퇴촌 아이와 가볼만한곳", "용인 아이와 가볼만한곳",
    "이천 여주 아이와 가볼만한곳", "포천 파주 아이와 가볼만한곳", "인천 송도 영종도 아이와 가볼만한곳", "시흥 강화 아이와 가볼만한곳",
    "수목원 식물원", "동물 먹이주기 체험", "체험농장 목장", "생태공원 습지공원", "자연휴양림 계곡", "박물관 과학관 아이", "호수공원 산책 둘레길",
]
EXTRA_SEEDS = ["강화루지", "화개정원", "전등사", "대룡시장", "상상플랫폼", "예단포 둘레길", "하남 미사경정공원", "비둘기낭폭포", "포천 아트밸리",
               "서울대공원", "인천대공원", "국립인천해양박물관", "송도 센트럴파크", "소래습지생태공원", "시흥 갯골생태공원", "물향기수목원",
               "광명동굴", "구리 한강시민공원", "남양주 물의정원", "세미원", "쁘띠프랑스", "아침고요수목원", "화담숲", "한택식물원", "허브아일랜드",
               "산정호수", "양평 두물머리", "에버랜드", "서울랜드", "아쿠아플라넷 일산", "안산 화랑유원지", "율봄식물원", "다산생태공원"]
ATTR_RE = re.compile(r"수목원|식물원|공원|생태|체험|목장|농원|농장|동물|아쿠아|수족관|박물관|과학관|테마파크|놀이|휴양림|계곡|호수|해수욕장|갯벌|레일바이크|승마|썰매|딸기|수확|미술관|전시|전망대|숲|둘레길|산책|정원|관광|명소|유원지|폭포|섬|해변|랜드|궁|마을|시장")
EXCL_RE = re.compile(r"부속시설|학원|병원|약국|부동산|편의점|마트|미용|세탁|은행|주유소|주차장|체육관|교회|어린이집|유치원|음식|식당|카페|커피|베이커리|캠핑|펜션|호텔|리조트|모텔|숙박|글램핑|골프|낚시|사무|공사|주민센터|아파트|도서관")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--blogs", type=int, default=1)
    ap.add_argument("--max-drive", type=float, default=90)
    a = ap.parse_args()
    hx, hy = geo.home()
    t0 = time.time()

    legacy = json.load(open(os.path.join(ROOT, "data", "legacy", "courses_22_unverified.json"), encoding="utf-8"))["courses"]
    legacy_names = [re.split(r"\s*&\s*", c["spot1"]["name"])[0] for c in legacy]

    cands = {}

    def add(it, tag):
        if not it or not it.get("id"):
            return
        cat = it.get("category") or ""
        if EXCL_RE.search(cat) or not ATTR_RE.search(cat + " " + (it.get("name") or "")):
            return
        c = cands.setdefault(it["id"], {**it, "queries": [], "seeds": []})
        c["queries"].append(tag) if tag.startswith("q:") else c["seeds"].append(tag)

    try:
        for q in QUERIES:
            for it in npl.list_places(q, hx, hy):
                add(it, "q:" + q)
            print(f"  발굴 '{q}': 누적 {len(cands)}", flush=True)
        for nm, tag in [(n, "seed:legacy") for n in legacy_names] + [(n, "seed:youtube/추가") for n in EXTRA_SEEDS]:
            r = npl.resolve(nm, hx, hy)
            if r["place"] and r["match"] >= 0.75:
                add(r["place"], tag)
    except npl.NaverBlocked as e:
        print("[중단] 네이버 차단 신호:", e); return
    except qg.QuotaExceeded as e:
        print("[캡]", e)
    print(f"[1] 발굴+시드 후보 {len(cands)}개 ({time.time()-t0:.0f}s)")

    pool = []
    for c in cands.values():
        c["straight_m"] = round(geo.haversine_m(hx, hy, c["x"], c["y"]))
        if c["straight_m"] <= 68000 and (c.get("visitor_review_count") or 0) + (c.get("blog_review_count") or 0) // 10 >= 200:
            pool.append(c)
    pool.sort(key=lambda c: -((c.get("visitor_review_count") or 0) + (c.get("blog_review_count") or 0) // 10 + 3000 * len(c["seeds"])))
    pool = pool[:75]
    print(f"[2] 직선 68km·리뷰 기준 통과 {len(pool)}개")

    near = []
    for c in pool:
        try:
            c["drive"] = geo.drive(c["x"], c["y"])
        except qg.QuotaExceeded as e:
            print("[캡]", e); break
        if c["drive"]["min"] <= a.max_drive:
            near.append(c)
    print(f"[3] 차량 {a.max_drive:.0f}분 이내 {len(near)}개 ({time.time()-t0:.0f}s)")

    results = []
    rawp = os.path.join(OUT, "raw.json")
    for i, c in enumerate(near[: a.top], 1):
        try:
            rec = collect_one(c, "attraction", blogs_per_place=a.blogs)
        except npl.NaverBlocked as e:
            print("[중단] 네이버 차단:", e); break
        except qg.QuotaExceeded as e:
            print("[캡]", e); break
        results.append(rec)
        print(f"  [{i}/{min(a.top, len(near))}] {c['name'][:20]:<20} ★N{c.get('visitor_review_score')}/K{rec['kakao'].get('rating')} {c['drive']['min']}분 "
              f"블로그 {len(rec['blogs_read'])}편 시드:{','.join(c['seeds'])[:24]} ({time.time()-t0:.0f}s)", flush=True)
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "home": [hx, hy], "places": results}, open(rawp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[완료] {len(results)}곳 수집, {time.time()-t0:.0f}s")
    for c_, u in qg.usage().items():
        if u["today"]:
            print(f"  캡 {c_:<18} {u['today']}/{u['daily_cap']}")


if __name__ == "__main__":
    main()
