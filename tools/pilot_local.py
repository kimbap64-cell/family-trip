"""파일럿 1단계: 우리 동네(집 기준 차량 ~12분 이내) 식당·카페 근거 수집.

발굴(네이버 플레이스 목록) -> 사전필터 -> 이동시간(OSRM/OSM) -> 상세(네이버) -> 카카오 교차검증·별점·영업상태·리뷰
-> 블로그 본문 읽기 -> 근거 문장 추출.  결과: data/pilot/misa_raw.json  (점수화는 pilot_score.py)

모든 외부 호출은 캐시 + quota_guard 캡. 차단 신호(NaverBlocked)면 즉시 중단하고 저장된 것까지만 보존.
사용: python tools/pilot_local.py [--max-detail 45] [--max-drive 12]
"""
import argparse, json, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import kakao_local as kl
import geo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "pilot")
os.makedirs(OUT, exist_ok=True)

QUERIES = [
    ("restaurant", "미사 한식"), ("restaurant", "미사 솥밥"), ("restaurant", "미사 두부 순두부"), ("restaurant", "미사 백반 정식"),
    ("restaurant", "미사 국밥 설렁탕"), ("restaurant", "미사 갈비"), ("restaurant", "미사 삼겹살"),
    ("restaurant", "미사 칼국수"), ("restaurant", "미사 냉면 국수"), ("restaurant", "미사 돈까스"), ("restaurant", "미사 파스타"),
    ("restaurant", "미사 생선구이"), ("restaurant", "미사 샤브샤브"), ("restaurant", "미사 아이랑 가족식당"),
    ("cafe", "미사 카페"), ("cafe", "미사 베이커리 카페"), ("cafe", "미사 브런치 카페"), ("cafe", "하남 대형 카페"),
]
CAFE_RE = re.compile(r"카페|커피|디저트|베이커리|제과|빵|브런치|찻집|다방")
FOOD_RE = re.compile(r"음식|식당|한식|양식|일식|중식|분식|고기|육류|갈비|삼겹|국밥|찌개|칼국수|국수|냉면|돈까스|돈가스|파스타|피자|햄버거|치킨|족발|보쌈|해산물|생선|횟집|초밥|샤브|전골|백숙|두부|솥밥|곰탕|설렁탕|순두부|중국|샐러드|뷔페|한정식|정식|쌈밥|덮밥|우동|라멘|곱창|막창|오리|닭|찜|탕|만두|죽")
EXCL_RE = re.compile(r"부속시설|학원|병원|약국|부동산|편의점|마트|미용|세탁|은행|주유소|주차장|공원|체육|헬스|교회|어린이집|유치원")

SPONSOR_RE = re.compile(r"(협찬|제공\s*받|제공받|원고료|체험단|소정의|서포터즈|광고|업체(로부터|에서)\s*(지원|제공)|초대\s*받)")
NEG_BEFORE = re.compile(r"(아님|아닌|않았|않고|없이|없음|없는|비협찬|내돈내산)")

