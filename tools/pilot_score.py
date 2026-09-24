"""게이트 -> 점수 -> 등급 (docs/SCORING.md, config/criteria.json 기준). 동네(local)와 당일 나들이(day_trip) 공용.

사용:
  python tools/pilot_score.py                                   # 동네 식당·카페 (기본)
  python tools/pilot_score.py --raw data/daytrip/raw.json --yt data/daytrip/youtube.json \
        --out data/daytrip/places.json --scope day_trip --kinds attraction --doc docs/DAYTRIP.md --title "당일 나들이"
"""
import argparse, json, math, os, re, statistics, sys, time
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_place as npl
from pilot_local import rel_days

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))
G, PS = CFG["gates"], CFG["place_score"]

B_WEIGHT = {"입식/테이블": 4, "주차": 3, "엘리베이터/1층/평지": 3, "넓고 여유": 2, "화장실 가까움": 1,
            "이동수단": 3, "쉼터·벤치·그늘": 2, "평탄·데크길": 3}
KIDS_LABELS = ["유아의자", "키즈메뉴", "놀이시설", "아이동반", "유모차", "체험·동물"]
SOFT_FOOD = re.compile(r"두부|순두부|죽|솥밥|찜|국밥|곰탕|설렁탕|칼국수|샤브|백숙|전골|수제비|국수|찌개|탕")
KIND_TITLE = {"restaurant": "식당", "cafe": "카페", "attraction": "체험·나들이"}


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


def est_admission(menus):
    """입장료 4인 추정: 성인 2 + 어린이 2 (네이버 메뉴/가격 항목의 성인·어린이 가격). 근거 없으면 None."""
    adult = child = None
    for m in menus or []:
        nm, pr = m.get("name") or "", to_int(m.get("price"))
        if not pr or pr <= 0:
            continue
        if adult is None and re.search(r"성인|어른|대인|일반", nm):
            adult = pr
        if child is None and re.search(r"어린이|소인|유아|초등", nm):
            child = pr
    if adult is None:
        return None
    ch = child if child is not None else adult
    return {"krw": 2 * adult + 2 * ch, "basis": f"입장료 성인 {adult:,}원 x2 + 어린이 {ch:,}원 x2 (네이버 등록 가격, 체험·식사 별도)",
            "sample": [(m.get("name"), to_int(m.get("price"))) for m in (menus or [])[:5]]}


def _d(e):
    dt = e.get("date")
    if not dt:
        return None
    return rel_days(dt if not re.match(r"\d{4}-", dt) else dt.replace("-", "."))


