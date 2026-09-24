"""공통 유틸: .env 로드 (키는 값이 절대 출력되지 않도록 마스킹해서만 표시)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """프로젝트 루트의 .env 를 읽어 환경변수에 넣고 dict 반환. 이미 설정된 환경변수(예: GitHub Secrets)가 우선."""
    path = path or os.path.join(ROOT, ".env")
    vals = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in vals.items():
        os.environ.setdefault(k, v)
    return {k: os.environ.get(k) for k in vals}


def need(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"[설정 필요] 환경변수 {name} 가 없습니다 (.env 또는 GitHub Secrets 에 등록)")
    return v


def mask(v):
    return "(없음)" if not v else f"{v[:3]}…{v[-2:]} (len={len(v)})"
