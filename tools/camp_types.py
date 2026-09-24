"""캠핑 유형 분류 요약 (글램핑/카라반/오토캠핑/펜션형).  python tools/camp_types.py
이름·카테고리·홍보문구로 유형을 추정한다. 사용자가 원하는 '직접 장비를 챙기는 오토캠핑'이 얼마나 되는지 확인용.
"""
import json, os, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def camp_type(name, promo="", cat=""):
    s = f"{name} {promo} {cat}"
    if re.search(r"글램핑|글램", name):          # 이름에 글램핑이 있으면 글램핑 (예: '글램핑 캠핑장')
        return "글램핑"
    if re.search(r"카라반", name):
        return "카라반"
    if re.search(r"풀빌라|펜션|리조트", name):
        return "펜션·리조트형"
    if re.search(r"오토캠핑|캠핑장|캠프|캠핑파크|캠핑랜드|야영", s):
        return "오토캠핑"
    return "기타"


if __name__ == "__main__":
    p = os.path.join(ROOT, "data", "camping", "raw.json")
    d = json.load(open(p, encoding="utf-8"))["places"]
    c = collections.Counter()
    for x in d:
        n = x["naver"]
        t = camp_type(n["name"], n.get("promo") or "", n.get("category") or "")
        c[t] += 1
        print(f"{t:<8} | {n['name'][:22]:<22} | {n.get('promo') or ''}"[:110])
    print("\n유형 분포:", dict(c))
