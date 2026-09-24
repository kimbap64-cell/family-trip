"""카카오 로컬 API 동작 확인 (기존 앱 '가족나들이'의 REST 키, 1~2회 호출)."""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tok = json.load(open(os.path.join(ROOT, "kakao_token.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "kakao_token.json")) \
    else json.load(open(r"C:\Users\JFAMILY\Desktop\antigravity\여행\kakao_token.json", encoding="utf-8"))
H = {"Authorization": f"KakaoAK {tok['rest_api_key']}"}

r = requests.get("https://dapi.kakao.com/v2/local/search/address.json",
                 params={"query": "경기도 하남시 미사강변중앙로 120"}, headers=H, timeout=15)
print("[주소검색] HTTP", r.status_code)
if r.status_code == 200:
    for d in r.json().get("documents", [])[:1]:
        print("  ", d.get("address_name"), "| x,y =", d.get("x"), d.get("y"))
else:
    print("  ", r.text[:200])

r = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json",
                 params={"query": "화담숲", "size": 2}, headers=H, timeout=15)
print("[키워드검색] HTTP", r.status_code)
if r.status_code == 200:
    for d in r.json().get("documents", []):
        print("  ", d["place_name"], "|", d.get("road_address_name"), "|", d["x"], d["y"], "|", d["place_url"])
else:
    print("  ", r.text[:200])
