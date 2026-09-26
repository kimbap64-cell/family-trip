"""수집 시 별점 출처 시험 — 목록 별점이 0.0/None 이어도 상세 페이지 별점을 써야 한다 (2026-09-26 캠핑 별점 0.0 덮어쓰기 버그 재현).
외부 호출 없이 가짜 detail/kakao 로 검증.  python tools/test_collect_rating.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_place as npl
import kakao_local as kl
import collect

fails = total = 0
def check(name, cond):
    global fails, total
    total += 1
    print(("PASS" if cond else "FAIL"), "-", name); fails += (not cond)

def fake_detail(score, count=1234, blog=555):
    return lambda pid: {"name": "테스트", "visitor_review_score": score, "visitor_review_count": count, "blog_review_count": blog,
                        "conveniences": [], "payment": None, "opening_hours": None, "menus": [], "micro_reviews": None,
                        "missing_info": None, "blog_reviews": []}

kl.verify = lambda *a, **k: {"found": False}
base = {"id": "1", "name": "테스트", "category": "캠핑,야영장", "x": 127.0, "y": 37.5, "queries": [], "seeds": []}

npl.detail = fake_detail(4.84)
r = collect.collect_one({**base, "visitor_review_score": 0.0, "visitor_review_count": 10}, "camping", blogs_per_place=0)
check("목록 별점 0.0 + 상세 4.84 -> 4.84 사용", r["naver"]["visitor_review_score"] == 4.84)
check("상세 리뷰 수 우선", r["naver"]["visitor_review_count"] == 1234)

npl.detail = fake_detail(None, count=None, blog=None)
r = collect.collect_one({**base, "visitor_review_score": 0.0, "visitor_review_count": 10}, "camping", blogs_per_place=0)
check("상세도 별점 없음 -> None (0.0 이 별점으로 남지 않음)", r["naver"]["visitor_review_score"] is None)
check("상세에 리뷰 수 없으면 목록 값 유지", r["naver"]["visitor_review_count"] == 10)

npl.detail = fake_detail(None)
r = collect.collect_one({**base, "visitor_review_score": 4.5, "visitor_review_count": 10}, "attraction", blogs_per_place=0)
check("상세 별점 없고 목록 별점 4.5 -> 목록 값 유지", r["naver"]["visitor_review_score"] == 4.5)
print(f"\n결과: {total - fails} 통과 / {fails} 실패")
sys.exit(1 if fails else 0)
