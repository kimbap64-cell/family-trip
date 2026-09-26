"""검증된 장소 데이터(data/pilot/misa_places.json)로 스마트폰용 단일 페이지 index.html 을 생성한다.

사용: python tools/build_site.py
- 데이터는 HTML 안에 JSON 으로 내장(외부 요청 없음). 근거 링크·네이버 내비 버튼·4인/6인 모드 토글.
- '제외'된 곳은 목록 대신 접힌 '제외된 곳과 이유'에만 표시(투명성).
"""
import json, os, re, sys, time, urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, "data", "pilot", "misa_places.json"), encoding="utf-8"))
raw = json.load(open(os.path.join(ROOT, "data", "pilot", "misa_raw.json"), encoding="utf-8"))["places"]
rawmap = {p["naver"]["id"]: p for p in raw}


def ev(e):
    t = e["src"].split(":")[0]
    kind = {"naver-blog": "블로그", "naver-blog-excerpt": "블로그", "kakao-review": "카카오 후기", "kakao-info": "카카오 안내"}.get(t, t)
    url = e["src"].split(":", 1)[1] if t.startswith("naver-blog") else None
    return {"l": e["label"], "q": e["quote"], "k": kind, "d": e.get("date"), "u": url}


def slim(p):
    r = rawmap[p["naver"]["place_id"]]
    fam = p["family"]["mode_b"]
    seen, pos, neg = set(), [], []
    for e in fam["positive"]:
        if e["label"] not in seen or len(pos) < 4:
            k = (e["label"], e["quote"][:30])
            if k not in seen:
                seen.add(k); pos.append(ev(e))
    for e in fam["negative"]:
        neg.append(ev(e))
    return {
        "id": p["naver"]["place_id"], "n": p["name"], "kind": p["kind"], "cat": (p["naver"].get("category") or ""),
        "tier": p["scores"]["tier"], "s": p["scores"]["total"], "bd": p["scores"]["breakdown"],
        "addr": p["naver"].get("road_address"), "tel": p["naver"].get("phone") or p["kakao"].get("phone"),
        "nr": p["naver"]["score"], "nn": p["naver"]["reviews"], "kr": p["kakao"].get("rating"), "kn": p["kakao"].get("review_count"),
        "rs": p["rating"]["source"], "rp": p["rating"]["pooled"],
        "dr": (p.get("drive") or {}).get("min"), "wk": (p.get("walk") or {}).get("min"),
        "cost": ((p["price"]["est_meal_4p"] or {}).get("krw")), "menus": [(m.get("name"), m.get("price")) for m in p["price"]["menus_sample"][:4]],
        "st": p["naver"].get("status"), "kst": p["kakao"].get("status"), "hl": p["kakao"].get("headline"),
        "bv": fam["verdict"], "unk": fam["unknown"], "soft": fam["soft_food"], "pos": pos[:4], "neg": neg[:3],
        "kids": p["family"]["mode_a"], "flags": p["flags"], "nw": bool(p["naver"].get("new_open")), "nws": p["naver"].get("new_open_since"),
        "park": [i.get("summary") for i in (p["kakao"].get("store_infos") or []) if i.get("title") == "주차"][:1],
        "conv": p["naver"].get("conveniences") or [], "fac": p["kakao"].get("facility_icons") or [],
        "blogs": [{"t": b.get("title"), "u": b["url"], "d": b.get("date"), "a": b.get("author"), "sp": b["sponsored"]} for b in p["sources"]["blogs"]],
        "yt": [{"l": y["link"], "q": y["quote"], "w": y["where"]} for y in p["sources"]["youtube"][:2]],
        "nav": {"app": p["nav"]["app_navigation"], "web": p["nav"]["web_place"], "kakao": p["kakao"].get("kakao_url")},
        "fails": p["scores"]["gates"]["failed"],
    }


places = [slim(p) for p in src["places"]]

