# 봇 리포트 수신과 화면 — 스펙 (2026-11-24)

- 요청: "너가 그록봇이 보낼 수 있도록 길을 만들어줘야함"
- Seed: `seed_c8e0278a987e`
- 봇에게 줄 안내문: `docs/bot-reports-guide.md`

## 1. 배경

그록봇이 매일 일봉 점검, 청산 히트맵, 고래·온체인 소식, 돌파 알림, 주봉 점검을 만들어 채팅으로 보낸다.
그 자료는 봇의 원격 저장 공간에만 있어 투자분석기 서버가 읽을 수 없다.
ETF 순유입, 청산 히트맵, 고래 소식은 투자분석기에 없는 정보다.

이번 범위는 **1단계: 받는 통로와 원문을 그대로 보여 주는 화면**이다.
리서치 카드(ETF 수급·청산 히트맵·고래 소식)와 기준표 등록은 다음 단계로 미룬다.

## 2. 수신 — `POST /api/bot-reports`

- PIN 토큰 없이 호출하고, 헤더 `X-Bot-Key`가 환경변수 `BOT_INGEST_KEY`와 같아야 한다(`hmac.compare_digest`).
- `BOT_INGEST_KEY`가 비어 있으면 어떤 키로도 받지 않고 503 — 키 등록 전에는 수신이 꺼져 있다.
- 키가 없거나 틀리면 401. 키 검사는 요청 제한 안쪽에서 해서 틀린 키로 반복 시도하는 것도 제한에 걸린다.
- IP당 분당 30건 제한(429). 프록시 뒤에서는 사실상 전체 30건/분이다.
- 본문: `kind`(daily_check·weekly_check·heatmap·whale·breakout·other), `title`(1~200자), `body`(1~20,000자),
  `reported_at`(선택, ISO), `data`(선택, 객체, JSON 50,000자 이하). 어기면 422.
- 같은 `kind`·`title`·`body`(SHA-256)를 다시 보내면 새 행을 만들지 않고 기존 `id`와 `duplicate: true`.
- 저장: `bot_reports(id, kind, title, body, data_json, reported_at, received_at, content_hash UNIQUE)`.
- 받은 값은 리서치 점수 계산에 넣지 않는다.
- 포트는 새로 열지 않는다 — 기존 서비스 주소(443)를 그대로 쓴다.

## 3. 조회 — `GET /api/bot-reports`

- 다른 화면과 같은 PIN 토큰 인증.
- `kind`로 거르고 `limit`(기본 50, 최대 200)으로 개수를 제한, `reported_at` 최신순.

## 4. 화면 — "봇 리포트" (`/bot-reports`, 메뉴 묶음 "기록 · 검증")

- 종류 칩: 전체·일봉 점검·주봉 점검·청산 히트맵·고래·온체인·돌파 알림·기타.
- 카드마다 종류, 제목, 한국 시간 시각, 본문. 가장 최근 한 건은 펼쳐 두고 나머지는 첫 문단 미리보기만.
- 본문은 마크다운 일부(표·굵은 글씨·링크·목록·제목)만 해석한다. 새 패키지 없이 `botReportView.ts`의 `parseReportBody`로 블록을 만들고 React 요소로 그린다.
  HTML은 해석하지 않아 글자 그대로 보이고, 링크는 `http`/`https`만 건다.
- 표는 카드 안에서만 가로로 넘겨 본다(모바일 390px에서 화면이 옆으로 밀리지 않게).
- 받은 리포트가 없으면 빈 상태 안내.

## 5. 운영에 필요한 일 (사용자)

1. Coolify 환경변수에 `BOT_INGEST_KEY`를 등록하고 다시 배포한다. 값은 로컬 `D:\Dev\coolify-migration\secrets\bot_ingest_key.txt`에 만들어 두었다(화면·로그에 출력하지 않음).
2. 그록봇에게 `docs/bot-reports-guide.md`와 키를 전달한다.
3. 그록봇이 외부 주소로 전송할 수 있는지는 아직 확인되지 않았다. 안 되면 공유 저장소를 거치는 방식으로 바꿔야 한다.

## 6. 검증

| 기준 | 방법 |
|---|---|
| 키 없음·틀림 401, 키 미등록 503 | pytest |
| 형식 오류 422 (7가지) | pytest |
| 저장과 같은 내용 재전송 무시 | pytest |
| 조회 최신순·kind 필터·limit | pytest |
| 분당 30건 제한 | pytest |
| 수신은 PIN 없이, 조회는 PIN으로 등록 | pytest(`main.py` 등록 확인) + 로컬 서버에서 PIN 없이 조회 401 |
| 본문 해석(표·굵게·링크·목록, HTML·javascript 링크 무시) | node 테스트 |
| 화면(칩·카드·빈 상태·모바일 폭) | 로컬 서버에 예시 3건을 보내고 PC·390px에서 확인 |
