"""검증된 장소 데이터(data/pilot/misa_places.json)로 스마트폰용 단일 페이지 index.html 을 생성한다.

사용: python tools/build_site.py
- 데이터는 HTML 안에 JSON 으로 내장(외부 요청 없음). 근거 링크·네이버 내비 버튼·4인/6인 모드 토글.
- '제외'된 곳은 목록 대신 접힌 '제외된 곳과 이유'에만 표시(투명성).
"""
import json, os, re, sys, time

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
        "kids": p["family"]["mode_a"], "flags": p["flags"],
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
    for p in csrc["places"]:
        s = slim(p)
        s["kind"] = "camping"
        s["costb"] = (p["price"]["est_meal_4p"] or {}).get("basis")
        s["plan"] = [{"l": e["label"], "q": e["quote"], "k": ev(e)["k"], "u": ev(e)["u"], "d": e.get("date")} for e in p.get("plan_notes", [])]
        s["near"] = None
        camps.append(s)

# 게시 조건: 추천·조건부가 3곳 미만이면(근거 수집 중) 캠핑 탭을 내보내지 않는다 — 빈 탭/근거 없는 목록 노출 방지
if sum(1 for x in camps if x["tier"] in ("추천", "조건부")) < 3:
    if camps:
        print(f"[캠핑 탭 보류] 추천·조건부 {sum(1 for x in camps if x['tier'] in ('추천', '조건부'))}곳 < 3 — 근거 수집(블로그 읽기) 후 자동으로 열림")
    camps = []

CT = ("추천", "조건부", "근거부족", "제외")
data = {"generated": src["generated"], "verified": time.strftime("%Y-%m-%d"), "places": places, "trips": trips, "camps": camps,
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
