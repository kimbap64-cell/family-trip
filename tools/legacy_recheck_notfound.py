"""reality_check에서 '못 찾음'으로 나온 항목을 검색어를 바꿔 재확인 (가짜로 단정하기 전 오탐 점검)."""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_place as npl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))
HX, HY = cfg["home"]["x"], cfg["home"]["y"]
rows = json.load(open(os.path.join(ROOT, "data", "legacy", "reality_check.json"), encoding="utf-8"))
nf = [r for r in rows if not r["place_id"] or r["match"] < 0.6]
print("재확인 대상:", len(nf))

GENERIC = ["오토캠핑장", "캠핑장", "캠핑랜드", "글램핑", "키즈", "&", "놀이터", "수생식물원", "생태숲"]
out = []
for r in nf:
    base = r["query"]
    core = base
    for g in GENERIC:
        core = core.replace(g, " ")
    core = re.sub(r"^(하남|남양주|양평|가평|광주|용인|여주|포천|이천|파주|연천|시흥|인천)\s+", "", core.strip()).strip()
    variants = [core + " 캠핑" if r["kind"] == "camp" else core, base]
    seen = []
    for q in variants:
        if not q.strip() or q in seen:
            continue
        seen.append(q)
        try:
            cands = npl.list_places(q, HX, HY)
        except npl.NaverBlocked as e:
            print("[중단]", e); raise SystemExit
        top = [(c["name"], c.get("category"), c.get("visitor_review_score"), c.get("visitor_review_count")) for c in cands[:3]]
        sims = [npl.match_score(core, c["name"]) for c in cands]
        best = max(sims) if sims else 0
        out.append({"legacy": r["legacy_name"], "kind": r["kind"], "q": q, "n": len(cands), "best_sim": best, "top3": top})
        print(f"[{r['kind']}] {r['legacy_name'][:20]:<20} | q='{q}' | 후보 {len(cands)} | 최고유사 {best:.2f} | {top[:2]}", flush=True)

json.dump(out, open(os.path.join(ROOT, "data", "legacy", "recheck_notfound.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
