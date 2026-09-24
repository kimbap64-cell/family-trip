"""파일럿 3단계: 게이트 -> 점수 -> 등급 (docs/SCORING.md, config/criteria.json 기준).

입력: data/pilot/misa_raw.json, (선택) data/pilot/misa_youtube.json
출력: data/pilot/misa_places.json (DATA_MODEL 구조), docs/PILOT_MISA.md (사람이 검토하는 표)
"""
import json, math, os, re, statistics, sys, time
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_place as npl
from pilot_local import rel_days

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIL = os.path.join(ROOT, "data", "pilot")
CFG = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))
G, PS = CFG["gates"], CFG["place_score"]

B_WEIGHT = {"입식/테이블": 4, "주차": 3, "엘리베이터/1층/평지": 3, "넓고 여유": 2, "화장실 가까움": 1}
KIDS_LABELS = ["유아의자", "키즈메뉴", "놀이시설", "아이동반", "유모차"]
SOFT_FOOD = re.compile(r"두부|순두부|죽|솥밥|찜|국밥|곰탕|설렁탕|칼국수|샤브|백숙|전골|수제비|국수|찌개|탕")


def pts_from(table, value, hi_is_good=True):
    for lim, p in table:
        if (value >= lim) if hi_is_good else (value <= lim):
            return p
    return 0


def to_int(s):
    try:
        return int(re.sub(r"[^\d]", "", str(s)))
    except ValueError:
        return None


def est_cost(menus):
    prices = [to_int(m.get("price")) for m in (menus or [])[:10]]
    prices = [p for p in prices if p and 2500 <= p <= 150000]
    if len(prices) < 2:
        return None
    return {"krw": int(round(4 * statistics.median(prices[:8]), -2)), "basis": f"메뉴판 상위 {min(8, len(prices))}개 가격 중앙값 x4 (추정, 신뢰도 낮음)",
            "sample": [(m.get("name"), to_int(m.get("price"))) for m in (menus or [])[:5]]}


