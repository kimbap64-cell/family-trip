"""'이번 주말 추천' 카카오톡 '나에게 보내기' 알림 (새 데이터 구조용).

기본은 --dry-run(미리보기만 출력, 발송 안 함). 실제 발송은 --send 를 명시해야 하며, 사용자 승인 없이 쓰지 않는다.
토큰 갱신 로직은 send_kakao_alert.py 의 것을 재사용한다(access_token 만료 시 refresh_token 으로 자동 재발급).

  python tools/notify_kakao.py              # 미리보기
  python tools/notify_kakao.py --send       # 실제 발송 (사용자 승인 후)
선정: 당일 나들이 '추천' 중 편도 60분 이내, 서로 다른 지역·브랜드 우선 3곳. 근거 부족·제외는 넣지 않는다.
"""
import argparse, json, os, re, sys
import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # send_kakao_alert.py 는 저장소 루트에 있음(토큰 로드·갱신 재사용)
import send_kakao_alert as ska
SITE = "https://kimbap64-cell.github.io/family-trip/"


def brand(name):
    return re.split(r"\s", name)[0][:4]


def pick(n=3):
    d = json.load(open(os.path.join(ROOT, "data", "daytrip", "places.json"), encoding="utf-8"))["places"]
    # 주간 추천은 별점 신뢰가 높은 곳만: 네이버 별점이 있거나, 카카오 원점수 4.3 이상(보정으로만 올라온 곳 제외)
    c = [p for p in d if p["scores"]["tier"] == "추천" and (p.get("drive") or {}).get("min", 999) <= 60
         and p["family"]["mode_b"]["verdict"] != "부적합(좌식 근거)"
         and (p["naver"]["score"] or (p["kakao"].get("rating") or 0) >= 4.3)]
    c.sort(key=lambda p: -p["scores"]["total"])
    out, seen = [], set()
    for p in c:
        b = brand(p["name"])
        if b in seen:
            continue
        seen.add(b)
        out.append(p)
        if len(out) == n:
            break
    return out


def line(p, i):
    # 화면·알림에는 보정 전 원래 별점만 쓴다(네이버 우선, 없으면 '카카오 x.x')
    r = p["naver"]["score"] if p["naver"]["score"] else (f"카카오{p['kakao'].get('rating')}" if p["kakao"].get("rating") else "-")
    cost = (p["price"]["est_meal_4p"] or {}).get("krw")
    note = ""
    for e in p.get("plan_notes", []):
        if e["label"] == "사전 예약":
            note = " · 사전예약"; break
    for e in p.get("plan_notes", []):
        if e["label"] == "휴관·휴무일":
            m = re.search(r"[월화수목금토일]요일", e["quote"])
            if m:
                note += f" · {m.group(0)[0]}요일 휴관?"
            break
    c = f" · 입장 약{round(cost/10000)}만" if cost else ""
    return f"{i}. {p['name'][:12]} 🚗{round(p['drive']['min'])}분 ★{r}{c}{note}".replace("★카카오", "카카오★")


def tpl_text(text, button="근거·내비 보기"):
    return {"object_type": "text", "text": text[:200], "link": {"web_url": SITE, "mobile_web_url": SITE}, "button_title": button}


def build():
    ps = pick()
    if not ps:
        return None
    text = "🚗 이번 주말 추천 (미사 출발)\n" + "\n".join(line(p, i + 1) for i, p in enumerate(ps))
    # 주간 점검 결과가 있으면 한 줄 요약(폐업 의심은 이름까지)
    sp = os.path.join(ROOT, "data", "status_log.json")
    if os.path.exists(sp):
        sl = json.load(open(sp, encoding="utf-8"))
        if sl["closures"]:
            text += "\n⚠️ 폐업 의심: " + ", ".join(c["name"][:8] for c in sl["closures"][:3])
        elif sl["changes"]:
            text += f"\n별점 변동 {len(sl['changes'])}곳 점검됨"
    text += "\n※ 휴관·예약은 가기 전 확인"
    return tpl_text(text)


def send(tpl):
    tok = ska.load_token()
    if not tok or not tok.get("access_token"):
        print("[중단] kakao_token.json 없음/토큰 없음"); return False
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    payload = {"template_object": json.dumps(tpl, ensure_ascii=False)}
    r = requests.post(url, headers={"Authorization": f"Bearer {tok['access_token']}"}, data=payload, timeout=20)
    if r.status_code == 401 and tok.get("rest_api_key") and tok.get("refresh_token"):
        new = ska.refresh_access_token(tok["rest_api_key"], tok["refresh_token"])
        if new:
            r = requests.post(url, headers={"Authorization": f"Bearer {new}"}, data=payload, timeout=20)
    print("발송 결과:", r.status_code, "" if r.status_code == 200 else r.text[:200])
    return r.status_code == 200


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--text", help="추천 대신 이 문구를 보낸다(예: 자동 점검 실패 알림)")
    a = ap.parse_args()
    tpl = tpl_text(a.text, "사이트 열기") if a.text else build()
    if not tpl:
        print("추천 조건을 만족하는 곳이 없어 알림을 만들지 않았어요."); sys.exit(0)
    print("[미리보기]\n" + tpl["text"] + f"\n(글자수 {len(tpl['text'])}/200)  버튼: {tpl['button_title']} -> {SITE}")
    if a.send:
        if not send(tpl):
            # 알림 실패가 사이트 갱신을 막으면 안 되므로 종료코드는 0. 대신 Actions 화면에 경고 주석을 남긴다.
            print("::warning title=카톡 발송 실패::토큰 만료/Secrets 확인 필요 (docs/ACTIONS_SETUP.md). 점검·사이트 갱신은 정상 처리됨")
    else:
        print("\n(미리보기만 — 발송하지 않았어요. 실제 발송은 사용자 승인 후 --send)")
