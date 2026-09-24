"""git HEAD 에 커밋된 places.json 과 작업 트리의 places.json 등급을 비교 (코드 변경이 결과를 바꿨는지 회귀 확인).
python tools/compare_tiers.py data/daytrip/places.json"""
import json, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
old = json.loads(subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True, encoding="utf-8").stdout)["places"]
new = json.load(open(path, encoding="utf-8"))["places"]
om = {p["naver"]["place_id"]: p for p in old}
diff = 0
for p in new:
    o = om.get(p["naver"]["place_id"])
    if not o:
        print("신규:", p["name"]); diff += 1; continue
    if (o["scores"]["tier"], o["scores"]["total"]) != (p["scores"]["tier"], p["scores"]["total"]):
        print(f"변경: {p['name'][:16]:<16} {o['scores']['tier']} {o['scores']['total']} -> {p['scores']['tier']} {p['scores']['total']}"); diff += 1
print(f"비교 {len(new)}곳 중 다른 곳 {diff}곳")
