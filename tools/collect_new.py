"""'새로 문 연 곳'(네이버 새로오픈 표시) 검토 대기 장소의 근거를 수집해 각 범위 raw.json 에 추가한다.

  python tools/collect_new.py [--max 8] [--blogs 2]

- 대상: registry['pending'] 중 new_open=True + 이력에 있는 신규오픈 장소인데 수집기가 raw 를 다시 만들며 빠진 것(복원).
- 장소당: 네이버 상세 1 + 카카오 검색·패널 + 블로그 본문 최대 3 (collect_one — 캐시·quota_guard 캡 적용). 차량 시간이 범위를 넘으면
  수집하지 않고 registry['rejected'] 에 사유를 남긴다.
- 점수화는 pilot_score 가 한다(신규 오픈: 리뷰 하한 완화·등급 상한 조건부). 근거(독립 출처)가 없으면 '근거부족' 이라 추천되지 않는다.
- 네이버 차단 신호 -> 즉시 중단(종료코드 2), 캡 -> 그때까지 저장하고 정상 종료.
"""
import argparse, json, os, sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import geo
import registry as rg
from collect import collect_one

ROOT = rg.ROOT
RAW = {"local": "data/pilot/misa_raw.json", "trip": "data/daytrip/raw.json", "camp": "data/camping/raw.json"}
MAX_DRIVE = {"local": 12, "trip": 90, "camp": 65}
CFG = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--blogs", type=int, default=2)
    a = ap.parse_args()
    reg = rg.load()
    if not reg:
        print("[중단] registry 없음"); return 1
    raws = {sc: json.load(open(os.path.join(ROOT, p), encoding="utf-8")) for sc, p in RAW.items() if os.path.exists(os.path.join(ROOT, p))}
    have = {sc: {p["naver"]["id"] for p in d["places"]} for sc, d in raws.items()}
    todo = []
    for key, v in reg["pending"].items():
        if v.get("new_open") and v["id"] not in have.get(v["scope"], set()):
            todo.append((key, v["cand"], v["kind"], v["scope"]))
    restore = []
    for key, r in reg["places"].items():  # 수집기가 raw 를 다시 만들어 빠진 신규오픈 장소 복원
        if r.get("new_open_since") and r.get("cand") and r["id"] not in have.get(r["scope"], set()) and r["status"] != "closed":
            restore.append((key, r["cand"], r["kind"], r["scope"]))
    # 별점이 높고 리뷰가 많은 순으로 (복원은 먼저)
    todo.sort(key=lambda t: (-(t[1].get("visitor_review_score") or 0), -(t[1].get("visitor_review_count") or 0)))
    queue = restore + todo[: a.max]
    print(f"[collect_new] 수집 대상 {len(queue)}곳 (복원 {len(restore)} · 신규 {min(len(todo), a.max)}/{len(todo)})")
    hx, hy = geo.home()
    done = rej = 0
    code = 0
    for i, (key, c, kind, sc) in enumerate(queue, 1):
        c = dict(c)
        try:
            c["straight_m"] = round(geo.haversine_m(hx, hy, c["x"], c["y"]))
            c["drive"] = geo.drive(c["x"], c["y"])
            if c["drive"]["min"] > MAX_DRIVE[sc]:
                reg.setdefault("rejected", {})[key] = f"차량 {c['drive']['min']:.0f}분 > {MAX_DRIVE[sc]}분"
                reg["pending"].pop(key, None)
                rej += 1
                print(f"  [{i}/{len(queue)}] {c['name'][:20]} — {reg['rejected'][key]} (범위 밖)")
                continue
            if sc == "local" and c["straight_m"] <= 3000:
                try:
                    c["walk"] = geo.walk(c["x"], c["y"])
                except qg.QuotaExceeded:
                    pass
            rec = collect_one(c, kind, blogs_per_place=a.blogs)
        except npl.NaverBlocked as e:
            print("[중단] 네이버 차단 신호:", e); code = 2; break
        except qg.QuotaExceeded as e:
            print("[캡] 오늘 한도 도달 — 여기까지 저장:", e); break
        rec["naver"]["new_opening"] = True
        raws[sc]["places"].append(rec)
        have[sc].add(c["id"])
        json.dump(raws[sc], open(os.path.join(ROOT, RAW[sc]), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rg.save(reg)
        done += 1
        print(f"  [{i}/{len(queue)}] {c['name'][:20]:20} 리뷰 {c.get('visitor_review_count')} ★{c.get('visitor_review_score')} 🚗{c['drive']['min']:.0f}분 블로그 {len(rec['blogs_read'])}편")
    rg.save(reg)
    print(f"[collect_new] 수집 {done}곳 · 범위 밖 {rej}곳 · 남은 신규 대기 {sum(1 for v in reg['pending'].values() if v.get('new_open') and v['id'] not in have.get(v['scope'], set()))}곳")
    return code


if __name__ == "__main__":
    sys.exit(main())
