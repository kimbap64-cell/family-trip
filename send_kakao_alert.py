"""
[send_kakao_alert.py]
카카오톡 '나에게 보내기' API를 통해 새로운 주말 나들이 추천 코스를 카톡으로 자동 발송하는 모듈입니다.
리프레시 토큰(Refresh Token)을 지원하여 토큰 만료 시 자동으로 재발급을 시도합니다.
"""

import os
import json
import requests
from datetime import datetime

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "kakao_token.json")

def load_token():
    """kakao_token.json 파일에서 인증 토큰 로드"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[경고] 토큰 파일 읽기 실패: {e}")
    return None

def save_token(token_data):
    """갱신된 인증 토큰 저장"""
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)
    print("[성공] 카카오 토큰 정보가 갱신되어 저장되었습니다.")

def refresh_access_token(rest_api_key, refresh_token):
    """리프레시 토큰을 이용해 액세스 토큰 자동 재발급"""
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token
    }
    resp = requests.post(url, data=data)
    if resp.status_code == 200:
        new_data = resp.json()
        token_info = load_token() or {}
        token_info["access_token"] = new_data["access_token"]
        if "refresh_token" in new_data:
            token_info["refresh_token"] = new_data["refresh_token"]
        save_token(token_info)
        return new_data["access_token"]
    else:
        print(f"[오류] 토큰 재발급 실패: {resp.text}")
        return None

def send_kakao_trip_alert(course_info, web_url="https://your-domain.github.io/travel"):
    """
    새로운 나들이 코스를 카카오톡 나에게 보내기로 발송
    course_info 예시:
    {
      "course_title": "송도 센트럴파크 & 솔찬공원 바다뷰 코스",
      "area_name": "인천 송도",
      "duration_min": 60,
      "cost_estimate_4p": "약 68,000원",
      "spot1_name": "송도 센트럴파크 꽃사슴정원",
      "restaurant_name": "바다앞 꼬막집 / 생선구이",
      "cafe_name": "케이슨24 바다뷰 카페"
    }
    """
    token_info = load_token()
    
    # 토큰 파일이 없거나 키가 비어있는 경우 시뮬레이션 안내 출력
    if not token_info or not token_info.get("access_token"):
        print("\n" + "="*50)
        print("[카카오톡 알림 발송 시뮬레이션 (Dry Run)]")
        print(f"📌 제목: 🚗 [하남 미사 출발] 이번 주말 추천 나들이 도착!")
        print(f"📍 코스: {course_info.get('course_title')} ({course_info.get('area_name')})")
        print(f"⏱️ 소요시간: 편도 약 {course_info.get('duration_min')}분 | 💰 4인 식비: {course_info.get('cost_estimate_4p')}")
        print(f"1️⃣ 오전: {course_info.get('spot1_name')}")
        print(f"2️⃣ 점심: {course_info.get('restaurant_name')}")
        print(f"3️⃣ 오후: {course_info.get('cafe_name')}")
        print(f"🔗 웹 가이드 링크: {web_url}")
        print("="*50)
        print("💡 [안내] 실제 카카오톡 메시지를 받으시려면 '카톡알림_및_부부공유_세팅가이드.md'를 참고해 kakao_token.json을 설정해주세요.\n")
        return True

    access_token = token_info.get("access_token")
    rest_api_key = token_info.get("rest_api_key")
    refresh_token = token_info.get("refresh_token")

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # 카카오톡 피드 템플릿 구성
    template_object = {
        "object_type": "feed",
        "content": {
            "title": f"🚗 [하남 미사] 주말 나들이 추천: {course_info.get('course_title')}",
            "description": f"⏱️ 편도 약 {course_info.get('duration_min')}분 | 💰 4인 {course_info.get('cost_estimate_4p')}\n1️⃣ {course_info.get('spot1_name')}\n2️⃣ {course_info.get('restaurant_name')}\n3️⃣ {course_info.get('cafe_name')}",
            "image_url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&auto=format&fit=crop&q=60",
            "link": {
                "web_url": web_url,
                "mobile_web_url": web_url
            }
        },
        "buttons": [
            {
                "title": "📱 모바일 가이드 보기",
                "link": {
                    "web_url": web_url,
                    "mobile_web_url": web_url
                }
            }
        ]
    }

    payload = {"template_object": json.dumps(template_object, ensure_ascii=False)}
    resp = requests.post(url, headers=headers, data=payload)

    # 401 Unauthorized인 경우 토큰 재발급 시도
    if resp.status_code == 401 and rest_api_key and refresh_token:
        print("[알림] 카카오 액세스 토큰이 만료되어 재발급을 시도합니다...")
        new_token = refresh_access_token(rest_api_key, refresh_token)
        if new_token:
            headers["Authorization"] = f"Bearer {new_token}"
            resp = requests.post(url, headers=headers, data=payload)

    if resp.status_code == 200:
        print("[성공] 카카오톡 '나에게 보내기' 메시지가 성공적으로 발송되었습니다!")
        return True
    else:
        print(f"[실패] 카카오톡 전송 실패: {resp.status_code} - {resp.text}")
        return False

if __name__ == "__main__":
    sample_course = {
        "course_title": "송도 센트럴파크 사슴농장 & 솔찬공원 바다뷰 코스",
        "area_name": "인천 송도",
        "duration_min": 60,
        "cost_estimate_4p": "약 68,000원",
        "spot1_name": "송도 센트럴파크 (꽃사슴정원 & 수상택시)",
        "restaurant_name": "송도 바다앞 꼬막집 / 생선구이",
        "cafe_name": "케이슨24 바다앞 컬쳐카페"
    }
    send_kakao_trip_alert(sample_course)
