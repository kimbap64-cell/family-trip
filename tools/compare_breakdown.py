"""git HEAD 의 places.json 과 현재를 항목별로 비교 (점수 급변 원인 추적).  python tools/compare_breakdown.py data/camping/places.json 양주르,인더풀"""
import json, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
path, names = sys.argv[1], sys.argv[2].split(",")
old = {p["naver"]["place_id"]: p for p in json.loads(subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True, encoding="utf-8").stdout)["places"]}
new = json.load(open(path, encoding="utf-8"))["places"]
for p in new:
    if not any(n in p["name"] for n in names):
        continue
    o = old.get(p["naver"]["place_id"])
    print(f"\n### {p['name']}")
    for label, x in (("이전(HEAD)", o), ("현재", p)):
        if not x:
            print(" ", label, "없음"); continue
        s = x["scores"]
        print(f"  {label}: {s['tier']} {s['total']} | 분해 {s['breakdown']} | 세부 {s['detail']}")
        print(f"          별점 {x['rating']} | 네이버 {x['naver']['score']}({x['naver']['reviews']}) 카카오 {x['kakao'].get('rating')}({x['kakao'].get('review_count')}) found={x['kakao'].get('found')}")
        print(f"          가족 kids={x['family']['mode_a']} b_verdict={x['family']['mode_b']['verdict']} | 출처 블로그 {len(x['sources']['blogs'])} 유튜브 {len(x['sources']['youtube'])} | flags {x['flags']}")
