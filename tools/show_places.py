"""점수화된 places.json 을 한 줄씩 요약 출력 (검토용).  python tools/show_places.py data/daytrip/places.json"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1], encoding="utf-8"))["places"]
for p in d:
    s, fam = p["scores"], p["family"]["mode_b"]
    cost = (p["price"]["est_meal_4p"] or {}).get("krw")
    print(f"{s['tier']:<4} {s['total']:>5} | {p['name'][:14]:<14} | 차 {round(p['drive']['min'])}분 | {p['rating']['source'] or '-'} {p['rating']['pooled']} "
          f"| 입장4인 {cost} | B:{fam['verdict']} | 확인필요:{','.join(fam['unknown'])} | 유튜브 {len(p['sources']['youtube'])} | {'; '.join(s['gates']['failed'])[:44]}")
