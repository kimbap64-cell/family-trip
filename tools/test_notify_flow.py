"""카톡 발송 흐름 시험 — 실제 발송 없이 가짜 응답으로 검증.
재현: Actions 처럼 access_token='' 인 토큰 파일이면 refresh 로 먼저 발급받아 발송해야 한다 (2026-09-24 알림 미발송 원인).
  python tools/test_notify_flow.py
"""
import json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import send_kakao_alert as ska
import notify_kakao as nk

tmp = os.path.join(tempfile.mkdtemp(), "kakao_token.json")
ska.TOKEN_FILE = tmp                       # 실제 토큰 파일을 건드리지 않도록 임시 파일 사용
calls = {"refresh": 0, "post": [], }


class R:
    def __init__(self, code): self.status_code, self.text = code, ""


def fake_refresh(key, rt):
    calls["refresh"] += 1
    return "NEW_ACCESS_TOKEN"


def run(case, token, post_codes):
    json.dump(token, open(tmp, "w", encoding="utf-8"))
    calls["refresh"], calls["post"] = 0, []
    codes = list(post_codes)
    def fake_post(url, headers=None, data=None, timeout=None):
        calls["post"].append(headers["Authorization"])
        return R(codes.pop(0))
    nk.requests.post = fake_post
    ska.refresh_access_token = fake_refresh
    ok = nk.send({"object_type": "text", "text": "t", "link": {"web_url": "x", "mobile_web_url": "x"}})
    return ok


fails = 0
def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL"), "-", name)
    fails += (not cond)

# 1) Actions 상황: access_token 비어 있음 -> 재발급 후 발송(200)
ok = run("empty-access", {"rest_api_key": "k", "access_token": "", "refresh_token": "r"}, [200])
check("access_token 비어 있으면 refresh 먼저 -> 발송 성공", ok and calls["refresh"] == 1 and calls["post"] == ["Bearer NEW_ACCESS_TOKEN"])
# 2) 로컬 상황: 유효 토큰이면 재발급 없이 발송
ok = run("valid", {"rest_api_key": "k", "access_token": "OLD", "refresh_token": "r"}, [200])
check("유효 토큰이면 재발급 없이 발송", ok and calls["refresh"] == 0 and calls["post"] == ["Bearer OLD"])
# 3) 만료(401) -> 재발급 후 재시도
ok = run("expired", {"rest_api_key": "k", "access_token": "OLD", "refresh_token": "r"}, [401, 200])
check("401이면 재발급 후 재시도 성공", ok and calls["refresh"] == 1 and calls["post"] == ["Bearer OLD", "Bearer NEW_ACCESS_TOKEN"])
# 4) 토큰 전무 -> 실패(예외 없이 False)
ok = run("none", {}, [])
check("토큰 없으면 False(예외 없음)", ok is False and not calls["post"])
# 5) 재발급 실패 -> False
ska.refresh_access_token = lambda k, r: None
json.dump({"rest_api_key": "k", "access_token": "", "refresh_token": "r"}, open(tmp, "w"))
check("재발급 실패면 False", nk.send({"object_type": "text", "text": "t", "link": {"web_url": "x", "mobile_web_url": "x"}}) is False)
print(f"\n결과: {5 - fails} 통과 / {fails} 실패")
sys.exit(1 if fails else 0)
