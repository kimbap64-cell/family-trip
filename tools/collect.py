"""장소 1곳의 근거 수집 (네이버 상세 + 카카오 검증/별점/리뷰 + 블로그 본문 읽기 + 근거 문장 추출). 캐시·캡 적용.
pilot_local.py 의 루프 본문을 재사용 가능한 함수로 옮긴 것 (동네·나들이·캠핑 공용).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import kakao_local as kl
from pilot_local import COMPILED, extract, is_sponsored, rel_days


def new_rec(c, kind):
    return {"naver": {k: c.get(k) for k in ("id", "name", "category", "road_address", "address", "x", "y", "phone",
                                          "visitor_review_count", "visitor_review_score", "blog_review_count", "business_status", "business_desc",
                                          "min_price", "promo", "micro_review")},
            "kind": kind, "queries": sorted(set(c.get("queries", []))), "straight_m": c.get("straight_m"),
            "drive": c.get("drive"), "walk": c.get("walk"), "evidence": {g: [] for g in COMPILED}, "notes": [], "seeds": c.get("seeds", [])}


def collect_one(c, kind, blogs_per_place=2, kakao_panel=True):
    """실패/캡이면 (rec 또는 None, 사유) 를 돌려준다. 네이버 차단 신호는 예외로 전파."""
    rec = new_rec(c, kind)
    d = npl.detail(c["id"])  # NaverBlocked / QuotaExceeded 는 호출자가 처리
    rec["naver_detail"] = {k: d.get(k) for k in ("conveniences", "payment", "opening_hours", "micro_reviews", "menus", "missing_info")}
    rec["naver_detail"]["blog_reviews_listed"] = [{k: b.get(k) for k in ("title", "url", "date", "authorName")} for b in d.get("blog_reviews", [])]
    for b in d.get("blog_reviews", []):
        ex = extract(b.get("contents"), f"naver-blog-excerpt:{b.get('url')}", b.get("date"))
        for g in ex:
            rec["evidence"][g] += ex[g]

    try:
        # 큰 공원·관광지는 네이버/카카오 대표 좌표가 수백 m~1km 다를 수 있어 허용 거리를 넓힘
        v = kl.verify(c["name"], c["x"], c["y"], max_m=1500 if kind == "attraction" else 250)
    except qg.QuotaExceeded:
        v = {"found": False}
        rec["notes"].append("카카오 검색 캡")
    rec["kakao"] = v
    if v.get("found") and kakao_panel:
        try:
            p = kl.panel(v["kakao_id"])
        except qg.QuotaExceeded:
            p = None
            rec["notes"].append("카카오 패널 캡(내일 재실행 시 보강)")
        except Exception as e:
            p = None
            rec["notes"].append(f"카카오 패널 실패: {str(e)[:60]}")
        if p:
            ss = (p.get("kakaomap_review") or {}).get("score_set") or {}
            am = (p.get("place_add_info") or {}).get("ai_mate") or {}
            rec["kakao"].update({
                "status": (p.get("summary") or {}).get("status"), "rating": ss.get("average_score"), "review_count": ss.get("review_count"),
                "headline": ((p.get("open_hours") or {}).get("headline") or {}).get("display_text"),
                "facility_icons": [x.get("text") for x in am.get("store_facility_icons", [])], "store_infos": am.get("store_infos", []),
                "tags": (p.get("place_add_info") or {}).get("tags", []), "subway": (p.get("find_way") or {}).get("subway")})
            for rvw in ((p.get("kakaomap_review") or {}).get("reviews") or [])[:12]:
                ex = extract(rvw.get("contents"), f"kakao-review:{rvw.get('review_id')}", (rvw.get("registered_at") or "")[:10])
                for g in ex:
                    rec["evidence"][g] += ex[g]
            for si in rec["kakao"]["store_infos"]:
                ex = extract(si.get("summary"), f"kakao-info:{v['kakao_id']}", None)
                for g in ex:
                    rec["evidence"][g] += ex[g]

    rec["blogs_read"] = []
    read = 0
    for b in d.get("blog_reviews", []):
        # 광고성 글은 근거로 못 쓰므로 '광고 아닌 글'이 blogs_per_place 편 모일 때까지 읽는다(최대 3편)
        if sum(1 for x in rec["blogs_read"] if not x["sponsored"]) >= blogs_per_place or len(rec["blogs_read"]) >= 3:
            break
        try:
            txt = npl.blog_text(b.get("url"))
        except qg.QuotaExceeded:
            rec["notes"].append("블로그 본문 캡(내일 재실행 시 보강)")
            break
        if not txt:
            continue
        spon = is_sponsored(txt)
        rec["blogs_read"].append({"url": b.get("url"), "title": b.get("title"), "date": b.get("date"), "days_ago": rel_days(b.get("date")),
                                  "author": b.get("authorName"), "chars": len(txt), "sponsored": spon})
        if not spon:
            ex = extract(txt, f"naver-blog:{b.get('url')}", b.get("date"))
            for g in ex:
                rec["evidence"][g] += ex[g]
        read += 1
    return rec
