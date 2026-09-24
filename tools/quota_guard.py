"""외부 API 하드캡 (코드 레벨).

호출 직전에 charge()로 카운터를 올리고, 일/월 한도를 넘으면 QuotaExceeded 로 즉시 멈춘다.
- 카운터는 호출 '전에' 올린다(실패해도 소모한 것으로 간주 = 보수적).
- 구글 API 화이트리스트: config/limits.json 의 google.allowed_apis 밖이면 ForbiddenAPI.
- 유료 가능 구글 API 는 (1) paid_apis_enabled 에 명시 승인 AND (2) 오늘 <= trial_ends(무료 체험 종료일) 일 때만 통과.
- 킬스위치: 환경변수 TRIP_API_KILL=1 이면 모든 호출 거부.
- 장부: data/cache/api_usage.json (환경변수 API_LEDGER_PATH 로 변경 가능). 날짜는 KST 기준.
"""
import json, os, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))


class QuotaExceeded(RuntimeError):
    pass


class ForbiddenAPI(RuntimeError):
    pass


def _cfg():
    return json.load(open(os.path.join(ROOT, "config", "limits.json"), encoding="utf-8"))


def _ledger_path():
    return os.environ.get("API_LEDGER_PATH") or os.path.join(ROOT, "data", "cache", "api_usage.json")


def _load():
    p = _ledger_path()
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(d):
    p = _ledger_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, p)


def today():
    return datetime.now(KST).date()


def _killed():
    cfg = _cfg()
    return os.environ.get(cfg.get("kill_switch_env", "TRIP_API_KILL")) == "1"


def require_google_api(name):
    """구글 API 호출 전 게이트. 허용 목록/유료/체험판 조건을 검사."""
    cfg = _cfg()["google"]
    if _killed():
        raise ForbiddenAPI("킬스위치 활성(TRIP_API_KILL=1)")
    if name in cfg["allowed_apis"]:
        return True
    if name in cfg["paid_capable_apis"]:
        if not cfg.get("paid_apis_enabled", {}).get(name):
            raise ForbiddenAPI(f"구글 유료 가능 API '{name}' 는 사용자 승인 전이라 금지 (limits.json paid_apis_enabled)")
        if today() > datetime.strptime(cfg["trial_ends"], "%Y-%m-%d").date():
            raise ForbiddenAPI(f"무료 체험판 종료일({cfg['trial_ends']})이 지나 '{name}' 금지")
        return True
    raise ForbiddenAPI(f"허용 목록에 없는 구글 API '{name}'")


def charge(counter, n=1):
    """counter 사용량을 n 만큼 올린다. 한도 초과면 올리지 않고 QuotaExceeded."""
    if _killed():
        raise ForbiddenAPI("킬스위치 활성(TRIP_API_KILL=1)")
    caps = _cfg()["caps"].get(counter)
    if caps is None:
        raise ForbiddenAPI(f"한도가 정의되지 않은 카운터 '{counter}' (config/limits.json caps)")
    led = _load()
    d = str(today())
    m = d[:7]
    day = led.setdefault(d, {})
    used_day = day.get(counter, 0)
    used_month = sum(v.get(counter, 0) for k, v in led.items() if k.startswith(m))
    if used_day + n > caps["daily"]:
        raise QuotaExceeded(f"[일 한도] {counter}: {used_day}+{n} > {caps['daily']}")
    if used_month + n > caps["monthly"]:
        raise QuotaExceeded(f"[월 한도] {counter}: {used_month}+{n} > {caps['monthly']}")
    day[counter] = used_day + n
    _save(led)
    return day[counter]


def ensure_available(counter):
    """명령 시작 시 호출: 오늘 한도가 0이거나 이미 소진됐으면 즉시 QuotaExceeded."""
    if _killed():
        raise ForbiddenAPI("킬스위치 활성(TRIP_API_KILL=1)")
    caps = _cfg()["caps"].get(counter)
    if caps is None:
        raise ForbiddenAPI(f"한도가 정의되지 않은 카운터 '{counter}'")
    used = _load().get(str(today()), {}).get(counter, 0)
    if caps["daily"] <= 0 or used >= caps["daily"]:
        raise QuotaExceeded(f"[일 한도] {counter}: 사용 {used}/{caps['daily']} — 실행하지 않음 (config/limits.json)")


def usage(counter=None):
    led = _load()
    d = str(today())
    m = d[:7]
    caps = _cfg()["caps"]
    out = {}
    for c in ([counter] if counter else caps):
        out[c] = {
            "today": led.get(d, {}).get(c, 0), "daily_cap": caps[c]["daily"],
            "month": sum(v.get(c, 0) for k, v in led.items() if k.startswith(m)), "monthly_cap": caps[c]["monthly"],
        }
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for c, u in usage().items():
        print(f"{c:<20} 오늘 {u['today']:>5}/{u['daily_cap']:<5} | 이번달 {u['month']:>6}/{u['monthly_cap']}")
