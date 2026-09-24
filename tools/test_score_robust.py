"""점수화가 None/누락 필드에 죽지 않는지 시험 (2026-09-24 Actions 실패 재현: kakao.facility_icons=None).
임시 폴더에 변형 데이터를 만들어 pilot_score 를 돌린다. 실제 데이터는 건드리지 않는다.  python tools/test_score_robust.py
"""
import json, os, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
ok = True
for name, raw_rel, yt_rel, scope, kinds in (("동네", "data/pilot/misa_raw.json", "data/pilot/misa_youtube.json", "local", "restaurant,cafe"),
                                              ("나들이", "data/daytrip/raw.json", "data/daytrip/youtube.json", "day_trip", "attraction"),
                                              ("캠핑", "data/camping/raw.json", "data/camping/youtube.json", "camping", "camping")):
    if not os.path.exists(os.path.join(ROOT, raw_rel)):
        continue
    doc = json.load(open(os.path.join(ROOT, raw_rel), encoding="utf-8"))
    for i, p in enumerate(doc["places"]):
        kk = p.get("kakao") or {}
        kk["facility_icons"] = None            # 실패 원인 재현
        if i % 3 == 0:
            kk["store_infos"] = None; kk["rating"] = None; kk["review_count"] = None
        if i % 4 == 0:
            (p.get("naver_detail") or {})["conveniences"] = None
        p["kakao"] = kk
    rp = os.path.join(tmp, f"{scope}_raw.json")
    json.dump(doc, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pilot_score.py"), "--raw", rp, "--yt", os.path.join(ROOT, yt_rel), "--out", os.path.join(tmp, f"{scope}_out.json"),
                        "--scope", scope, "--kinds", kinds, "--doc", os.path.join(tmp, f"{scope}.md")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    good = r.returncode == 0
    ok &= good
    print(("PASS" if good else "FAIL"), "-", name, "None 주입 점수화", "" if good else "\n" + (r.stderr or r.stdout)[-400:])
sys.exit(0 if ok else 1)
