"""네이버 플레이스 조회기 (공개 페이지, 소량·저속).

- list_places(query, x, y)   : pcmap 목록 페이지의 __APOLLO_STATE__ 에서 장소 후보 추출
- resolve(name, x, y)        : 이름과 가장 잘 맞는 후보 1개 + 일치도
- detail(place_id)           : m.place 상세에서 편의시설/결제/영업시간/메뉴/블로그후기 추출
- nav_links(name, x, y, id)  : 네이버 지도 길안내 링크 (앱 스킴 + 웹)

규칙: 요청 간 >=2초, 캐시 우선, 캡차/차단 신호 감지 시 즉시 예외(우회 금지).
"""
import hashlib, json, os, random, re, sys, time, urllib.parse, difflib

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "naver")
os.makedirs(CACHE, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
H = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://m.place.naver.com/"}
APPNAME = "kr.familytrip.misa"
_last = [0.0]
FRESH = os.environ.get("TRIP_FRESH") == "1"  # 1이면 캐시를 읽지 않고 새로 조회(주간 상태 점검용). 결과는 캐시에 다시 저장


class NaverBlocked(Exception):
    pass


def _get(url, params=None, cache_key=None):
    """캐시 -> 저속 GET. 차단 신호면 NaverBlocked."""
    cp = None
    if cache_key:
        cp = os.path.join(CACHE, hashlib.md5(cache_key.encode()).hexdigest() + ".html")
        if os.path.exists(cp) and not FRESH:
            return open(cp, encoding="utf-8").read()
    import quota_guard as qg  # 캐시 미스일 때만 하드캡 차감
    qg.charge("naver_place", 1)
    wait = 2.0 + random.random() * 1.5 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, params=params, headers=H, timeout=25)
    _last[0] = time.time()
    r.encoding = "utf-8"
    if r.status_code in (403, 429) or "captcha" in r.url.lower():
        raise NaverBlocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {url}")
    if cp:
        open(cp, "w", encoding="utf-8").write(r.text)
    return r.text


def apollo(html):
    i = html.find("__APOLLO_STATE__")
    if i < 0:
        return None
    j = html.find("{", i)
    depth, instr, esc = 0, False, False
    for k in range(j, len(html)):
        ch = html[k]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
        else:
            if ch == '"':
                instr = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(html[j:k + 1])
    return None


def _num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def list_places(query, x=None, y=None):
    params = {"query": query}
    if x and y:
        params.update({"x": x, "y": y})
    html = _get("https://pcmap.place.naver.com/place/list", params, cache_key=f"list|{query}|{x}|{y}")
    st = apollo(html)
    if st is None:
        raise NaverBlocked("APOLLO_STATE 없음 (차단/구조 변경 의심)")
    out = []
    for k, v in st.items():
        if not k.startswith("PlaceListBusinessesItem:"):
            continue
        bh = v.get("newBusinessHours") or {}
        out.append({
            "id": v.get("id"), "name": v.get("name"), "category": v.get("category"),
            "road_address": v.get("roadAddress"), "address": v.get("address"),
            "x": _num(v.get("x")), "y": _num(v.get("y")),
            "phone": v.get("phone") or v.get("virtualPhone"),
            "visitor_review_count": int(_num(v.get("visitorReviewCount")) or 0) if v.get("visitorReviewCount") else None,
            "visitor_review_score": _num(v.get("visitorReviewScore")),
            "blog_review_count": int(_num(v.get("blogCafeReviewCount")) or 0) if v.get("blogCafeReviewCount") else None,
            "business_status": bh.get("status"), "business_desc": bh.get("description"),
            "distance": v.get("distance"),
        })
    return out


def _norm(s):
    return re.sub(r"[\s\(\)\[\]·\-_,./]+", "", (s or "").lower())


