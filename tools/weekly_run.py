"""주간 자동 실행 (GitHub Actions 또는 로컬): 상태 점검 -> 점수화 -> 사이트 -> 검증 -> (선택) 카톡 알림.

종료코드: 0 성공 / 2 점검 중단(차단·캡; 데이터는 저장하지 않음) / 3 검증 실패(오류>0; 사이트 갱신하지 않음)
카톡은 --notify 를 줄 때만, 그리고 카카오 토큰이 있을 때만 보낸다.
"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
T = lambda s: os.path.join(ROOT, "tools", s)


def run(args, code_map=None):
    print("\n$", " ".join([os.path.basename(args[1])] + args[2:]))
    r = subprocess.run(args, cwd=ROOT)
    if r.returncode != 0:
        print(f"[중단] {os.path.basename(args[1])} exit {r.returncode}")
        sys.exit((code_map or {}).get(r.returncode, r.returncode))


run([PY, T("refresh_status.py")], {2: 2})
run([PY, T("pilot_score.py")])
run([PY, T("pilot_score.py"), "--raw", "data/daytrip/raw.json", "--yt", "data/daytrip/youtube.json", "--out", "data/daytrip/places.json",
     "--scope", "day_trip", "--kinds", "attraction", "--doc", "docs/DAYTRIP.md", "--title", "당일 나들이 시범"])
run([PY, T("build_site.py")])
run([PY, T("verify.py")], {1: 3})
if "--notify" in sys.argv:
    os.environ["TRIP_FRESH"] = "0"
    run([PY, T("notify_kakao.py"), "--send"])
print("\n[주간 실행 완료]")
