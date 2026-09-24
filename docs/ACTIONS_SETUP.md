# 주간 자동 점검 (GitHub Actions) 설정과 한계

## 하는 일
매주 금요일 08:00(KST)에 클라우드에서 자동 실행:
`상태 점검(별점·리뷰수·폐업 신호) → 점수화 → 사이트 재생성 → verify(오류 0일 때만) → 커밋/푸시(Pages 자동 반영) → 카톡`
사이트 상단에 **마지막 자동 점검일**이 표시되고, 10일 넘게 점검이 없으면 경고가 뜬다.

## 필요한 설정 (사용자, 1회) — 카톡 알림을 받으려면
점검·사이트 갱신에는 비밀키가 **필요 없다**(공개 페이지 조회). 카톡 알림만 아래 Secrets 2개가 필요하다.
GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
| 이름 | 값 (이 PC의 `kakao_token.json` 에서 복사) |
|---|---|
| `KAKAO_REST_API_KEY` | `rest_api_key` 값 |
| `KAKAO_REFRESH_TOKEN` | `refresh_token` 값 |
※ 비밀번호·토큰 입력은 Claude가 대신할 수 없다(직접 붙여넣기). 메모장으로 `kakao_token.json` 을 열어 값만 복사하면 된다.

## 한계 (숨기지 않는다)
- **클라우드 IP 차단 위험**: 네이버 공개 페이지·카카오맵 패널을 GitHub 서버 IP에서 부르면 막힐 수 있다. 막히면 워크플로가 **저장 없이 중단**(exit 2)하고 실패 알림을 보낸다. 이 경우 로컬(집 PC)에서 `python tools/weekly_run.py` 로 대신 돌린다.
- **카카오 refresh_token 만료(약 2개월)**: 카카오가 새 refresh_token 을 발급하면 Actions는 Secrets를 스스로 갱신할 수 없다. 알림이 갑자기 실패하면 Secrets 의 `KAKAO_REFRESH_TOKEN` 을 새 값으로 다시 넣는다(점검·사이트 갱신은 영향 없음).
- **새 장소 발굴·블로그 읽기·판정 검증은 자동화하지 않는다**(Claude 세션에서). 이 워크플로는 이미 검증된 장소의 '상태'만 갱신한다.
- 호출은 quota_guard 캡 안(장소 ~75곳 = 네이버 ~75, 카카오 패널 ~75/100). 장소가 늘면 카카오 패널 캡(일 100) 상향이 필요하며 사용자 승인 후에만 올린다.
- 폐업 판단은 신호일 뿐: 네이버 상세 소멸 또는 카카오 영업상태 변경 + 서로 다른 출처 2건이 모이면 자동 '제외', 1건이면 "폐업 의심" 표시만.

## 수동 실행 / 로컬 실행
- GitHub → Actions → "주간 상태 점검" → Run workflow
- 로컬: `python tools/weekly_run.py` (카톡까지: `--notify`)
