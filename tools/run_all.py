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
    [PY, T("daytrip_collect.py"), "--top", "30", "--blogs", "2"],
    [PY, T("pilot_youtube.py")],
    [PY, T("pilot_youtube.py"), "--set", "daytrip", "--raw", "data/daytrip/raw.json", "--out", "data/daytrip/youtube.json", "--cache", "data/cache/yt_daytrip_raw.json"],
    [PY, T("pilot_score.py")],
    [PY, T("pilot_score.py"), "--raw", "data/daytrip/raw.json", "--yt", "data/daytrip/youtube.json", "--out", "data/daytrip/places.json",
     "--scope", "day_trip", "--kinds", "attraction", "--doc", "docs/DAYTRIP.md", "--title", "당일 나들이 시범"],
    [PY, T("daytrip_courses.py"), "--n", "10"],
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
