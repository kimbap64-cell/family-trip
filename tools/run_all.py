"""전체 파이프라인 재생성 (캐시 우선 — 대부분 외부 호출 0). 캡은 quota_guard 가 지킨다.

  python tools/run_all.py            # 캐시 재추출 -> 점수화 -> 사이트 빌드 -> 검증
  python tools/run_all.py --fetch    # 새 장소 수집까지(네이버·카카오 캡 안에서). 유튜브 API는 --refresh 를 직접 지정해야만 재호출
"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
T = lambda s: os.path.join(ROOT, "tools", s)
steps = [
    [PY, T("pilot_local.py"), "--max-detail", "45", "--max-drive", "12"],
    [PY, T("daytrip_collect.py"), "--top", "45", "--blogs", "2"],
    [PY, T("pilot_youtube.py")],
    [PY, T("pilot_youtube.py"), "--set", "daytrip", "--raw", "data/daytrip/raw.json", "--out", "data/daytrip/youtube.json", "--cache", "data/cache/yt_daytrip_raw.json"],
    [PY, T("pilot_score.py")],
    [PY, T("pilot_score.py"), "--raw", "data/daytrip/raw.json", "--yt", "data/daytrip/youtube.json", "--out", "data/daytrip/places.json",
     "--scope", "day_trip", "--kinds", "attraction", "--doc", "docs/DAYTRIP.md", "--title", "당일 나들이 시범"],
    [PY, T("camp_collect.py"), "--top", "25", "--blogs", "2"],
    [PY, T("pilot_youtube.py"), "--set", "camping", "--raw", "data/camping/raw.json", "--out", "data/camping/youtube.json", "--cache", "data/cache/yt_camp_raw.json"],
    [PY, T("pilot_score.py"), "--raw", "data/camping/raw.json", "--yt", "data/camping/youtube.json", "--out", "data/camping/places.json",
     "--scope", "camping", "--kinds", "camping", "--doc", "docs/CAMPING.md", "--title", "키즈캠핑 시범"],
    # 장소별 맞춤 유튜브 검색(캐시 우선, 새 장소만 API). pilot_youtube 가 youtube.json 을 새로 쓰므로 반드시 그 뒤에 병합 -> 재점수화
    [PY, T("yt_place_search.py"), "--places", "data/daytrip/places.json", "--yt", "data/daytrip/youtube.json", "--n", "12"],
    [PY, T("yt_place_search.py"), "--places", "data/camping/places.json", "--yt", "data/camping/youtube.json", "--n", "12", "--suffix", "캠핑"],
    [PY, T("pilot_score.py"), "--raw", "data/daytrip/raw.json", "--yt", "data/daytrip/youtube.json", "--out", "data/daytrip/places.json",
     "--scope", "day_trip", "--kinds", "attraction", "--doc", "docs/DAYTRIP.md", "--title", "당일 나들이 시범"],
    [PY, T("pilot_score.py"), "--raw", "data/camping/raw.json", "--yt", "data/camping/youtube.json", "--out", "data/camping/places.json",
     "--scope", "camping", "--kinds", "camping", "--doc", "docs/CAMPING.md", "--title", "키즈캠핑 시범"],
    [PY, T("daytrip_courses.py"), "--n", "10"],
    [PY, T("registry.py")],  # 이력 갱신(기준선이 없으면 지금 목록을 기준선으로)
    [PY, T("build_site.py")],
    [PY, T("verify.py")],
]
for s in steps:
    print("\n$", " ".join(os.path.basename(x) if i < 2 else x for i, x in enumerate(s)))
    r = subprocess.run(s, cwd=ROOT)
    if r.returncode != 0:
        print(f"[중단] 단계 실패(exit {r.returncode}) — 이후 단계 실행하지 않음")
        sys.exit(r.returncode)
print("\n[전체 완료]")