def score_place(p, yt):
    n, k, nd = p["naver"], p["kakao"], p.get("naver_detail") or {}
    kind = p["kind"]
    nr, nn = n.get("visitor_review_score"), n.get("visitor_review_count") or 0
    kr, kn = k.get("rating"), k.get("review_count") or 0
    # 별점 출처: 네이버 우선. 없으면 카카오+보정(카카오가 평균 0.8 낮고 표본이 작음 — 파일럿 측정)
    if nr:
        pooled, rate_n, rate_src = nr, nn, "네이버"
    elif kr:
        pooled, rate_n, rate_src = min(5.0, kr + PS["kakao_rating_offset"]), kn, f"카카오(+{PS['kakao_rating_offset']} 보정)"
    else:
        pooled, rate_n, rate_src = None, 0, None
    total_rev = nn + kn
    prior, w = PS["bayes_prior_rating"], PS["bayes_prior_weight"]
    bayes = (pooled * rate_n + prior * w) / (rate_n + w) if pooled else None
    rating_pts = pts_from(PS["rating_points"], bayes) if bayes else 0
    review_pts = min(PS["review_scale_max"], 2.5 * math.log10(total_rev + 1))
    reputation = round(rating_pts + review_pts, 1)

    # 출처: 광고성 제외 블로그 + 유튜브 채널
    blogs = [b for b in p.get("blogs_read", []) if not b["sponsored"]]
    blog_authors = {b.get("author") for b in blogs}
    ymentions = [m for m in yt.get("mentions", []) if m["place_id"] == n["id"]]
    yvideos = {v["id"]: v for v in yt.get("videos", [])}
    ychannels = {yvideos[m["video_id"]]["channel_id"] for m in ymentions if m["video_id"] in yvideos and m["where"] == "description"}
    src_count = len(blog_authors) + len(ychannels)
    src_pts = PS["source_count_points"].get(str(min(src_count, 3)), 0) if src_count else 0
    best_s = max([yvideos[m["video_id"]]["credibility"]["total"] for m in ymentions if m["video_id"] in yvideos] or [0])
    ages = [b["days_ago"] for b in blogs if b.get("days_ago") is not None]
    blog_bonus = (3 if ages and min(ages) <= 30 else 2 if ages and min(ages) <= 90 else 1) if blogs else 0
    bonus = round(min(PS["best_source_bonus_max"], max(best_s / 100 * 5, blog_bonus)), 1)
    evidence_pts = src_pts + bonus

    # 가족 적합도
    ev = p["evidence"]
    kids = {e["label"] for e in ev["kids"]}
    if "유아의자" in (nd.get("conveniences") or []) or any("유아" in (i or "") for i in k.get("facility_icons", [])):
        kids.add("유아의자")
    mode_a = min(PS["mode_a_max"], 3 * len(kids & set(KIDS_LABELS)))
    pos = {e["label"] for e in ev["b_pos"]}
    if "주차" in (nd.get("conveniences") or []) or "주차가능" in k.get("facility_icons", []):
        pos.add("주차")
    neg = {e["label"] for e in ev["b_neg"]}
    b_raw = sum(B_WEIGHT.get(l, 0) for l in pos) - (5 if "좌식" in neg else 0) - (3 if "계단" in neg else 0) - (3 if "엘리베이터 없음" in neg else 0)
    mode_b = max(0, min(PS["mode_b_max"], b_raw))
    menu_names = " ".join((m.get("name") or "") for m in nd.get("menus") or [])
    soft = bool(SOFT_FOOD.search(menu_names + " " + (n.get("category") or "")))
    if "좌식" in neg and "입식/테이블" not in pos:
        verdict = "부적합(좌식 근거)"
    elif "입식/테이블" in pos and not ({"좌식", "계단", "엘리베이터 없음"} & neg):
        verdict = "적합 근거"
    elif {"계단", "엘리베이터 없음", "좌식"} & neg:
        verdict = "조건부(주의 근거)"
    else:
        verdict = "확인 필요"
    unknown = []
    if not ({"입식/테이블", "좌식"} & (pos | neg)):
        unknown.append("좌석 형태(입식/좌식)")
    if "주차" not in pos:
        unknown.append("주차")
    if not ({"엘리베이터/1층/평지", "계단", "엘리베이터 없음"} & (pos | neg)):
        unknown.append("층·계단·엘리베이터")
    family = min(PS["family_fit_max"], mode_a + mode_b)

    # 실용성
    dm = (p.get("drive") or {}).get("min")
    drive_pts = pts_from(PS["drive_points"], dm, hi_is_good=False) if dm is not None else 0
    cost = est_cost(nd.get("menus"))
    cost_pts = PS["cost_unknown_points"]
    if cost:
        cost_pts = pts_from(PS["cost_points"], cost["krw"], hi_is_good=False)
    practical = drive_pts + cost_pts

    total = round(reputation + evidence_pts + family + practical, 1)

    # 게이트
    fails, flags = [], []
    days_limit = 90
    closure = []
    for e in ev["closure"]:
        d = None
        if e.get("date"):
            d = rel_days(e["date"]) if not re.match(r"\d{4}-", e["date"]) else rel_days(e["date"].replace("-", "."))
        if d is None or d <= days_limit:
            closure.append(e)
    kst = k.get("status")
    if kst not in (None, "Y"):
        fails.append(f"카카오 영업상태 '{kst}'")
    if re.search(r"폐업|휴업", (n.get("business_status") or "") + (n.get("business_desc") or "")):
        fails.append(f"네이버 영업상태 '{n.get('business_status')}'")
    if closure:
        flags.append(f"폐업·이전 언급 {len(closure)}건 — 직접 확인 필요")
        # 제외는 '서로 다른 출처 2건 이상의 사실 언급'일 때만. 1건은 표시만(오판 방지: 추측·부분시설 언급이 섞임)
        if len({e["src"] for e in closure}) >= 2:
            fails.append("최근 90일 내 폐업/이전 사실 언급 2건 이상")
    min_rate = G["min_naver_rating"].get(kind, 4.2)
    if rate_src and rate_src != "네이버":
        min_rate = round(min_rate - PS["kakao_only_gate_relax"], 2)
        flags.append(f"네이버 별점 없음 → {rate_src}, 기준 {min_rate}로 완화")
    if pooled is None:
        flags.append("별점 없음(네이버·카카오 모두)")
    elif bayes is not None and bayes < min_rate - 0.05 and pooled < min_rate:
        fails.append(f"별점({rate_src}) {pooled:.2f} < {min_rate}")
    if total_rev < G["min_review_count"].get(kind, 100):
        fails.append(f"리뷰 {total_rev} < {G['min_review_count'].get(kind, 100)}")
    if dm is None or dm > CFG["scopes"]["local"]["max_drive_min"]:
        fails.append(f"차량 {dm}분 > {CFG['scopes']['local']['max_drive_min']}분")
    if src_count < G["require_min_sources"]:
        fails.append("독립 출처 0")
    if not k.get("found"):
        flags.append("카카오 교차검증 실패(확인 필요)")
    if cost and cost["krw"] > G["max_meal_cost_4p_krw"] and kind == "restaurant":
        flags.append(f"4인 추정 {cost['krw']:,}원 > 10만원(추정치)")
    if pooled and pooled >= G["high_rating_badge"]:
        flags.append("고평점(≥4.5)")
    if kind == "restaurant" and soft:
        flags.append("부드러운 음식 메뉴 있음")
    if "웨이팅" in neg:
        flags.append("웨이팅 언급(오래 서 있기 부담)")

    tier_cfg = CFG["recommend_tiers"]
    if fails:
        tier = "제외"
    elif total >= tier_cfg["recommended"]["min_score"]:
        tier = "추천"
    elif total >= tier_cfg["conditional"]["min_score"]:
        tier = "조건부"
    else:
        tier = "근거부족"
    if tier == "추천" and (pooled is None or not k.get("found")):
        tier = "조건부"  # 별점/교차검증이 빠졌으면 추천 상한 = 조건부

    # 최신 근거 날짜
    ds = []
    for grp in ev.values():
        for e in grp:
            if e.get("date"):
                d = rel_days(e["date"] if not re.match(r"\d{4}-", e["date"]) else e["date"].replace("-", "."))
                if d is not None:
                    ds.append(d)
    ev_days = min(ds) if ds else None

    return {
        "id": f"naver-{n['id']}", "name": n["name"], "kind": kind,
        "naver": {"place_id": n["id"], "category": n.get("category"), "road_address": n.get("road_address"),
                  "x": n.get("x"), "y": n.get("y"), "score": nr, "reviews": nn, "blog_reviews": n.get("blog_review_count"),
                  "status": n.get("business_status"), "conveniences": nd.get("conveniences"), "phone": n.get("phone")},
        "kakao": {k_: k.get(k_) for k_ in ("found", "kakao_id", "kakao_url", "kakao_road_address", "rating", "review_count", "status", "dist_m", "facility_icons", "store_infos", "headline")},
        "rating": {"pooled": round(pooled, 2) if pooled else None, "bayes": round(bayes, 2) if bayes else None, "total_reviews": total_rev, "source": rate_src},
        "nav": npl.nav_links(n["name"], n["x"], n["y"], n["id"]),
        "drive": p.get("drive"), "walk": p.get("walk"),
        "price": {"est_meal_4p": cost, "menus_sample": (nd.get("menus") or [])[:6]},
        "family": {"mode_a": sorted(kids), "mode_b": {"positive": [e for e in ev["b_pos"]], "negative": [e for e in ev["b_neg"]],
                                                      "verdict": verdict, "unknown": unknown, "soft_food": soft}},
        "sources": {"blogs": p.get("blogs_read", []), "youtube": [{"video_id": m["video_id"], "link": m["link"], "t": m["t"], "quote": m["quote"], "where": m["where"]} for m in ymentions]},
        "scores": {"total": total, "tier": tier, "breakdown": {"reputation": reputation, "evidence": round(evidence_pts, 1), "family_fit": family, "practicality": practical},
                   "detail": {"rating_pts": rating_pts, "review_pts": round(review_pts, 1), "source_count": src_count, "mode_a": mode_a, "mode_b": mode_b, "drive_pts": drive_pts, "cost_pts": cost_pts},
                   "gates": {"pass": not fails, "failed": fails}},
        "flags": flags, "evidence_days_ago": ev_days, "verified_at": str(date.today()),
    }