# ---- 당일 나들이(있으면) ----
trips = []
tp = os.path.join(ROOT, "data", "daytrip", "places.json")
if os.path.exists(tp):
    tsrc = json.load(open(tp, encoding="utf-8"))
    traw = {p["naver"]["id"]: p for p in json.load(open(os.path.join(ROOT, "data", "daytrip", "raw.json"), encoding="utf-8"))["places"]}
    rawmap.update(traw)
    cp = os.path.join(ROOT, "data", "daytrip", "courses.json")
    cmap = {c["attraction_id"]: c for c in json.load(open(cp, encoding="utf-8"))["courses"]} if os.path.exists(cp) else {}

    def near(items):
        return [{"role": i["role"], "n": i["name"], "cat": i.get("category"), "addr": i.get("road_address"), "sc": i.get("score"), "rv": i.get("reviews"),
                 "dk": i.get("dist_km"), "tel": i.get("phone"), "kok": bool(i["kakao"].get("found")),
                 "nav": {"app": i["nav"]["app_navigation"], "web": i["nav"]["web_place"], "kakao": i["kakao"].get("kakao_url")}} for i in items]

    for p in tsrc["places"]:
        s = slim(p)
        s["kind"] = "attraction"
        s["costb"] = (p["price"]["est_meal_4p"] or {}).get("basis")
        s["plan"] = [{"l": e["label"], "q": e["quote"], "k": ev(e)["k"], "u": ev(e)["u"], "d": e.get("date")} for e in p.get("plan_notes", [])]
        c = cmap.get(p["naver"]["place_id"])
        s["near"] = {"meals": near(c["meals"]), "cafes": near(c["cafes"])} if c else None
        trips.append(s)

# ---- 키즈캠핑(있으면) ----
camps = []
cpp = os.path.join(ROOT, "data", "camping", "places.json")
if os.path.exists(cpp):
    csrc = json.load(open(cpp, encoding="utf-8"))
    rawmap.update({p["naver"]["id"]: p for p in json.load(open(os.path.join(ROOT, "data", "camping", "raw.json"), encoding="utf-8"))["places"]})
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from camp_types import camp_type
    for p in csrc["places"]:
        s = slim(p)
        s["kind"] = "camping"
        rp = rawmap[p["naver"]["place_id"]]["naver"]
        s["ctype"] = camp_type(p["name"], rp.get("promo") or "", p["naver"].get("category") or "")
        s["costb"] = (p["price"]["est_meal_4p"] or {}).get("basis")
        s["plan"] = [{"l": e["label"], "q": e["quote"], "k": ev(e)["k"], "u": ev(e)["u"], "d": e.get("date")} for e in p.get("plan_notes", [])]
        # 화장실·샤워실 근거(라벨당 1개, 개별 > 청결 > 온수 > 아쉬움 순)
        order = ["개별 화장실·샤워실", "화장실·샤워실 청결", "온수 잘 나옴", "화장실·샤워실 아쉬움"]
        seen_b, bath = set(), []
        for e in sorted(p["family"].get("bath", []), key=lambda e: order.index(e["label"])):
            if e["label"] not in seen_b:
                seen_b.add(e["label"])
                bath.append({"l": e["label"], "q": e["quote"], "k": ev(e)["k"], "u": ev(e)["u"], "d": e.get("date")})
        s["bath"] = bath
        s["bp"] = p["scores"]["detail"].get("bath_pts", 0)
        # 가격 확인용 외부 검색 링크(검색 URL 이므로 '직접 확인' 용도로만 표기 — 가격 데이터로 쓰지 않는다)
        s["cf"] = "https://camfit.co.kr/search/result?keyword=" + urllib.parse.quote(re.sub(r"\s*(캠핑장|글램핑|카라반).*$", "", p["name"]) or p["name"])
        s["near"] = None
        camps.append(s)

# 게시 조건: 추천·조건부가 3곳 미만이면(근거 수집 중) 캠핑 탭을 내보내지 않는다 — 빈 탭/근거 없는 목록 노출 방지
if sum(1 for x in camps if x["tier"] in ("추천", "조건부")) < 3:
    if camps:
        print(f"[캠핑 탭 보류] 추천·조건부 {sum(1 for x in camps if x['tier'] in ('추천', '조건부'))}곳 < 3 — 근거 수집(블로그 읽기) 후 자동으로 열림")
    camps = []

