"""좌표 유틸: 직선거리, 집->목적지 차량/도보 시간. 결과는 캐시, 호출은 quota_guard 경유.

- 차량: OSRM 공개 서버(router.project-osrm.org, 실시간 교통 미반영 -> 주말 정체는 별도 안내)
- 도보: routing.openstreetmap.de foot 프로파일
"""
import hashlib, json, math, os, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "geo")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "family-trip-personal/1.0 (low-volume, cached)"}
_last = [0.0]


def home():
    c = json.load(open(os.path.join(ROOT, "config", "criteria.json"), encoding="utf-8"))["home"]
    return c["x"], c["y"]


def haversine_m(x1, y1, x2, y2):
    R = 6371000.0
    p1, p2 = math.radians(y1), math.radians(y2)
    dp, dl = p2 - p1, math.radians(x2 - x1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _cached(key, counter, url):
    cp = os.path.join(CACHE, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    qg.charge(counter, 1)
    w = 0.6 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    r = requests.get(url, params={"overview": "false"}, headers=UA, timeout=25)
    _last[0] = time.time()
    if r.status_code != 200:
        raise RuntimeError(f"{counter} HTTP {r.status_code}")
    j = r.json()
    if j.get("code") != "Ok":
        raise RuntimeError(f"{counter} code {j.get('code')}")
    rt = j["routes"][0]
    out = {"min": round(rt["duration"] / 60, 1), "km": round(rt["distance"] / 1000, 2)}
    json.dump(out, open(cp, "w", encoding="utf-8"))
    return out


def drive(x, y, origin=None):
    ox, oy = origin or home()
    k = f"drive|{ox:.5f},{oy:.5f}|{x:.5f},{y:.5f}"
    r = _cached(k, "osrm_drive", f"https://router.project-osrm.org/route/v1/driving/{ox},{oy};{x},{y}")
    return {**r, "method": "OSRM(교통 미반영)"}


def walk(x, y, origin=None):
    ox, oy = origin or home()
    k = f"walk|{ox:.5f},{oy:.5f}|{x:.5f},{y:.5f}"
    r = _cached(k, "osm_foot", f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{ox},{oy};{x},{y}")
    return {**r, "method": "OSM foot"}
