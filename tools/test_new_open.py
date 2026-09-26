"""신규 오픈 기준 시험: 리뷰 하한 완화·등급 상한(조건부)·표시. 실제 데이터의 한 곳을 변형해 pilot_score.score_place 로 확인."""
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot_score as ps

ROOT = ps.ROOT
raw = json.load(open(os.path.join(ROOT, "data", "pilot", "misa_raw.json"), encoding="utf-8"))["places"]
yt = json.load(open(os.path.join(ROOT, "data", "pilot", "misa_youtube.json"), encoding="utf-8"))
base = next(p for p in raw if p["kind"] == "restaurant" and p["naver"].get("visitor_review_score") and len(p.get("blogs_read", [])) >= 1)
p = copy.deepcopy(base)
p["naver"]["visitor_review_count"] = 40          # 300 미만, 신규 하한(20) 이상
p["naver"]["visitor_review_score"] = 4.9
p["kakao"]["review_count"] = 0
ok = True


def check(c, m):
    global ok
    print(("OK  " if c else "FAIL"), m)
    ok &= bool(c)


ps.NEW_OPEN = {}
r0 = ps.score_place(p, yt, "local")
check(any("리뷰" in f for f in r0["scores"]["gates"]["failed"]) and r0["scores"]["tier"] == "제외", "신규 표시 없으면 리뷰 40건은 하한(300) 미달로 제외")
ps.NEW_OPEN = {f"local:{p['naver']['id']}": "2026-09-20"}
r1 = ps.score_place(p, yt, "local")
check(not any("리뷰" in f for f in r1["scores"]["gates"]["failed"]), "신규 오픈이면 리뷰 40건도 통과(하한 20)")
check(r1["naver"]["new_open"] and any("신규 오픈" in f for f in r1["flags"]), "신규 오픈 표시·경고 문구")
check(r1["scores"]["tier"] != "추천", "신규 오픈은 추천 상한 = 조건부")
check(r1["rating"]["bayes"] > r0["rating"]["bayes"], "표본이 작은 신규는 사전분포 영향을 줄여 평가")
p["naver"]["visitor_review_count"] = 8
r2 = ps.score_place(p, yt, "local")
check(any("리뷰" in f for f in r2["scores"]["gates"]["failed"]), "신규여도 리뷰 8건은 하한(20) 미달")
ps.NEW_OPEN = {f"local:{p['naver']['id']}": "2025-01-01"}
r3 = ps.score_place(p, yt, "local")
check(not r3["naver"]["new_open"], "신규 표시 180일이 지나면 일반 기준으로 복귀")
sys.exit(0 if ok else 1)