# ---- 근거 문장 추출 패턴 ---------------------------------------------------
PAT = {
    "kids": {
        "유아의자": r"(아기|유아|어린이|아이)\s*(의자|식탁의자)",
        "키즈메뉴": r"(키즈|어린이|아이)\s*(메뉴|세트|밥|식사)",
        "놀이시설": r"(놀이방|놀이터|키즈존|키즈카페|놀이\s*공간|장난감|잔디)",
        "아이동반": r"(아이랑|아이와|아이들과|아기랑|아기와|아이\s*동반|애들이랑|아이들이\s*좋아|아이들\s*(먹기|입맛))",
        "유모차": r"유모차",
    },
    "b_pos": {
        "입식/테이블": r"(입식|테이블석|테이블\s*좌석|테이블\s*자리|의자\s*(좌석|자리|석)|홀\s*좌석)",
        "주차": r"(주차(장)?\s*(이\s*)?(넓|편|가능|무료|여유|전용|바로|이용\s*가능|공간|시설)|발렛|주차\s*걱정|주차\s*편)",
        "엘리베이터/1층/평지": r"((엘리베이터|엘베)\s*(가|는|도|로|를|이|나|와)?\s*(있|설치|이용|타고|탑승|올라|로\s*이동)|평지|턱\s*없|무단차|경사\s*(가\s*)?(없|완만)|계단\s*(이\s*)?없|1층\s*(매장|에\s*위치|입구|에\s*있))",
        "넓고 여유": r"(매장이?\s*(넓|크|쾌적)|넓은\s*(매장|공간|좌석|홀)|좌석\s*간격|자리\s*(넓|여유)|테이블\s*간격)",
        "화장실 가까움": r"(화장실\s*(이\s*)?(깨끗|청결|가까|내부|매장\s*내)|매장\s*내\s*화장실)",
    },
    "b_neg": {
        "좌식": r"(좌식|바닥에\s*앉|신발\s*(을\s*)?벗|온돌|방\s*좌석|룸\s*좌석)",
        "계단": r"(계단(이|을|은|도|으로|을\s*올)?|가파른|오르막|내리막|경사(가|진|로))",
        "엘리베이터 없음": r"(엘리베이터\s*(가\s*)?없|엘베\s*(가\s*)?없)",
        "웨이팅": r"(웨이팅|대기\s*(시간|줄|명단)|줄\s*(을\s*)?서|1시간\s*(넘게\s*)?(기다|대기))",
    },
    "closure": {
        "폐업/이전": r"(폐업\s*(했|하였|함|되었|된|한\s*곳|안내|공지)|영업\s*종료\s*(했|하였|됨|되었)|이전\s*(했|하였|함|되었)|(가게|매장|식당|카페)\s*(가\s*)?(문을\s*닫았|없어졌)|장기\s*휴업)",
    },
}
COMPILED = {g: {k: re.compile(p) for k, p in d.items()} for g, d in PAT.items()}


def is_sponsored(text):
    for m in SPONSOR_RE.finditer(text or ""):
        before = text[max(0, m.start() - 8): m.start()]
        after = text[m.end(): m.end() + 8]
        if NEG_BEFORE.search(before) or NEG_BEFORE.search(after):
            continue
        return True
    return False


def extract(text, src, date=None):
    """text 에서 패턴별 근거 (라벨, 인용문(±45자), src, date) 를 뽑는다. 라벨당 최대 2개."""
    out = {g: [] for g in COMPILED}
    if not text:
        return out
    for g, d in COMPILED.items():
        for label, rx in d.items():
            n = 0
            for m in rx.finditer(text):
                s = text[max(0, m.start() - 45): m.end() + 45].replace("\n", " ")
                # '계단 없' 류 부정은 계단(neg)에서 제외
                if label == "계단" and re.search(r"계단\s*(이|은|도)?\s*(없|안)", text[m.start(): m.end() + 6]):
                    continue
                win = text[max(0, m.start() - 30): m.end() + 30]
                # 계단이 나와도 엘리베이터가 함께 언급되면(엘리베이터나 계단을 이용해…) 주의 근거가 아님
                if label == "계단" and re.search(r"엘리베이터|엘베", win):
                    continue
                # 추측/소문/불확실 표현이 붙은 폐업 언급은 근거가 아님 ('폐업하지 않을까 싶네요')
                if g == "closure" and re.search(r"(않을까|싶네요|싶어요|할\s*것\s*같|같아요|같네요|듯\s|모르겠|소문|하려나)", win):
                    continue
                out[g].append({"label": label, "quote": s.strip(), "src": src, "date": date})
                n += 1
                if n >= 2:
                    break
    return out


def kind_of(category):
    c = category or ""
    if EXCL_RE.search(c):
        return None
    if CAFE_RE.search(c):
        return "cafe"
    if FOOD_RE.search(c):
        return "restaurant"
    return None


