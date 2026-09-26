"""이력 저장소 시험: 기준선 -> 신규 -> 등급/별점 변화 -> 이름 변경 -> 빠짐/복귀 -> 폐업/재개 -> 같은 날 재실행 중복 없음."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as rg

rg.REG = os.path.join(tempfile.mkdtemp(), "registry.json")
ok = True


def check(cond, msg):
    global ok
    print(("OK  " if cond else "FAIL"), msg)
    ok &= bool(cond)


def mk(name, tier="조건부", score=70.0, rating=4.5, closed=False, pid="1"):
    return {f"local:{pid}": {"scope": "local", "id": pid, "name": name, "kind": "restaurant", "closed": closed,
                             "snap": {"tier": tier, "score": score, "rating": rating, "reviews": 500, "addr": "a", "cat": "c", "dr": 5, "app": "x", "web": "y"}}}


def run(day, cur):
    rg.current = lambda: cur
    return rg.update(day)


reg = run("2026-01-01", {**mk("가게A"), **mk("가게B", pid="2")})
check(len(reg["places"]) == 2 and all(r["baseline"] for r in reg["places"].values()), "처음 실행: 전부 baseline (새로 추가 배지 안 뜸)")
reg = run("2026-01-08", {**mk("가게A"), **mk("가게B", pid="2"), **mk("새가게", pid="3")})
check(reg["places"]["local:3"]["events"][0]["type"] == "new" and not reg["places"]["local:3"]["baseline"], "새 장소는 new 이벤트")
reg = run("2026-01-15", {**mk("가게A", tier="추천", score=76.0, rating=4.7), **mk("가게B", pid="2"), **mk("새가게", pid="3")})
types = [e["type"] for e in reg["places"]["local:1"]["events"]]
check("tier" in types and "rating" in types, "등급·별점 변화 기록")
reg = run("2026-01-22", {**mk("가게A 리뉴얼점", tier="추천", score=76.0, rating=4.7), **mk("새가게", pid="3")})
check(reg["places"]["local:1"]["name"] == "가게A 리뉴얼점" and "renamed" in [e["type"] for e in reg["places"]["local:1"]["events"]], "이름 변경(리뉴얼) 기록")
check(reg["places"]["local:2"]["status"] == "missing" and len(reg["places"]) == 3, "목록에서 빠져도 삭제되지 않고 missing")
reg = run("2026-01-29", {**mk("가게A 리뉴얼점", tier="추천", score=76.0, rating=4.7), **mk("가게B", pid="2"), **mk("새가게", pid="3", tier="제외", closed=True)})
check(reg["places"]["local:2"]["status"] == "active" and "back" in [e["type"] for e in reg["places"]["local:2"]["events"]], "복귀 기록")
check(reg["places"]["local:3"]["status"] == "closed" and "closed" in [e["type"] for e in reg["places"]["local:3"]["events"]], "폐업 신호 -> closed, 이력 유지")
n = len(reg["places"]["local:3"]["events"])
reg = run("2026-01-29", {**mk("가게A 리뉴얼점", tier="추천", score=76.0, rating=4.7), **mk("가게B", pid="2"), **mk("새가게", pid="3", tier="제외", closed=True)})
check(len(reg["places"]["local:3"]["events"]) == n, "같은 날 재실행해도 이벤트 중복 없음")
reg = run("2026-02-05", {**mk("가게A 리뉴얼점", tier="추천", score=76.0, rating=4.7), **mk("가게B", pid="2"), **mk("새가게", pid="3")})
check(reg["places"]["local:3"]["status"] == "active" and "reopened" in [e["type"] for e in reg["places"]["local:3"]["events"]], "재개 기록")
sys.exit(0 if ok else 1)
