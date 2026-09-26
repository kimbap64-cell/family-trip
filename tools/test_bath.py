"""캠핑 화장실·샤워실 근거 추출 회귀 시험 (실제 오판 사례 포함)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pilot_local import extract

def labels(t):
    return {e["label"] for e in extract(t, "t")["bath"]}

def check(cond, msg):
    print(("OK  " if cond else "FAIL"), msg)
    return cond

ok = True
ok &= check("개별 화장실·샤워실" in labels("깔끔한 시설과 내부에 개별 화장실도 있으니 좋아요"), "개별 화장실 인식")
ok &= check("개별 화장실·샤워실" not in labels("여성 전용 샤워장과 화장실도 있고 관리가 잘 되어있어서"), "여성 전용 샤워장은 개별 아님(오판 사례)")
ok &= check("화장실·샤워실 청결" in labels("화장실도 깨끗했어요! 기본 어메너티로"), "화장실 깨끗 인식")
ok &= check("화장실·샤워실 청결" not in labels("화장실이 깨끗하지 않아서 아쉬웠어요"), "깨끗하지 않다는 근거 아님")
ok &= check("화장실·샤워실 아쉬움" in labels("샤워실이 너무 멀어서 불편했어요"), "샤워실 멀다 = 아쉬움")
ok &= check("화장실·샤워실 아쉬움" not in labels("화장실이 멀지 않아서 좋았어요"), "멀지 않다는 아쉬움 아님")
ok &= check("온수 잘 나옴" in labels("온수도 잘 나오고 수건도 있어요"), "온수 인식")
sys.exit(0 if ok else 1)