def rel_days(s):
    """'3일 전' '1주 전' '2개월 전' '어제' -> 일수. 모르면 None"""
    if not s:
        return None
    m = re.search(r"(\d+)\s*(분|시간|일|주|개월|달|년)\s*전", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return {"분": 0, "시간": 0, "일": n, "주": n * 7, "개월": n * 30, "달": n * 30, "년": n * 365}[u]
    if "어제" in s:
        return 1
    if re.search(r"\d{4}[.\-]\d{1,2}[.\-]\d{1,2}", s):
        y, mo, d = map(int, re.findall(r"\d+", s)[:3])
        from datetime import date as D
        try:
            return (D.today() - D(y, mo, d)).days
        except Exception:
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-detail", type=int, default=45)
    ap.add_argument("--max-drive", type=float, default=12.0)
    ap.add_argument("--blogs-per-place", type=int, default=2)
    a = ap.parse_args()

    hx, hy = geo.home()
    t0 = time.time()

    # 1) 발굴 ------------------------------------------------------------
    cands = {}
    for hint, q in QUERIES:
        try:
            items = npl.list_places(q, hx, hy)
        except npl.NaverBlocked as e:
            print("[중단] 네이버 차단 신호:", e); break
        for it in items:
            k = kind_of(it["category"])
            if not k or not it["id"]:
                continue
            c = cands.setdefault(it["id"], {**it, "kind": k, "queries": []})
            c["queries"].append(q)
        print(f"  발굴 '{q}': 누적 후보 {len(cands)}", flush=True)
    print(f"[1] 발굴 완료: 후보 {len(cands)}개 ({time.time()-t0:.0f}s)")

    # 2) 사전필터 + 직선거리 -------------------------------------------------
    pool = []
    for c in cands.values():
        c["straight_m"] = round(geo.haversine_m(hx, hy, c["x"], c["y"]))
        rv = c.get("visitor_review_count") or 0
        if c["straight_m"] <= 6500 and rv >= 100:
            pool.append(c)
    pool.sort(key=lambda c: -((c.get("visitor_review_count") or 0) + (c.get("blog_review_count") or 0)))
    pool = pool[:70]
    print(f"[2] 사전필터(직선 6.5km·방문자리뷰≥100) 통과 {len(pool)}개")

    # 3) 이동시간 -------------------------------------------------------------
    near = []
    for c in pool:
        try:
            c["drive"] = geo.drive(c["x"], c["y"])
        except qg.QuotaExceeded as e:
            print("[캡]", e); break
        if c["drive"]["min"] <= a.max_drive:
            if c["straight_m"] <= 3000:
                try:
                    c["walk"] = geo.walk(c["x"], c["y"])
                except qg.QuotaExceeded:
                    pass
            near.append(c)
    print(f"[3] 차량 {a.max_drive:.0f}분 이내 {len(near)}개 ({time.time()-t0:.0f}s)")
    near = near[: a.max_detail]

    # 4) 상세(네이버) + 5) 카카오 + 6) 블로그 본문 ------------------------------------
    results = []
    for i, c in enumerate(near, 1):
        rec = {"naver": {k: c.get(k) for k in ("id", "name", "category", "road_address", "address", "x", "y", "phone",
                                              "visitor_review_count", "visitor_review_score", "blog_review_count",
                                              "business_status", "business_desc")},
               "kind": c["kind"], "queries": sorted(set(c["queries"])), "straight_m": c["straight_m"],
               "drive": c.get("drive"), "walk": c.get("walk"), "evidence": {g: [] for g in COMPILED}, "notes": []}
        try:
            d = npl.detail(c["id"])
        except npl.NaverBlocked as e:
            print("[중단] 네이버 상세 차단:", e); break
        except qg.QuotaExceeded as e:
            print("[캡]", e); break
        rec["naver_detail"] = {k: d.get(k) for k in ("conveniences", "payment", "opening_hours", "micro_reviews", "menus", "missing_info")}
        rec["naver_detail"]["blog_reviews_listed"] = [{k: b.get(k) for k in ("title", "url", "date", "authorName")} for b in d.get("blog_reviews", [])]
        for b in d.get("blog_reviews", []):  # 발췌문(본문 일부)도 근거 후보
            ex = extract(b.get("contents"), f"naver-blog-excerpt:{b.get('url')}", b.get("date"))
            for g in ex:
                rec["evidence"][g] += ex[g]

        # 카카오 교차검증 + 패널
        try:
            v = kl.verify(c["name"], c["x"], c["y"])
        except qg.QuotaExceeded as e:
            print("[캡]", e); v = {"found": False}
        rec["kakao"] = v
        if v.get("found"):
            try:
                p = kl.panel(v["kakao_id"])
            except Exception as e:
                p = None; rec["notes"].append(f"카카오 패널 실패: {str(e)[:60]}")
            if p:
                ss = (p.get("kakaomap_review") or {}).get("score_set") or {}
                rec["kakao"].update({
                    "status": (p.get("summary") or {}).get("status"),
                    "rating": ss.get("average_score"), "review_count": ss.get("review_count"),
                    "headline": ((p.get("open_hours") or {}).get("headline") or {}).get("display_text"),
                    "facility_icons": [x.get("text") for x in ((p.get("place_add_info") or {}).get("ai_mate") or {}).get("store_facility_icons", [])],
                    "store_infos": ((p.get("place_add_info") or {}).get("ai_mate") or {}).get("store_infos", []),
                    "tags": (p.get("place_add_info") or {}).get("tags", []),
                    "subway": (p.get("find_way") or {}).get("subway"),
                })
                for rvw in ((p.get("kakaomap_review") or {}).get("reviews") or [])[:12]:
                    ex = extract(rvw.get("contents"), f"kakao-review:{rvw.get('review_id')}", (rvw.get("registered_at") or "")[:10])
                    for g in ex:
                        rec["evidence"][g] += ex[g]
                for si in rec["kakao"]["store_infos"]:
                    ex = extract(si.get("summary"), f"kakao-info:{v['kakao_id']}", None)
                    for g in ex:
                        rec["evidence"][g] += ex[g]

        # 블로그 본문 읽기(광고성 제외)
        rec["blogs_read"] = []
        read = 0
        for b in d.get("blog_reviews", []):
            if read >= a.blogs_per_place:
                break
            try:
                txt = npl.blog_text(b.get("url"))
            except npl.NaverBlocked as e:
                print("[중단] 블로그 차단:", e); txt = None; read = 99
            except qg.QuotaExceeded as e:
                print("[캡]", e); txt = None; read = 99
            if not txt:
                continue
            spon = is_sponsored(txt)
            rec["blogs_read"].append({"url": b.get("url"), "title": b.get("title"), "date": b.get("date"), "days_ago": rel_days(b.get("date")),
                                      "author": b.get("authorName"), "chars": len(txt), "sponsored": spon})
            if not spon:
                ex = extract(txt, f"naver-blog:{b.get('url')}", b.get("date"))
                for g in ex:
                    rec["evidence"][g] += ex[g]
            read += 1
        results.append(rec)
        print(f"  [{i}/{len(near)}] {c['name'][:18]:<18} ({c['kind']}) ★N{c.get('visitor_review_score')}/K{rec['kakao'].get('rating')} "
              f"{c['drive']['min']}분 상태 N:{c.get('business_status')} K:{rec['kakao'].get('status')} 블로그 {len(rec['blogs_read'])}편 ({time.time()-t0:.0f}s)", flush=True)
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "home": [hx, hy], "places": results},
                  open(os.path.join(OUT, "misa_raw.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n[완료] {len(results)}곳 수집, {time.time()-t0:.0f}s")
    for c_, u in qg.usage().items():
        if u["today"]:
            print(f"  캡 사용 {c_:<18} {u['today']}/{u['daily_cap']}")


if __name__ == "__main__":
    main()
