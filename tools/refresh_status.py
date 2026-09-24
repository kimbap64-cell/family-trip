"""주간 상태 점검: 이미 검증된 장소의 별점·리뷰수·영업상태(폐업)·편의시설을 새로 조회해 갱신한다.

- 새 장소 발굴·블로그 읽기는 하지 않는다(그건 Claude 세션에서). 네이버 상세 + 카카오 패널만 신선 조회(TRIP_FRESH=1).
- 차단 신호(NaverBlocked/카카오 403·429) 또는 연속 실패면 **아무것도 저장하지 않고 중단**(exit 2). 낡은 데이터를 조용히 새것처럼 두지 않는다.
- 폐업 신호: 네이버 상세 소멸 또는 카카오 status != 'Y' -> raw 의 closure 근거로 기록 -> pilot_score 게이트가 판단(서로 다른 출처 2건이면 제외).
- 변경 요약: data/status_log.json (사이트 푸터·카톡 알림이 사용)
사용: TRIP_FRESH=1 python tools/refresh_status.py [--limit N] [--dry]
"""
import argparse, json, os, sys, time
from datetime import date

os.environ["TRIP_FRESH"] = "1"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_guard as qg
import naver_place as npl
import kakao_local as kl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["data/pilot/misa_raw.json", "data/daytrip/raw.json", "data/camping/raw.json"]
RATE_DELTA = 0.15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    docs = {f: json.load(open(os.path.join(ROOT, f), encoding="utf-8")) for f in FILES if os.path.exists(os.path.join(ROOT, f))}
    changes, failures, closures, n, fail_streak = [], [], [], 0, 0
    kakao_capped = False
    t0 = time.time()
    for f, doc in docs.items():
        for rec in doc["places"]:
            if a.limit and n >= a.limit:
                break
            n += 1
            nv, name, pid = rec["naver"], rec["naver"]["name"], rec["naver"]["id"]
            try:
                d = npl.detail(pid)
                fail_streak = 0
            except (npl.NaverBlocked, qg.QuotaExceeded) as e:
                print(f"[중단] 네이버 차단/캡: {e} — 저장하지 않음"); sys.exit(2)
            except Exception as e:
                failures.append({"name": name, "why": f"네이버 조회 실패: {str(e)[:60]}"}); fail_streak += 1
                if fail_streak >= 5:
                    print("[중단] 연속 5회 실패 — 저장하지 않음"); sys.exit(2)
                continue
            if not d.get("name"):
                # 상세 페이지가 사라짐 = 폐업/이전/삭제 신호
                closures.append({"name": name, "why": "네이버 장소 페이지 없음"})
                rec["evidence"].setdefault("closure", []).append({"label": "폐업/이전", "quote": "네이버 플레이스 상세 페이지가 조회되지 않음", "src": "naver-status", "date": str(date.today())})
                continue
            old_s, new_s = nv.get("visitor_review_score"), d.get("visitor_review_score")
            if old_s and new_s and abs(old_s - new_s) >= RATE_DELTA:
                changes.append({"name": name, "what": f"네이버 별점 {old_s} → {new_s}"})
            nv["visitor_review_score"], nv["visitor_review_count"] = new_s if new_s is not None else old_s, d.get("visitor_review_count") or nv.get("visitor_review_count")
            nv["blog_review_count"] = d.get("blog_review_count") or nv.get("blog_review_count")
            nd = rec.setdefault("naver_detail", {})
            for k in ("conveniences", "payment", "opening_hours", "menus"):
                if d.get(k) is not None:
                    nd[k] = d[k]
            kk = rec.get("kakao") or {}
            if kk.get("kakao_id") and not kakao_capped:
                try:
                    p = kl.panel(kk["kakao_id"])
                except qg.QuotaExceeded as e:
                    # 카카오 패널 캡 도달: 전체를 중단하지 않고 남은 장소는 네이버만 점검(카카오 값은 이전 확인값 유지) + 로그에 기록
                    kakao_capped = True
                    failures.append({"name": name, "why": f"카카오 패널 캡 도달 — 이후 장소는 네이버만 점검 ({e})"})
                    print(f"[경고] 카카오 캡 도달 — 이후는 네이버만 점검: {e}")
                    p = None
                except Exception as e:
                    print(f"[중단] 카카오 패널 차단/오류: {str(e)[:80]} — 저장하지 않음"); sys.exit(2)
                if p:
                    ss = (p.get("kakaomap_review") or {}).get("score_set") or {}
                    st = (p.get("summary") or {}).get("status")
                    if kk.get("status") == "Y" and st != "Y":
                        closures.append({"name": name, "why": f"카카오 영업상태 Y → {st}"})
                        rec["evidence"].setdefault("closure", []).append({"label": "폐업/이전", "quote": f"카카오맵 영업상태가 {st}로 바뀜", "src": "kakao-status", "date": str(date.today())})
                    if kk.get("rating") and ss.get("average_score") and abs(kk["rating"] - ss["average_score"]) >= 0.3:
                        changes.append({"name": name, "what": f"카카오 별점 {kk['rating']} → {ss['average_score']}"})
                    kk.update({"status": st, "rating": ss.get("average_score", kk.get("rating")), "review_count": ss.get("review_count", kk.get("review_count"))})
                    am = (p.get("place_add_info") or {}).get("ai_mate") or {}
                    kk["facility_icons"] = [x.get("text") for x in am.get("store_facility_icons", [])] or (kk.get("facility_icons") or [])
            if n % 10 == 0:
                print(f"  점검 {n}건 ({time.time()-t0:.0f}s)", flush=True)
    log = {"checked_at": time.strftime("%Y-%m-%d %H:%M"), "date": str(date.today()), "checked": n, "changes": changes, "closures": closures, "failures": failures}
    print(f"[점검 완료] {n}건 · 별점 변동 {len(changes)} · 폐업 의심 {len(closures)} · 실패 {len(failures)}")
    for c in changes[:8]:
        print("  변동:", c["name"], c["what"])
    for c in closures:
        print("  ⚠️ 폐업 의심:", c["name"], c["why"])
    if a.dry:
        print("(--dry: 저장하지 않음)"); return
    for f, doc in docs.items():
        json.dump(doc, open(os.path.join(ROOT, f), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(log, open(os.path.join(ROOT, "data", "status_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
