# 수정 계획: 검수 후속 3건 — 경로 탐색 방어 · 봇 로거 · 고래 알림 소생

작성일: 2026-07-04
상태: 구현 확정 (ouroboros seed_3bbca73e2f35, A등급)
근거: [full-review-2026-07-04.md](../full-review-2026-07-04.md) A-2 · B-1 · B-2

## 1. SPA catch-all 경로 탐색 방어 [보안]

- 위치: `dashboard/backend/main.py` spa_fallback (192-197행)
- 원인: `_FRONTEND_DIST / full_path`를 정규화 없이 `is_file()` 후 서빙 — 무인증 라우트라 상위 디렉터리 이동 시퀀스로 dist 밖 파일(.env, crypto.db) 노출 가능
- 수정: 경로 판정을 모듈 레벨 순수 함수 `_safe_static_file(full_path)`로 추출 — `resolve()` 후 `is_relative_to(_FRONTEND_DIST.resolve())` 검증, 밖이면 None → index.html 폴백
- AC: dist 밖 파일 요청 → None(=index.html 서빙, 내용 미노출) / 정상 자산 → 서빙 / 단위테스트로 검증

## 2. 봇 로거 — app.* 모듈 로그 유실 [관측성]

- 위치: `crypto-volatility-bot/app/main.py:17`
- 원인: `setup_logger("crypto-bot")`는 그 이름 로거만 구성. 모든 모듈은 `logging.getLogger(__name__)`("app.*") 사용 → 핸들러 없는 "app" 네임스페이스라 INFO 유실, WARNING은 lastResort stderr
- 수정: `app/main.py`에서 `setup_logger("app", ...)`를 함께 호출해 "app" 네임스페이스 로거에 JSON 핸들러 부착 (모듈 로거들이 propagate로 상속). 루트 로거는 건드리지 않음 — 대시보드 배포(봇 모듈 임포트만)에 영향 없음
- AC: app.* 로거 INFO가 JSON 핸들러로 출력됨을 스트림 캡처 테스트로 검증

## 3. 고래 알림 — 유동량 급증 감지 구현 [죽은 기능 소생]

- 위치: `crypto-volatility-bot/app/data/data_collector.py` fetch_onchain_data
- 원인: `dormant_whale_activated: False` 하드코딩 → `_check_whale` 도달 불가 (판정 원천 데이터 부재)
- 수정 (사용자 확정 — 급증 감지로 구현):
  - CoinMetrics 조회 `limit_per_asset` 1→31, "time" 정렬 후 최신일 판별
  - 일별 총유동량 = FlowInExNtv + FlowOutExNtv
  - 발화 조건: 최신일 유동량 ≥ 직전 30일 중앙값 × `_WHALE_SPIKE_RATIO`(3.0)
  - 억제 조건: 이력 8일 미만 또는 중앙값 ≤ 0 → False
  - 기존 반환 필드(exchange_inflow/outflow/whale_transaction_volume/mvrv)는 최신일 기준 유지 — 분석기·포맷터 무변경
  - 의미 변경: "휴면 고래" → "대규모 온체인 이동 급증" (주석·독스트링 갱신)
- AC: 합성 31일 응답으로 (a) 급증일 True (b) 평상일 False (c) 이력 부족 False (d) 기존 필드 불변

## 공통 제약

한국어 주석 · 외과적 변경 · TDD · 회귀 무파손(봇 316 + 대시보드 65) · 새 의존성 금지(statistics.median) · 기존 httpx mock 컨벤션(`_make_httpx_mock`) 준수 · 커밋 3개(목적별)
