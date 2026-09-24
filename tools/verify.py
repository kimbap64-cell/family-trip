"""게시 전 검증 (CLAUDE.md 규칙 6). 결과를 그대로 보고한다.

검사 항목
  1. 링크: 검색 URL 금지(youtube results / search.naver), 네이버 내비 좌표 == 장소 좌표, 웹 링크에 place_id 포함
  2. 좌표: 한국 범위, 집 기준 거리와 이동시간이 일관(직선거리 대비 비정상 시간 검출), 네이버-카카오 좌표 차 <= 250m
  3. 필수 필드: 이름·좌표·별점 출처·이동시간·근거 1개 이상, 추천/조건부는 근거 링크 보유
  4. 등급 일관성: 게이트 실패인데 추천/조건부이거나, 통과인데 제외인 경우
  5. 근거 인용문: 비어 있지 않고 출처(src)가 있음
사용: python tools/verify.py [data/pilot/misa_places.json ...]  (인자 없으면 존재하는 모든 places.json)
"""
import json, os, re, sys, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD_URL = re.compile(r"youtube\.com/results|search\.naver\.com|search_query=")


def urls(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from urls(v)
    elif isinstance(o, list):
        for v in o:
            yield from urls(v)
    elif isinstance(o, str) and o.startswith(("http://", "https://", "nmap://")):
        yield o


def check_place(p, hx, hy):
    errs, warns = [], []
    n, k = p["naver"], p.get("kakao") or {}
    x, y = n.get("x"), n.get("y")
    if not (x and y and 124 < x < 132 and 33 < y < 39):
        errs.append("좌표 없음/한국 범위 밖")
    else:
        # 내비 링크 좌표 일치
        app = p["nav"]["app_navigation"]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(app).query)
        try:
            if abs(float(q["dlat"][0]) - y) > 1e-6 or abs(float(q["dlng"][0]) - x) > 1e-6:
                errs.append("nmap 내비 좌표 != 장소 좌표")
        except Exception:
            errs.append("nmap 링크 형식 오류")
        if n["place_id"] not in p["nav"]["web_place"]:
            errs.append("웹 링크에 place_id 없음")
        if not app.startswith("nmap://navigation?"):
            errs.append("내비 링크가 nmap://navigation 이 아님")
        # 이동시간 일관성: 직선거리 대비 (도로는 직선의 1~2.5배, 평균 30~60km/h)
        dr = (p.get("drive") or {}).get("min")
        if dr is None:
            errs.append("차량 이동시간 없음")
        else:
            km = geo.haversine_m(hx, hy, x, y) / 1000
            if km > 1 and not (km / 100 * 60 <= dr <= km / 12 * 60 + 8):
                warns.append(f"이동시간 {dr}분이 직선 {km:.1f}km 대비 비정상")
    lim = 1500 if p.get("kind") == "attraction" else 800 if p.get("kind") == "camping" else 250
    if k.get("found") and k.get("dist_m") is not None and k["dist_m"] > lim:
        errs.append(f"네이버-카카오 좌표 차 {k['dist_m']}m > {lim}m")
    if not k.get("found"):
        warns.append("카카오 교차검증 실패")
    if p["rating"]["source"] is None:
        warns.append("별점 출처 없음")
    for u in urls(p):
        if BAD_URL.search(u):
            errs.append(f"검색 URL 사용 금지: {u[:70]}")
    tier, gp = p["scores"]["tier"], p["scores"]["gates"]["pass"]
    if tier in ("추천", "조건부") and not gp:
        errs.append("게이트 실패인데 추천/조건부")
    if tier == "제외" and gp:
        errs.append("게이트 통과인데 제외")
    if tier in ("추천", "조건부"):
        blogs = [b for b in p["sources"]["blogs"] if not b["sponsored"] and b.get("url")]
        if not blogs and not p["sources"]["youtube"]:
            errs.append("추천/조건부인데 근거 링크 없음")
    for grp in ("positive", "negative"):
        for e in p["family"]["mode_b"][grp]:
            if not e.get("quote") or not e.get("src"):
                errs.append(f"근거 인용문/출처 누락({e.get('label')})")
    return errs, warns


def main():
    files = sys.argv[1:] or [os.path.join(ROOT, "data", d, f) for d, f in (("pilot", "misa_places.json"), ("daytrip", "places.json"), ("camping", "places.json")) if os.path.exists(os.path.join(ROOT, "data", d, f))]
    hx, hy = geo.home()
    tot_e = tot_w = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))["places"]
        ne = nw = ok = 0
        print(f"\n== {os.path.relpath(f, ROOT)} ({len(d)}곳)")
        for p in d:
            e, w = check_place(p, hx, hy)
            ne += len(e); nw += len(w); ok += (not e)
            for m in e:
                print(f"  ❌ {p['name']}: {m}")
            for m in w[:2]:
                print(f"  ⚠️ {p['name']}: {m}")
        print(f"  -> 오류 없는 곳 {ok}/{len(d)} · 오류 {ne}건 · 경고 {nw}건")
        tot_e += ne; tot_w += nw
    # index.html 링크 검사
    ip = os.path.join(ROOT, "index.html")
    if os.path.exists(ip):
        html = open(ip, encoding="utf-8").read()
        bad = [u for u in set(re.findall(r"https?://[^\s\"'<>]+", html)) if BAD_URL.search(u)]
        print(f"\n== index.html: 검색 URL {len(bad)}건" + (f" ❌ {bad[:2]}" if bad else " ✅"))
        tot_e += len(bad)
    print(f"\n[검증 결과] 오류 {tot_e}건 · 경고 {tot_w}건 -> {'통과' if tot_e == 0 else '실패(게시 금지)'}")
    sys.exit(1 if tot_e else 0)


if __name__ == "__main__":
    main()
