"""1차본(Antigravity) 항목이 실제로 존재하는지 네이버 플레이스로 점검하고 집->목적지 운전시간(OSRM)을 계산."""
import json, os, re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
import naver_place as npl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))
HX, HY = cfg["home"]["x"], cfg["home"]["y"]

legacy_courses = json.load(open(os.path.join(ROOT, "data", "legacy", "courses_22_unverified.json"), encoding="utf-8"))["courses"]
backup = json.load(open(os.path.join(ROOT, "..", "antigravity_원본백업_여행", "trips_data.json"), encoding="utf-8"))

items = []
for c in legacy_courses:
    nm = re.split(r"\s*&\s*", c["spot1"]["name"])[0]
    items.append(("course", c["id"], nm, c.get("duration_min"), c["spot1"]["name"]))
for c in backup["camping_sites"]:
    nm = re.sub(r"\s*\(.*?\)", "", c["name"])
    items.append(("camp", c["id"], nm, c.get("duration_min"), c["name"]))
for cat, arr in backup["local_misa_spots"].items():
    for i, s in enumerate(arr, 1):
        nm = re.sub(r"\s*\(.*?\)", "", s["name"]).replace(" or ", " ").strip()
        items.append((f"misa_{cat}", f"{cat}-{i}", nm, None, s["name"]))


def drive(x, y):
    try:
        r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{HX},{HY};{x},{y}",
                         params={"overview": "false"}, timeout=20).json()
        rt = r["routes"][0]
        return round(rt["duration"] / 60), round(rt["distance"] / 1000, 1)
    except Exception:
        return None, None


out, t0 = [], time.time()
for n, (kind, iid, nm, claimed, orig) in enumerate(items, 1):
    try:
        res = npl.resolve(nm, HX, HY)
    except npl.NaverBlocked as e:
        print("[중단] 네이버 차단 신호:", e)
        break
    p = res["place"] or {}
    dmin, dkm = (drive(p["x"], p["y"]) if p.get("x") else (None, None))
    if p.get("x"):
        time.sleep(1.0)
    row = {
        "kind": kind, "id": iid, "legacy_name": orig, "query": nm, "match": res["match"],
        "found_name": p.get("name"), "category": p.get("category"), "place_id": p.get("id"),
        "road_address": p.get("road_address"), "x": p.get("x"), "y": p.get("y"),
        "score": p.get("visitor_review_score"), "reviews": p.get("visitor_review_count"),
        "blog_reviews": p.get("blog_review_count"), "status": p.get("business_status"),
        "drive_min": dmin, "drive_km": dkm, "legacy_claimed_min": claimed,
    }
    out.append(row)
    print(f"{n:>2}/{len(items)} [{kind}] {orig[:22]:<22} -> {str(row['found_name'])[:20]:<20} match={row['match']:.2f} "
          f"★{row['score']} ({row['reviews']}) {dmin}분 (1차본 {claimed})", flush=True)

json.dump(out, open(os.path.join(ROOT, "data", "legacy", "reality_check.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[완료] {len(out)}건, {time.time()-t0:.0f}s")