def score_place(p, yt, scope="local"):
    n, k, nd = p["naver"], p["kakao"], p.get("naver_detail") or {}
    kind = p["kind"]
    max_drive = CFG["scopes"][scope]["max_drive_min"]
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
    if kind == "attraction":
        neg.discard("웨이팅")  # 나들이 장소의 '대기번호'는 온라인 예약 대기(서 있는 부담 아님)
    b_raw = sum(B_WEIGHT.get(l, 0) for l in pos) - (5 if "좌식" in neg else 0) - (3 if "계단" in neg else 0) \
        - (3 if "엘리베이터 없음" in neg else 0) - (3 if "긴 보행" in neg else 0)
    mode_b = max(0, min(PS["mode_b_max"], b_raw))
    menu_names = " ".join((m.get("name") or "") for m in nd.get("menus") or [])
    soft = bool(SOFT_FOOD.search(menu_names + " " + (n.get("category") or ""))) and kind != "attraction"
    hard_neg = {"좌식", "계단", "엘리베이터 없음", "긴 보행"} & neg
    if "좌식" in neg and "입식/테이블" not in pos:
        verdict = "부적합(좌식 근거)"
    elif kind == "attraction":
        ok_move = {"이동수단", "평탄·데크길", "엘리베이터/1층/평지"} & pos
        if ok_move and not hard_neg:
            verdict = "적합 근거"
        elif hard_neg:
            verdict = "조건부(주의 근거)"
        else:
            verdict = "확인 필요"
    elif "입식/테이블" in pos and not hard_neg:
        verdict = "적합 근거"
    elif hard_neg:
        verdict = "조건부(주의 근거)"
    else:
        verdict = "확인 필요"
    unknown = []
    if kind == "attraction":
        if not ({"이동수단", "평탄·데크길", "엘리베이터/1층/평지", "계단", "긴 보행"} & (pos | neg)):
            unknown.append("경사·계단·걷는 거리")
        if "쉼터·벤치·그늘" not in pos:
            unknown.append("쉼터·벤치")
    else:
        if not ({"입식/테이블", "좌식"} & (pos | neg)):
            unknown.append("좌석 형태(입식/좌식)")
        if not ({"엘리베이터/1층/평지", "계단", "엘리베이터 없음"} & (pos | neg)):
            unknown.append("층·계단·엘리베이터")
    if "주차" not in pos:
        unknown.append("주차")
    family = min(PS["family_fit_max"], mode_a + mode_b)

    # 실용성
    dm = (p.get("drive") or {}).get("min")
    drive_pts = pts_from(PS["drive_points"], dm, hi_is_good=False) if dm is not None else 0
    cost = est_admission(nd.get("menus")) if kind == "attraction" else est_cost(nd.get("menus"))
    cost_pts = PS["cost_unknown_points"]
    if cost:
        cost_pts = pts_from(PS["cost_points"], cost["krw"], hi_is_good=False)
    practical = drive_pts + cost_pts

    total = round(reputation + evidence_pts + family + practical, 1)

    # 게이트
    fails, flags = [], []
    closure = [e for e in ev["closure"] if (_d(e) is None or _d(e) <= 90)]
    kst = k.get("status")
    if kst not in (None, "Y"):
        fails.append(f"카카오 영업상태 '{kst}'")
    if re.search(r"폐업|휴업", (n.get("business_status") or "") + (n.get("business_desc") or "")):
        fails.append(f"네이버 영업상태 '{n.get('business_status')}'")
    if closure:
        flags.append(f"폐업·이전 언급 {len(closure)}건 — 직접 확인 필요")
        if len({e["src"] for e in closure}) >= 2:  # 제외는 서로 다른 출처 2건 이상의 사실 언급일 때만
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
    if dm is None or dm > max_drive:
        fails.append(f"차량 {dm}분 > {max_drive}분")
    no_source = src_count < G["require_min_sources"]
    if no_source:
        flags.append("읽은 독립 출처 0 — 근거 수집 부족(품질 문제 아님), 추가 수집 필요")
    if not k.get("found"):
        flags.append("카카오 교차검증 실패(확인 필요)")
    if cost and kind == "restaurant" and cost["krw"] > G["max_meal_cost_4p_krw"]:
        flags.append(f"4인 추정 {cost['krw']:,}원 > 10만원(추정치)")
    if cost and kind == "attraction" and cost["krw"] > 60000:
        flags.append(f"입장료만 4인 약 {cost['krw']:,}원")
    if pooled and pooled >= G["high_rating_badge"]:
        flags.append("고평점(≥4.5)")
    if soft:
        flags.append("부드러운 음식 메뉴 있음")
    if "웨이팅" in neg and kind != "attraction":
        flags.append("웨이팅 언급(오래 서 있기 부담)")
    if "긴 보행" in neg:
        flags.append("걷는 거리 긺 언급")
    if dm is not None and dm > CFG["scopes"][scope].get("preferred_drive_min", 10**6):
        flags.append(f"차량 {round(dm)}분(선호 {CFG['scopes'][scope]['preferred_drive_min']}분 초과)")

    plan_notes, seen_pl = [], set()
    for e in ev.get("plan", []):
        key = (e["label"], e["quote"][:20])
        if key not in seen_pl:
            seen_pl.add(key)
            plan_notes.append(e)
    for lb in sorted({e["label"] for e in plan_notes}):
        flags.append(f"{lb} 언급 — 가기 전 확인")

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
    if tier in ("추천", "조건부") and no_source:
        tier = "근거부족"  # 읽은 독립 출처가 없으면 추천/조건부로 올리지 않음(제외도 아님)
    if tier == "추천" and kind == "attraction" and cost and cost["krw"] > 150000:
        tier = "조건부"  # 입장료 4인 15만원 초과는 예산 주의 -> 추천 상한 조건부
        flags.append("입장료 4인 15만원 초과 → 추천 상한 조건부")

    ds = [d for grp in ev.values() for e in grp if (d := _d(e)) is not None]
    ev_days = min(ds) if ds else None

    return {
        "id": f"naver-{n['id']}", "name": n["name"], "kind": kind,
        "naver": {"place_id": n["id"], "category": n.get("category"), "road_address": n.get("road_address"),
                  "x": n.get("x"), "y": n.get("y"), "score": nr, "reviews": nn, "blog_reviews": n.get("blog_review_count"),
                  "status": n.get("business_status"), "conveniences": nd.get("conveniences"), "phone": n.get("phone")},
        "kakao": {k_: k.get(k_) for k_ in ("found", "kakao_id", "kakao_url", "kakao_road_address", "rating", "review_count", "status", "dist_m", "facility_icons", "store_infos", "headline", "phone")},
        "rating": {"pooled": round(pooled, 2) if pooled else None, "bayes": round(bayes, 2) if bayes else None, "total_reviews": total_rev, "source": rate_src},
        "nav": npl.nav_links(n["name"], n["x"], n["y"], n["id"]),
        "drive": p.get("drive"), "walk": p.get("walk"),
        "price": {"est_meal_4p": cost, "menus_sample": (nd.get("menus") or [])[:6]},
        "family": {"mode_a": sorted(kids), "mode_b": {"positive": list(ev["b_pos"]), "negative": list(ev["b_neg"]),
                                                      "verdict": verdict, "unknown": unknown, "soft_food": soft}},
        "sources": {"blogs": p.get("blogs_read", []), "youtube": [{"video_id": m["video_id"], "link": m["link"], "t": m["t"], "quote": m["quote"], "where": m["where"]} for m in ymentions]},
        "scores": {"total": total, "tier": tier, "breakdown": {"reputation": reputation, "evidence": round(evidence_pts, 1), "family_fit": family, "practicality": practical},
                   "detail": {"rating_pts": rating_pts, "review_pts": round(review_pts, 1), "source_count": src_count, "mode_a": mode_a, "mode_b": mode_b, "drive_pts": drive_pts, "cost_pts": cost_pts},
                   "gates": {"pass": not fails, "failed": fails}},
        "flags": flags, "plan_notes": plan_notes[:4], "evidence_days_ago": ev_days, "verified_at": str(date.today()),
    }


