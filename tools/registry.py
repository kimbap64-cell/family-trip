"""장소 이력 저장소 — 목록이 사라지지 않고 쌓이도록 (설계: docs/UPDATE_PLAN.md).

  python tools/registry.py            # 오늘 점수화 결과와 비교해 data/registry.json 갱신 (같은 날 재실행해도 중복 없음)

규칙
- 키 = "<범위>:<네이버 place_id>" (범위: local 동네 / trip 당일 나들이 / camp 키즈캠핑). 이름이 바뀌어도(리뉴얼·상호 변경) 같은 장소로 이어진다.
- 절대 지우지 않는다. 이번 점수화 목록에서 빠진 곳은 status='missing'(순위 밀림 등 — 폐업 아님), 폐업·영업종료 신호는 'closed'.
- 이벤트: baseline(이력 기록 시작 시점 목록) / new(새로 목록에 들어옴) / tier(등급 변화) / rating(별점 ±0.1 이상) /
         closed / reopened / renamed / missing / back
- 처음 실행하면 지금 목록 전체를 baseline 으로 등록(그래서 '새로 추가' 배지가 전부 뜨지 않는다).
"""
import json, os, re, sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "registry.json")
SOURCES = {"local": "data/pilot/misa_places.json", "trip": "data/daytrip/places.json", "camp": "data/camping/places.json"}
CLOSED_RE = re.compile(r"영업상태|폐업/이전")
MAX_EVENTS = 40


def load():
    if os.path.exists(REG):
        return json.load(open(REG, encoding="utf-8"))
    return None


def save(reg):
    os.makedirs(os.path.dirname(REG), exist_ok=True)
    json.dump(reg, open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)


def current():
    """오늘 점수화 결과 -> {키: 스냅샷}"""
    out = {}
    for scope, rel in SOURCES.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding="utf-8"))["places"]:
            n, s = r["naver"], r["scores"]
            out[f"{scope}:{n['place_id']}"] = {
                "scope": scope, "id": n["place_id"], "name": r["name"], "kind": r["kind"],
                "snap": {"tier": s["tier"], "score": s["total"], "rating": n.get("score") or (r.get("rating") or {}).get("pooled"),
                         "reviews": n.get("reviews"), "addr": n.get("road_address"), "cat": n.get("category"),
                         "dr": (r.get("drive") or {}).get("min"), "app": r["nav"]["app_navigation"], "web": r["nav"]["web_place"]},
                "closed": s["tier"] == "제외" and any(CLOSED_RE.search(f) for f in s["gates"]["failed"]),
            }
    return out


def new_open_map():
    """{키: 신규오픈 표시를 처음 본 날} — 점수화가 리뷰 기준 완화·표시에 쓴다."""
    reg = load()
    out = {}
    if reg:
        for k, r in reg["places"].items():
            if r.get("new_open_since"):
                out[k] = r["new_open_since"]
        for k, v in reg.get("pending", {}).items():
            if v.get("new_open"):
                out[k] = v.get("first_found")
    return out


def add_event(rec, day, typ, text):
    ev = {"date": day, "type": typ, "text": text}
    if not any(e["date"] == day and e["type"] == typ and e["text"] == text for e in rec["events"]):
        rec["events"].append(ev)
        del rec["events"][:-MAX_EVENTS]
        return True
    return False


def update(today=None):
    today = today or str(date.today())
    reg = load()
    cur = current()
    first = reg is None
    if first:
        reg = {"version": 1, "baseline": today, "places": {}, "pending": {}}
    P = reg["places"]
    added = changed = 0
    for key, c in cur.items():
        rec = P.get(key)
        if rec is None:
            rec = P[key] = {"scope": c["scope"], "id": c["id"], "name": c["name"], "kind": c["kind"], "first_seen": today,
                            "last_seen": today, "status": "closed" if c["closed"] else "active", "baseline": first, "snap": c["snap"], "events": [], "names": []}
            if first:
                add_event(rec, today, "baseline", f"이력 기록 시작 — {c['snap']['tier']} {c['snap']['score']}점")
            else:
                add_event(rec, today, "new", f"새로 목록에 들어옴 — {c['snap']['tier']} {c['snap']['score']}점")
                added += 1
            pv = reg["pending"].pop(key, None)
            if pv and pv.get("new_open"):  # 검토 대기에서 승격 — 신규 오픈 표시·후보 정보(수집기가 raw 를 다시 만들어도 복원용) 유지
                rec["new_open_since"] = pv.get("first_found") or today
                rec["cand"] = pv.get("cand")
                add_event(rec, today, "new", f"🌱 새로 문 연 곳으로 목록에 들어옴 — {c['snap']['tier']} {c['snap']['score']}점")
                rec["events"] = [e for e in rec["events"] if not (e["type"] == "new" and e["date"] == today and "🌱" not in e["text"])]
            continue
        old = rec["snap"]
        new = c["snap"]
        if rec["status"] == "missing":
            add_event(rec, today, "back", "다시 점검 목록에 들어옴"); changed += 1
        if c["name"] != rec["name"] and c["name"] not in rec.get("names", []):  # 발굴 단계에서 이미 기록한 이름 변경은 중복 기록 안 함
            rec["names"] = sorted(set(rec.get("names", []) + [rec["name"]]))
            add_event(rec, today, "renamed", f"이름이 '{rec['name']}' → '{c['name']}'(으)로 바뀜 — 리뉴얼·상호 변경일 수 있어요"); changed += 1
            rec["name"] = c["name"]
        if old.get("tier") != new["tier"]:
            add_event(rec, today, "tier", f"{old.get('tier')} → {new['tier']} ({old.get('score')}→{new['score']}점)"); changed += 1
        if old.get("rating") and new.get("rating") and abs(new["rating"] - old["rating"]) >= 0.1:
            add_event(rec, today, "rating", f"별점 {old['rating']:.2f} → {new['rating']:.2f}"); changed += 1
        if c["closed"] and rec["status"] != "closed":
            add_event(rec, today, "closed", "폐업·영업종료 신호 — 목록에서 제외됨(이력은 남김)"); changed += 1
        elif not c["closed"] and rec["status"] == "closed":
            add_event(rec, today, "reopened", "영업 신호가 다시 확인됨"); changed += 1
        rec["status"] = "closed" if c["closed"] else "active"
        rec["last_seen"] = today
        rec["snap"] = new
    for key, rec in P.items():
        if key not in cur and rec["status"] == "active":
            rec["status"] = "missing"
            add_event(rec, today, "missing", "이번 점검 목록에서 빠짐(후보 순위 밀림 등 — 폐업 뜻은 아님)"); changed += 1
    reg["updated"] = today
    save(reg)
    st = {s: sum(1 for r in P.values() if r["status"] == s) for s in ("active", "missing", "closed")}
    print(f"[registry] {'기준선 생성' if first else '갱신'} {today}: 장소 {len(P)}곳 {st} | 신규 {added} · 변화 {changed} · 검토대기 {len(reg['pending'])}")
    return reg


if __name__ == "__main__":
    update()
