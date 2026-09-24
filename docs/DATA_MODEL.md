# 데이터 구조 (재구축판)

핵심 원칙: **장소(place)가 원자 단위**, 모든 사실은 **출처(source)를 가리킨다**, 코스(course)는 검증된 장소들의 조합.
출처 없는 값은 `null` 또는 `"unknown"`이고 화면에 "확인 필요"로 뜬다. (1차본은 코스 안에 문장으로 다 섞여 있어 검증이 불가능했음)

## data/places.json  — 검증된 장소
```jsonc
{
  "id": "naver-35708336",
  "name": "화담숲",
  "kind": "attraction",            // attraction | restaurant | cafe | camping
  "themes": ["forest"],            // animal|forest|water|craft|camping|kids
  "naver": {                       // 네이버 플레이스에서 읽은 값만
    "place_id": "35708336", "category": "식물원,수목원",
    "road_address": "경기 광주시 도척면 도척윗로 278-1",
    "x": 127.2894272, "y": 37.340776,
    "score": 4.49, "reviews": 11137, "blog_reviews": 28390,
    "status": "운영 중", "conveniences": ["주차"], "fetched_at": "2026-09-24"
  },
  "nav": {                         // 좌표는 위 naver.x/y 그대로
    "app_navigation": "nmap://navigation?dlat=…&dlng=…&dname=…&appname=…",
    "web_place": "https://map.naver.com/p/entry/place/35708336"
  },
  "drive": {"min": 47, "km": 41.2, "method": "OSRM", "fetched_at": "2026-09-24"},
  "price": {"meal_4p_krw": null, "evidence": []},
  "family": {
    "mode_a": [{"text": "동물 먹이주기 체험", "src": "yt:VIDEOID@312"}],
    "mode_b": {
      "positive": [{"text": "입구부터 완만한 평지", "src": "yt:VIDEOID@190"}],
      "negative": [{"text": "후반부 오르막 구간", "src": "blog:URL"}],
      "unknown": ["좌석 형태", "장애인 화장실"]
    }
  },
  "sources": ["yt:VIDEOID", "blog:URL"],
  "scores": {"total": 78, "tier": "recommended",
             "breakdown": {"reputation": 27, "evidence": 20, "family_fit": 18, "practicality": 13},
             "gates": {"pass": true, "failed": []}},
  "evidence_date": "2026-06-12", "verified_at": "2026-09-24", "flags": []
}
```

## data/sources.json — 읽은 콘텐츠와 신뢰도
```jsonc
{
  "id": "yt:VIDEOID", "type": "youtube",
  "url": "https://www.youtube.com/watch?v=VIDEOID", "title": "…", "channel": "…",
  "upload_date": "2026-06-12", "views": 123456, "comments": 321, "likes": 4567, "subscribers": 89000,
  "sponsored_hint": [], "has_captions": true, "read_at": "2026-09-24",
  "credibility": {"total": 72, "recency": 25, "engagement": 18, "channel": 14, "info_density": 15, "sponsor": 0},
  "mentions": [{"place": "naver-35708336", "t": 312, "note": "동물 먹이주기, 입장료 언급"}]
}
```
링크는 항상 `…watch?v=ID&t=초`(타임스탬프)로 만든다. 블로그는 `{"type":"blog","url":"https://blog.naver.com/…"}`.

## data/courses.json — 하루 코스 (장소들의 조합)
```jsonc
{
  "id": "course-gwangju-hwadam", "title": "…", "region": "경기 광주",
  "anchor": "naver-35708336",                 // 메인 체험
  "meals":  ["naver-…", "naver-…", "naver-…"], // 1·2·3순위 (2순위 아이입맛, 3순위 속편한 한식/입식)
  "cafes":  ["naver-…", "naver-…"],            // 1·2순위
  "modes": {"a": true, "b": "conditional"},    // 4인 / 6인(파킨슨) 적합
  "est_cost_4p_krw": 68000,                    // 근거 있는 가격의 합, 없으면 null
  "drive_min": 47, "notes": []
}
```

## 검증 (tools/verify.py, 게시 전 필수)
- 모든 `nav`가 `naver.x/y`와 일치, 좌표가 주소와 일치(집에서 반경 이내), 링크 형식 검사
- 모든 `src`가 실제 `sources.json` 항목을 가리키는지, 유튜브 링크가 검색 URL이 아닌지
- 게이트/점수 재계산이 저장값과 일치하는지, 필수 필드 누락 여부
- 결과를 그대로 보고(통과/실패 개수 포함)
