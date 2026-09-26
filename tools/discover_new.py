"""새로 생긴 장소·이름이 바뀐 장소 발굴 (주 1회, 목록 검색만 — 상세·블로그는 읽지 않는다).

  python tools/discover_new.py

- 동네·나들이·캠핑 각 발굴 검색어를 '새로 조회'(캐시 무시)해서 이력 저장소(data/registry.json)에 없는 장소를 찾는다.
- 통과 기준(리뷰 수·거리·별점 하한)을 넘는 새 장소는 registry['pending'](검토 대기)에 넣는다.
  네이버 '새로오픈' 표시(newOpening)가 붙은 곳은 리뷰 하한을 낮춰(gates.min_review_count_new_open) 이미 본 후보 목록과 무관하게 검토 대기에 올린다(new_open=True). **추천으로 바로 올리지 않는다** —
  다음 수집(run_all --fetch / Claude 세션)에서 블로그·카카오 근거를 읽고 점수화한 뒤에야 목록에 오른다.
- 이미 이력에 있는 장소의 이름이 바뀌었으면 renamed 이벤트를 기록한다(리뉴얼·상호 변경).
- 네이버 차단 신호(403/429/구조 변경)면 즉시 중단하고 종료코드 2 (이력은 그대로).
"""
import json, os, re, sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import geo
import registry as rg

npl.FRESH = os.environ.get("DISCOVER_USE_CACHE") != "1"  # 기본: 캐시를 읽지 않고 새로 조회 (새 장소를 찾는 것이 목적). 시험용으로만 캐시 사용
ROOT = rg.ROOT
CFG = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))["gates"]
MAX_NEW = 40  # 범위당 검토 대기 최대(넘치면 리뷰 많은 순)


def scopes():
    import pilot_local as pl
    import daytrip_collect as dc
    import camp_collect as cc
    def local_ok(it):
        k = pl.kind_of(it.get("category"))
        return k and (it, k, 6500, "local")
    def trip_ok(it):
        cat = it.get("category") or ""
        if dc.EXCL_RE.search(cat) or not dc.ATTR_RE.search(cat + " " + (it.get("name") or "")):
            return None
        return (it, "attraction", 68000, "trip")
    def camp_ok(it):
        txt = (it.get("category") or "") + " " + (it.get("name") or "")
        if cc.CAMP_RE.search(txt) and not cc.EXCL_RE.search(txt) and "부속시설" not in (it.get("category") or ""):
            return (it, "camping", 55000, "camp")
        return None
    return [("local", [q for _, q in pl.QUERIES], local_ok), ("trip", dc.QUERIES, trip_ok), ("camp", cc.QUERIES, camp_ok)]


def main():
    hx, hy = geo.home()
    reg = rg.load()
    if reg is None:
        print("[중단] data/registry.json 이 없음 — 먼저 python tools/registry.py 로 기준선을 만든다")
        return 1
    today = str(date.today())
    P, pend = reg["places"], reg["pending"]
    found = {}  # 키 -> 후보
    renamed = 0
    try:
        for scope, queries, ok in scopes():
            for q in queries:
                for it in npl.list_places(q, hx, hy):
                    if not it.get("id"):
                        continue
                    r = ok(it)
                    if not r:
                        continue
                    it, kind, max_m, sc = r
                    key = f"{sc}:{it['id']}"
                    rec = P.get(key)
                    if rec:  # 이미 이력에 있음 -> 이름 변경·신규오픈 표시만 확인
                        if it.get("new_opening") and not rec.get("new_open_since"):
                            rec["new_open_since"] = today
                            rg.add_event(rec, today, "new_open", "🌱 네이버 '새로오픈' 표시가 붙음")
                        if it["name"] and it["name"] != rec["name"] and it["name"] not in rec.get("names", []):
                            rec["names"] = sorted(set(rec.get("names", []) + [rec["name"]]))
                            rg.add_event(rec, today, "renamed", f"이름이 '{rec['name']}' → '{it['name']}'(으)로 바뀜 — 리뉴얼·상호 변경일 수 있어요")
                            rec["name"] = it["name"]
                            renamed += 1
                        continue
                    if key in reg.get("rejected", {}):
                        continue  # 이미 검토해 범위 밖(차량 시간 초과 등)으로 정한 곳
                    if it.get("x") is None or it.get("y") is None:
                        continue
                    d = geo.haversine_m(hx, hy, it["x"], it["y"])
                    rv = it.get("visitor_review_count") or 0
                    is_new = bool(it.get("new_opening"))
                    min_rv = (CFG["min_review_count_new_open"] if is_new else CFG["min_review_count"]).get(kind, 300)
                    if d > max_m or rv < min_rv:
                        continue
                    sc_rate = it.get("visitor_review_score")
                    if sc_rate and sc_rate < CFG["min_naver_rating"].get(kind, 4.2) - 0.3 and (rv >= 10 or not is_new):
                        continue  # 별점이 분명히 낮은 곳은 검토 대기에도 올리지 않는다(리뷰 10건 미만 신규는 별점 표본이 무의미해 예외)
                    nav = npl.nav_links(it["name"], it["x"], it["y"], it["id"])
                    found[key] = {"scope": sc, "id": it["id"], "name": it["name"], "kind": kind, "category": it.get("category"),
                                  "addr": it.get("road_address"), "rating": sc_rate, "reviews": rv, "km": round(d / 1000, 1),
                                  "app": nav["app_navigation"], "web": nav["web_place"], "new_open": is_new, "cand": it}
            print(f"  [{scope}] 검색 {len(queries)}건 완료 — 누적 새 후보 {sum(1 for k in found if k.startswith(scope))}", flush=True)
    except npl.NaverBlocked as e:
        print("[중단] 네이버 차단 신호 — 이번 발굴은 저장하지 않음:", e)
        return 2
    except qg.QuotaExceeded as e:
        print("[캡] 발굴 중단 — 이번 발굴은 저장하지 않음:", e)
        return 2
    # '지금까지 본 후보'(seen) 기준선: 첫 발굴 때 기준을 통과한 모든 후보(점검 대상 밖의 미평가 후보 포함)를 기록한다.
    # 그 뒤 처음 나타난 곳(새로 문을 열었거나 리뷰 기준을 새로 넘은 곳)만 '새 후보'로 올린다.
    new = 0
    if "seen" not in reg:
        reg["seen"] = {k: today for k in found}
        print(f"[discover] 기준선: 점검 대상 밖의 미평가 후보 {len(found)}곳을 '이미 본 후보'로 기록 (다음 발굴부터 새로 나타난 곳만 새 후보)")
    else:
        for k, v in sorted(found.items(), key=lambda kv: -kv[1]["reviews"]):
            if (k not in reg["seen"] or v["new_open"]) and k not in pend and sum(1 for x in pend.values() if x["scope"] == v["scope"]) < MAX_NEW:
                v["first_found"] = today
                v["last_seen"] = today
                pend[k] = v
                new += 1
            reg["seen"].setdefault(k, today)
        for k, v in pend.items():
            if k in found:
                v["last_seen"] = today
    reg["discovered"] = today
    rg.save(reg)
    print(f"[discover] 새 검토 대기 {new}곳 · 이름 변경 {renamed}곳 · 검토 대기 합계 {len(pend)}곳 · 이미 본 후보 {len(reg['seen'])}곳")
    for k, v in sorted(pend.items(), key=lambda kv: -kv[1]["reviews"])[:15]:
        print(f"   {k:22} {v['name'][:22]:22} 리뷰 {v['reviews']:>6} ★{v['rating'] or '-'} {v['km']}km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
