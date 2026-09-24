"""
[auto_collector.py]
유튜브/네이버 블로그 링크를 입력받거나, 정해진 스케줄에 따라
하남 미사 출발 기준 새로운 맞춤 여행 코스를 자동 발굴하여 DB에 누적하고
카카오톡 알림을 발송하는 자동화 수집기입니다.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from send_kakao_alert import send_kakao_trip_alert

DB_PATH = os.path.join(os.path.dirname(__file__), "trips_data.json")

def load_db():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": str(datetime.now().date()), "courses": []}

def save_db(data):
    data["updated_at"] = str(datetime.now().date())
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[성공] trips_data.json 갱신 완료 (총 {len(data['courses'])}개 코스 저장됨)")

def add_custom_course(new_course):
    """새로운 코스를 DB에 추가하고 카톡 알림 발송"""
    db = load_db()
    
    # ID 중복 검사
    existing_ids = [c["id"] for c in db.get("courses", [])]
    if new_course["id"] in existing_ids:
        print(f"[알림] 이미 등록된 코스 ID입니다: {new_course['id']}")
        return False
    
    # 최신 코스를 맨 위에 추가
    db["courses"].insert(0, new_course)
    save_db(db)
    
    # 카카오톡 알림 발송
    alert_info = {
        "course_title": new_course["course_title"],
        "area_name": new_course["area_name"],
        "duration_min": new_course["duration_min"],
        "cost_estimate_4p": new_course["cost_estimate_4p"],
        "spot1_name": new_course["spot1"]["name"],
        "restaurant_name": new_course["restaurant"]["name"],
        "cafe_name": new_course["cafe"]["name"]
    }
    send_kakao_trip_alert(alert_info)
    return True

def run_sample_auto_update():
    """자동 스케줄러 실행 시 샘플 코스 발굴 및 누적 예시"""
    sample_discovery = {
        "id": f"auto-{datetime.now().strftime('%Y%m%d')}",
        "region": "동부권",
        "area_name": "경기 남양주 별내",
        "duration_min": 25,
        "course_title": "남양주 산들소리수목원 동물교감 & 별내 불암산 한우쌈밥 코스",
        "tags": ["당일치기", "동물먹이체험", "숲놀이터", "무장애평지", "초근접"],
        "cost_estimate_4p": "약 62,000원",
        "spot1": {
            "name": "산들소리수목원 (동물농장 & 힐링카페)",
            "category": "자연·체험",
            "address": "경기 남양주시 불암산로 59번길 48-31",
            "description": "불암산 자락 아래 토끼/다람쥐 먹이주기, 뗏목 타기, 맨발 산책로가 조성된 도심 속 힐링 수목원.",
            "mode4_tip": "토끼 먹이주기 바구니 들고 탐험, 숲속 해먹 쉼터에서 낮잠 타임!",
            "mode6_tip": "입구부터 메인 수목원 카페까지 완만한 평지길로 어르신 관람에 부담이 없음."
        },
        "restaurant": {
            "name": "별내 목향원 (석쇠불고기 쌈밥)",
            "menu": "유기농 석쇠불고기 쌈밥 정식 4인 (삼색밥 포함)",
            "price_4p": "약 60,000원 ~ 68,000원",
            "seating": "입식 테이블 완비, 전통 초가집 정원",
            "address": "경기 남양주시 덕릉로1071번길 34-11",
            "notes": "부드러운 석쇠불고기와 소화가 잘되는 찰진 삼색밥으로 3대 가족 식사에 최고 평점."
        },
        "cafe": {
            "name": "보나슈 (산들소리수목원 내 힐링베이커리)",
            "menu": "수제 단팥빵 & 산들라떼 & 시원한 식혜",
            "address": "경기 남양주시 불암산로 59번길 48-31",
            "features": "수목원 전경이 한눈에 내려다보이는 야외 테라스. 휠체어/유모차 진입 가능.",
            "kid_senior_tip": "수목원 관람 후 이동 없이 바로 카페에서 티타임 가능."
        },
        "mode4_summary": "오전 동물먹이 & 뗏목타기 ➔ 점심 석쇠불고기 쌈밥 ➔ 수목원 내 힐링카페 빵타임",
        "mode6_summary": "불암산 자락 평지 산책 ➔ 부드러운 불고기 쌈밥 ➔ 숲속 그늘 툇마루 쉼터",
        "youtube_url": "https://www.youtube.com/results?search_query=산들소리수목원+아이랑+목향원",
        "naver_blog_url": "https://search.naver.com/search.naver?query=산들소리수목원+휠체어+유모차+목향원",
        "navi_kakao": "https://map.kakao.com/link/to/산들소리수목원,37.6621,127.1082",
        "navi_naver": "https://map.naver.com/v5/search/산들소리수목원"
    }
    print("[정보] 새로운 나들이 코스를 발굴하여 DB에 추가합니다...")
    add_custom_course(sample_discovery)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="하남 미사 가족나들이 자동 수집기")
    parser.add_argument("--test", action="store_true", help="샘플 신규 여행지 추가 및 카톡 알림 테스트")
    args = parser.parse_args()

    if args.test:
        run_sample_auto_update()
    else:
        print("[사용법 안내]")
        print("1. 테스트 실행: python auto_collector.py --test")
        print("2. trips_data.json 파일에 신규 코스가 누적되고 카카오톡 알림이 발송됩니다.")