def md_row(r):
    s, n, k = r["scores"], r["naver"], r["kakao"]
    dr, wk = r.get("drive") or {}, r.get("walk") or {}
    cost = (r["price"]["est_meal_4p"] or {}).get("krw")
    walk_txt = " · 도보 %s분" % wk["min"] if wk and wk.get("min") is not None else ""
    cost_txt = "{:,}원".format(cost) if cost else "-"
    return (f"| {s['tier']} {s['total']} | **{r['name']}** | {n['score'] or '-'}({n['reviews']}) / {k.get('rating') or '-'}({k.get('review_count') or '-'}) "
            f"| {dr.get('min', '-')}분{walk_txt} | {cost_txt} | {r['family']['mode_b']['verdict']} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/pilot/misa_raw.json")
    ap.add_argument("--yt", default="data/pilot/misa_youtube.json")
    ap.add_argument("--out", default="data/pilot/misa_places.json")
    ap.add_argument("--scope", default="local")
    ap.add_argument("--kinds", default="restaurant,cafe")
    ap.add_argument("--doc", default="docs/PILOT_MISA.md")
    ap.add_argument("--title", default="파일럿: 우리 동네 식당·카페")
    a = ap.parse_args()
    P = lambda x: os.path.join(ROOT, x)
    raw = json.load(open(P(a.raw), encoding="utf-8"))["places"]
    yt = json.load(open(P(a.yt), encoding="utf-8")) if os.path.exists(P(a.yt)) else {}
    res = [score_place(p, yt, a.scope) for p in raw]
    res.sort(key=lambda r: (-(r["scores"]["gates"]["pass"]), -r["scores"]["total"]))
    os.makedirs(os.path.dirname(P(a.out)), exist_ok=True)
    json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "scope": a.scope, "places": res}, open(P(a.out), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    L = [f"# {a.title} (자동 생성 — 사람이 검토용)", "",
         f"- 생성: {time.strftime('%Y-%m-%d %H:%M')} · 기준: docs/SCORING.md · 집: 미사강변아란티움 · 범위: {a.scope} (차량 {CFG['scopes'][a.scope]['max_drive_min']}분 이내)",
         f"- 수집 {len(res)}곳 → 게이트 통과 {sum(r['scores']['gates']['pass'] for r in res)}곳 "
         f"(추천 {sum(r['scores']['tier']=='추천' for r in res)} · 조건부 {sum(r['scores']['tier']=='조건부' for r in res)} · 근거부족 {sum(r['scores']['tier']=='근거부족' for r in res)} · 제외 {sum(r['scores']['tier']=='제외' for r in res)})", ""]
    for kind in a.kinds.split(","):
        title = KIND_TITLE.get(kind, kind)
        rows = [r for r in res if r["kind"] == kind]
        L += [f"## {title} ({len(rows)}곳)", "", "| 등급·점수 | 이름 | ★네이버(리뷰) / ★카카오(리뷰) | 차량·도보 | 4인 추정 | 모드B(파킨슨) |", "|---|---|---|---|---|---|"]
        L += [md_row(r) for r in rows] + [""]
        for r in [x for x in rows if x["scores"]["gates"]["pass"]][:12]:
            L += [f"### {r['name']} — {r['scores']['tier']} {r['scores']['total']}점",
                  f"- 분해: 평판 {r['scores']['breakdown']['reputation']} · 근거 {r['scores']['breakdown']['evidence']} · 가족적합 {r['scores']['breakdown']['family_fit']} · 실용 {r['scores']['breakdown']['practicality']}",
                  f"- 위치: {r['naver']['road_address']}",
                  f"- 내비: [네이버 내비]({r['nav']['app_navigation']}) · [네이버 장소]({r['nav']['web_place']}) · [카카오맵]({r['kakao'].get('kakao_url')})"]
            fam = r["family"]["mode_b"]
            for e in fam["positive"][:3]:
                L.append(f"- ✅ {e['label']}: “{e['quote']}” ({e['src'].split(':')[0]}, {e.get('date')})")
            for e in fam["negative"][:3]:
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
            L += [f"#### 제외된 {title} ({len(ex)}곳) — 사유", ""] + [f"- {r['name']}: {' / '.join(r['scores']['gates']['failed'])}" for r in ex] + [""]
    open(P(a.doc), "w", encoding="utf-8").write("\n".join(L))
    from collections import Counter
    print(f"[완료] {len(res)}곳 점수화 -> {a.out}, {a.doc}")
    print("등급 분포:", dict(Counter(r["scores"]["tier"] for r in res)))


if __name__ == "__main__":
    main()