def md_row(r):
    s, n, k = r["scores"], r["naver"], r["kakao"]
    dr, wk = r.get("drive") or {}, r.get("walk") or {}
    cost = (r["price"]["est_meal_4p"] or {}).get("krw")
    return (f"| {s['tier']} {s['total']} | **{r['name']}** | {n['score'] or '-'}({n['reviews']}) / {k.get('rating') or '-'}({k.get('review_count') or '-'}) "
            f"| {dr.get('min', '-')}분 · 도보 {wk.get('min', '-')}분 | {f'{cost:,}원' if cost else '-'} | {r['family']['mode_b']['verdict']} |")


def main():
    raw = json.load(open(os.path.join(PIL, "misa_raw.json"), encoding="utf-8"))["places"]
    yp = os.path.join(PIL, "misa_youtube.json")
    yt = json.load(open(yp, encoding="utf-8")) if os.path.exists(yp) else {}
    res = [score_place(p, yt) for p in raw]
    res.sort(key=lambda r: (-(r["scores"]["gates"]["pass"]), -r["scores"]["total"]))
    json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "scope": "local(차량 12분 이내)", "places": res},
              open(os.path.join(PIL, "misa_places.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 마크다운 검토표 ----
    L = ["# 파일럿: 우리 동네 식당·카페 (자동 생성 — 사람이 검토용)", "",
         f"- 생성: {time.strftime('%Y-%m-%d %H:%M')} · 기준: docs/SCORING.md · 집: 미사강변아란티움 · 범위: 차량 12분 이내",
         f"- 수집 {len(res)}곳 → 게이트 통과 {sum(r['scores']['gates']['pass'] for r in res)}곳 "
         f"(추천 {sum(r['scores']['tier']=='추천' for r in res)} · 조건부 {sum(r['scores']['tier']=='조건부' for r in res)} · 근거부족 {sum(r['scores']['tier']=='근거부족' for r in res)} · 제외 {sum(r['scores']['tier']=='제외' for r in res)})", ""]
    for kind, title in (("restaurant", "식당"), ("cafe", "카페")):
        rows = [r for r in res if r["kind"] == kind]
        L += [f"## {title} ({len(rows)}곳)", "", "| 등급·점수 | 이름 | ★네이버(리뷰) / ★카카오(리뷰) | 차량·도보 | 4인 추정 | 모드B(파킨슨) |", "|---|---|---|---|---|---|"]
        L += [md_row(r) for r in rows]
        L += [""]
        for r in [x for x in rows if x["scores"]["gates"]["pass"]][:10]:
            L += [f"### {r['name']} — {r['scores']['tier']} {r['scores']['total']}점",
                  f"- 분해: 평판 {r['scores']['breakdown']['reputation']} · 근거 {r['scores']['breakdown']['evidence']} · 가족적합 {r['scores']['breakdown']['family_fit']} · 실용 {r['scores']['breakdown']['practicality']}",
                  f"- 위치: {r['naver']['road_address']} · 네이버 상태 {r['naver']['status']} · 카카오 상태 {r['kakao'].get('status')} ({r['kakao'].get('headline')})",
                  f"- 내비: [네이버 내비]({r['nav']['app_navigation']}) · [네이버 장소]({r['nav']['web_place']}) · [카카오맵]({r['kakao'].get('kakao_url')})"]
            fam = r["family"]["mode_b"]
            for e in (fam["positive"][:3]):
                L.append(f"- ✅ {e['label']}: “{e['quote']}” ({e['src'].split(':')[0]}, {e.get('date')})")
            for e in (fam["negative"][:3]):
                L.append(f"- ⚠️ {e['label']}: “{e['quote']}” ({e['src'].split(':')[0]}, {e.get('date')})")
            if fam["unknown"]:
                L.append(f"- ❓ 확인 필요: {', '.join(fam['unknown'])}")
            if r["flags"]:
                L.append(f"- 표시: {' · '.join(r['flags'])}")
            for b in r["sources"]["blogs"]:
                L.append(f"- 📝 블로그{'(광고성 제외)' if b['sponsored'] else ''}: [{(b.get('title') or '')[:40]}]({b['url']}) — {b.get('author')} · {b.get('date')}")
            for y in r["sources"]["youtube"][:2]:
                L.append(f"- ▶️ 유튜브 {y['where']}: [{(y['quote'] or '')[:50]}]({y['link']})")
            L.append("")
        ex = [r for r in rows if not r["scores"]["gates"]["pass"]]
        if ex:
            L += [f"#### 제외된 {title} ({len(ex)}곳) — 사유", ""]
            for r in ex:
                L.append(f"- {r['name']}: {' / '.join(r['scores']['gates']['failed'])}")
            L.append("")
    open(os.path.join(ROOT, "docs", "PILOT_MISA.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"[완료] {len(res)}곳 점수화 -> data/pilot/misa_places.json, docs/PILOT_MISA.md")
    from collections import Counter
    print("등급 분포:", dict(Counter(r["scores"]["tier"] for r in res)))


if __name__ == "__main__":
    main()