# ---- 이력(registry): 카드 배지 + '이력' 탭 (설계: docs/UPDATE_PLAN.md) ----
sys.path.insert(0, os.path.join(ROOT, "tools"))
import registry as rg
from datetime import date as _date
REGD = rg.load()
TODAY = _date.today()
NEW_DAYS, RECENT_DAYS = 30, 60


def _age(d):
    try:
        return (TODAY - _date.fromisoformat(d)).days
    except (TypeError, ValueError):
        return 9999


def hist(scope, pid):
    r = (REGD or {}).get("places", {}).get(f"{scope}:{pid}")
    if not r:
        return None
    ev = [e for e in r["events"] if e["type"] != "baseline"]
    return {"fs": r["first_seen"], "new": (not r["baseline"]) and _age(r["first_seen"]) <= NEW_DAYS,
            "ev": [{"d": e["date"], "t": e["type"], "x": e["text"]} for e in ev[-4:]][::-1],
            "tier_chg": next((e["text"] for e in reversed(ev) if e["type"] == "tier" and _age(e["date"]) <= NEW_DAYS), None)}


for _s, _scope in ((places, "local"), (trips, "trip"), (camps, "camp")):
    for _p in _s:
        _p["h"] = hist(_scope, _p["id"])

HIST = None
if REGD:
    recent, archive, pending = [], [], []
    for key, r in REGD["places"].items():
        for e in r["events"]:
            if e["type"] != "baseline" and _age(e["date"]) <= RECENT_DAYS:
                recent.append({"d": e["date"], "t": e["type"], "x": e["text"], "n": r["name"], "sc": r["scope"], "app": r["snap"].get("app"), "web": r["snap"].get("web")})
        if r["status"] in ("missing", "closed"):
            sn = r["snap"]
            archive.append({"n": r["name"], "sc": r["scope"], "st": r["status"], "ls": r["last_seen"], "tier": sn.get("tier"), "s": sn.get("score"),
                            "addr": sn.get("addr"), "web": sn.get("web"), "why": next((e["text"] for e in reversed(r["events"]) if e["type"] in ("missing", "closed")), "")})
    for key, v in REGD.get("pending", {}).items():
        pending.append({"n": v["name"], "sc": v["scope"], "cat": v.get("category"), "addr": v.get("addr"), "rv": v.get("reviews"), "rt": v.get("rating"),
                        "km": v.get("km"), "ff": v.get("first_found"), "web": v.get("web"), "nw": bool(v.get("new_open"))})
    recent.sort(key=lambda e: e["d"], reverse=True)
    HIST = {"since": REGD["baseline"], "recent": recent[:60], "archive": archive, "pending": pending, "discovered": REGD.get("discovered"),
            "total": len(REGD["places"]), "seen": len(REGD.get("seen", {}))}

CT = ("추천", "조건부", "근거부족", "제외")
data = {"generated": src["generated"], "verified": time.strftime("%Y-%m-%d"), "places": places, "trips": trips, "camps": camps, "hist": HIST,
        "counts": {t: sum(1 for x in places if x["tier"] == t) for t in CT},
        "tcounts": {t: sum(1 for x in trips if x["tier"] == t) for t in CT},
        "ccounts": {t: sum(1 for x in camps if x["tier"] == t) for t in CT}}

sp = os.path.join(ROOT, "data", "status_log.json")
if os.path.exists(sp):
    sl = json.load(open(sp, encoding="utf-8"))
    data["status"] = {"date": sl["date"], "checked": sl["checked"], "changes": len(sl["changes"]), "closures": len(sl["closures"])}
else:
    data["status"] = None

TEMPLATE = open(os.path.join(ROOT, "tools", "site_template.html"), encoding="utf-8").read()
html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
print(f"index.html 생성: {len(html)/1024:.0f}KB | 동네 {len(places)}곳 {data['counts']} | 나들이 {len(trips)}곳 {data['tcounts']} | 캠핑 {len(camps)}곳 {data['ccounts']}")
