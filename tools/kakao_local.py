"""카카오 로컬 API(공식) 래퍼 — 장소 존재·주소·좌표 교차검증. 호출은 quota_guard 경유, 캐시."""
import hashlib, json, os, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
from common import load_env, need
import naver_place as npl
import geo

load_env()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "kakao")
os.makedirs(CACHE, exist_ok=True)


def keyword(query, x=None, y=None, radius=None, size=5):
    key = f"kw|{query}|{x}|{y}|{radius}|{size}"
    cp = os.path.join(CACHE, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    qg.charge("kakao_local", 1)
    p = {"query": query, "size": size}
    if x and y:
        p.update({"x": x, "y": y})
        if radius:
            p["radius"] = radius
    r = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json", params=p,
                     headers={"Authorization": f"KakaoAK {need('KAKAO_REST_API_KEY')}"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"kakao_local HTTP {r.status_code}: {r.text[:150]}")
    docs = r.json().get("documents", [])
    json.dump(docs, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
    return docs


def panel(kakao_id):
    """카카오맵 장소 패널(별점·리뷰·메뉴·영업시간). 비공식 공개 엔드포인트라 소량만(kakao_place_page 캡), 캐시."""
    cp = os.path.join(CACHE, f"panel_{kakao_id}.json")
    if os.path.exists(cp) and os.environ.get("TRIP_FRESH") != "1":
        return json.load(open(cp, encoding="utf-8"))
    qg.charge("kakao_place_page", 1)
    import time
    time.sleep(1.0)
    H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
         "Referer": "https://map.kakao.com/", "pf": "PC", "Accept": "application/json"}
    r = requests.get(f"https://place-api.map.kakao.com/places/panel3/{kakao_id}", headers=H, timeout=25)
    if r.status_code in (403, 429):
        raise RuntimeError(f"kakao panel blocked HTTP {r.status_code}")
    if r.status_code != 200:
        return None
    j = r.json()
    json.dump(j, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
    return j


def verify(name, nx, ny, road_address=None, max_m=250):
    """네이버 장소(name, 좌표)와 같은 곳이 카카오에도 있는지. 이름 유사도 + 좌표거리(<=max_m)로 판정."""
    docs = keyword(name, nx, ny, radius=1000, size=5)
    best = None
    for d in docs:
        dm = geo.haversine_m(nx, ny, float(d["x"]), float(d["y"]))
        sim = npl.match_score(name, d["place_name"])
        score = sim - min(dm, 2000) / 4000.0
        if best is None or score > best[0]:
            best = (score, d, dm, sim)
    if not best:
        return {"found": False}
    _, d, dm, sim = best
    ok = dm <= max_m and sim >= 0.6
    return {"found": ok, "kakao_id": d["id"], "kakao_name": d["place_name"], "kakao_url": d["place_url"],
            "kakao_road_address": d.get("road_address_name"), "kakao_category": d.get("category_name"),
            "phone": d.get("phone"), "dist_m": round(dm), "name_sim": sim,
            "x": float(d["x"]), "y": float(d["y"])}
