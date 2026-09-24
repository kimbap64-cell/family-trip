"""안전캡 동작 시험. 임시 장부를 쓰므로 실제 사용량 장부를 건드리지 않는다.
실행: python tools/test_quota_guard.py
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmp = os.path.join(tempfile.mkdtemp(), "ledger.json")
os.environ["API_LEDGER_PATH"] = tmp
os.environ.pop("TRIP_API_KILL", None)
import quota_guard as qg

ok, fail = 0, 0


def check(name, fn, expect):
    global ok, fail
    try:
        fn()
        got = None
    except Exception as e:
        got = type(e)
    good = (got is expect) if expect else (got is None)
    ok += good
    fail += (not good)
    print(("PASS" if good else "FAIL"), "-", name, "" if good else f"(기대 {expect}, 실제 {got})")


# 1) 일 한도: youtube_api_search 일 40 -> 40회까지 통과, 41번째 차단
def fill_search():
    for _ in range(40):
        qg.charge("youtube_api_search", 1)
check("검색 40회까지 통과", fill_search, None)
check("검색 41번째 차단(일 한도)", lambda: qg.charge("youtube_api_search", 1), qg.QuotaExceeded)

# 2) 유닛 캡: 3000 초과 차단, 초과 시도는 장부에 안 올라감
qg.charge("youtube_api_units", 2990)
check("유닛 2990+100(검색 1회) 차단", lambda: qg.charge("youtube_api_units", 100), qg.QuotaExceeded)
check("유닛 남은 10 이하는 통과", lambda: qg.charge("youtube_api_units", 10), None)
check("유닛 3000 도달 후 1도 차단", lambda: qg.charge("youtube_api_units", 1), qg.QuotaExceeded)

# 3) 스크래핑 캡 0 -> 시작 자체 차단
check("스크래핑(youtube_scrape) 한도 0: ensure_available 차단", lambda: qg.ensure_available("youtube_scrape"), qg.QuotaExceeded)
check("스크래핑 charge 도 차단", lambda: qg.charge("youtube_scrape", 1), qg.QuotaExceeded)

# 4) 구글 API 화이트리스트/유료 금지
check("youtube 허용", lambda: qg.require_google_api("youtube"), None)
check("places(유료 가능) 승인 전 금지", lambda: qg.require_google_api("places"), qg.ForbiddenAPI)
check("gemini(유료 가능) 금지", lambda: qg.require_google_api("gemini"), qg.ForbiddenAPI)
check("모르는 구글 API 금지", lambda: qg.require_google_api("something_new"), qg.ForbiddenAPI)

# 5) 정의 안 된 카운터 거부
check("정의 안 된 카운터 거부", lambda: qg.charge("unknown_counter", 1), qg.ForbiddenAPI)

# 6) 킬스위치
os.environ["TRIP_API_KILL"] = "1"
check("킬스위치: charge 차단", lambda: qg.charge("naver_place", 1), qg.ForbiddenAPI)
check("킬스위치: 구글 게이트 차단", lambda: qg.require_google_api("youtube"), qg.ForbiddenAPI)
os.environ.pop("TRIP_API_KILL")
check("킬스위치 해제 후 통과", lambda: qg.charge("naver_place", 1), None)

# 7) 승인 + 체험판 종료일 로직 (설정을 임시로 바꿔 검증)
import json
orig = qg._cfg
def patched(enabled, ends):
    def f():
        c = orig()
        c["google"]["paid_apis_enabled"] = enabled
        c["google"]["trial_ends"] = ends
        return c
    return f
qg._cfg = patched({"places": True}, "2099-01-01")
check("places 승인+체험판 유효 -> 통과", lambda: qg.require_google_api("places"), None)
qg._cfg = patched({"places": True}, "2000-01-01")
check("places 승인했어도 체험판 종료일 지나면 금지", lambda: qg.require_google_api("places"), qg.ForbiddenAPI)
qg._cfg = orig

print(f"\n결과: {ok} 통과 / {fail} 실패")
sys.exit(1 if fail else 0)
