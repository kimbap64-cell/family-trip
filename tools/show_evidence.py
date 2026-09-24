"""장소별 모드B 근거 문장 출력(판독 검증용).  python tools/show_evidence.py data/daytrip/places.json 이름1,이름2"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1], encoding="utf-8"))["places"]
names = sys.argv[2].split(",")
for p in d:
    if not any(n in p["name"] for n in names):
        continue
    f = p["family"]["mode_b"]
    print(f"\n### {p['name']} — {p['scores']['tier']} {p['scores']['total']} | 모드B: {f['verdict']} | 카카오 {p['kakao'].get('found')} {p['kakao'].get('rating')} | 출처 {p['scores']['detail']['source_count']}")
    for grp, sign in (("negative", "⚠️"), ("positive", "✅")):
        seen = set()
        for e in f[grp]:
            k = (e["label"], e["quote"][:25])
            if k in seen:
                continue
            seen.add(k)
            print(f"  {sign} {e['label']} [{e['src'].split(':')[0]} {e.get('date')}] {e['quote']}")
    print("  플래그:", p["flags"])