def match_score(query_name, cand_name):
    a, b = _norm(query_name), _norm(cand_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        r = max(r, 0.85)
    return round(r, 3)


def resolve(name, x=None, y=None, query=None):
    """가장 잘 맞는 후보. 부속시설(카테고리 '부속시설')은 이름이 정확히 같을 때만."""
    cands = list_places(query or name, x, y)
    best, best_s = None, 0.0
    for c in cands:
        s = match_score(name, c["name"])
        if c.get("category") == "부속시설" and s < 0.99:
            s *= 0.5
        if s > best_s:
            best, best_s = c, s
    return {"query": query or name, "match": round(best_s, 3), "place": best, "n_candidates": len(cands)}


def detail(place_id):
    html = _get(f"https://m.place.naver.com/place/{place_id}/home", cache_key=f"detail|{place_id}")
    st = apollo(html)
    if not st:
        raise NaverBlocked("상세 APOLLO_STATE 없음")
    base = st.get(f"PlaceDetailBase:{place_id}") or {}
    menus, blogs = [], []
    for k, v in st.items():
        if k.startswith(f"Menu:{place_id}"):
            menus.append({kk: v.get(kk) for kk in ("name", "price", "description", "recommend") if kk in v})
        elif k.startswith("FsasReview:"):
            blogs.append({kk: v.get(kk) for kk in ("title", "url", "date", "type", "authorName", "contents") if kk in v})
    return {
        "id": place_id, "name": base.get("name"), "category": base.get("category"),
        "road_address": base.get("roadAddress"), "address": base.get("address"),
        "phone": base.get("phone") or base.get("virtualPhone"),
        "conveniences": base.get("conveniences"), "payment": base.get("paymentInfo"),
        "opening_hours": base.get("openingHours"), "micro_reviews": base.get("microReviews"),
        "visitor_review_count": base.get("visitorReviewsTotal"), "visitor_review_score": base.get("visitorReviewsScore"),
        "blog_review_count": base.get("cafeBlogReviewsTotal"),
        "coordinate": base.get("coordinate"), "menus": menus[:12], "blog_reviews": blogs[:10],
        "missing_info": base.get("missingInfo"),
    }


def blog_text(url, max_chars=6000):
    """네이버 블로그 글 본문(공개 페이지). m.blog.naver.com/{id}/{no} 또는 blog.naver.com/{id}/{no} 지원. 캐시+캡(naver_blog)."""
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d+)", url)
    if not m:
        return None
    bid, no = m.group(1), m.group(2)
    cp = os.path.join(CACHE, "blog_" + hashlib.md5(f"{bid}/{no}".encode()).hexdigest() + ".txt")
    if os.path.exists(cp):
        return open(cp, encoding="utf-8").read()
    import quota_guard as qg
    from bs4 import BeautifulSoup
    qg.charge("naver_blog", 1)
    wait = 2.0 + random.random() * 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get("https://blog.naver.com/PostView.naver",
                     params={"blogId": bid, "logNo": no, "redirect": "Dlog", "widgetTypeCall": "true", "directAccess": "false"},
                     headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://blog.naver.com/"}, timeout=25)
    _last[0] = time.time()
    r.encoding = "utf-8"
    if r.status_code in (403, 429):
        raise NaverBlocked(f"blog HTTP {r.status_code}")
    if r.status_code != 200:
        return None
    s = BeautifulSoup(r.text, "lxml")
    body = s.select_one("div.se-main-container") or s.select_one("#postViewArea") or s.select_one("div.post-view")
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True)) if body else ""
    text = text[:max_chars]
    open(cp, "w", encoding="utf-8").write(text)
    return text


def nav_links(name, x, y, place_id):
    """네이버 지도 길안내 링크. 좌표는 네이버 플레이스가 준 값(WGS84)만 사용."""
    q = urllib.parse.quote(name)
    return {
        "app_navigation": f"nmap://navigation?dlat={y}&dlng={x}&dname={q}&appname={APPNAME}",
        "app_route": f"nmap://route/car?dlat={y}&dlng={x}&dname={q}&appname={APPNAME}",
        "app_place": f"nmap://place?lat={y}&lng={x}&name={q}&appname={APPNAME}",
        "web_place": f"https://map.naver.com/p/entry/place/{place_id}",
        "mobile_place": f"https://m.place.naver.com/place/{place_id}/home",
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--x"); ap.add_argument("--y")
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    r = resolve(a.name, a.x, a.y)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.detail and r["place"]:
        print(json.dumps(detail(r["place"]["id"]), ensure_ascii=False, indent=1))
