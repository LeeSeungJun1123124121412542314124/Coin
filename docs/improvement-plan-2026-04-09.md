# 프로젝트 개선 계획서

작성일: 2026-04-09
대상: `d:\Dev\Coin` 전체 (백엔드/봇/프론트엔드/인프라)

---

## 1. 안정성/운영

### 1-1. API 캐싱 부재
- **현재**: `/api/dashboard` 등 매 요청마다 외부 API(CoinGecko, Yahoo Finance, FRED, Bybit 등) 7개+ 직접 호출
- **위험**: 동시 사용자 증가 시 외부 API rate limit 소진, 응답 지연
- **위치**: 모든 라우터 (`dashboard_routes.py`, `market_routes.py`, `liquidity_routes.py` 등)
- **개선**: `@cached` 데코레이터를 주요 엔드포인트에 적용 (CoinGecko 30s, FRED 1h, Fear&Greed 6h 등)

### 1-2. 스케줄 잡 재시도 로직 없음
- **현재**: 외부 API 실패 시 해당 날의 데이터 영구 누락. `collect_spf`, `collect_volume` 등 모두 실패 시 `return`으로 종료
- **대조**: `data_collector.py`의 `_retry_async`에는 3회 지수 백오프 재시도 구현되어 있음 — 잡에는 미적용
- **위치**: `dashboard/backend/jobs/` 4개 파일 전체
- **개선**: 잡 실행 래퍼에 재시도 로직(3회, 지수 백오프) 추가

### 1-3. 잡 실패 알림 없음
- **현재**: `logger.error()`만 남기고 조용히 실패. 운영자가 인지 불가
- **위치**: `dashboard/backend/jobs/` 전체 + `main.py` 인라인 잡
- **개선**: 잡 실패 시 Telegram으로 운영 알림 발송. APScheduler `event_listener` 활용 가능

### 1-4. 헬스체크 빈약
- **현재**: `/api/health`가 `{"status": "ok"}`만 반환 (`main.py:69`)
- **개선**: DB 연결, 외부 API 접근 가능 여부, 스케줄러 상태, 마지막 잡 실행 시각 포함

### 1-5. 에러 응답 형식 불일치
- **현재**: 화면마다 200+None, 404, 500, 503 제각각
  - `whale_routes.py`: `{"error": "포지션 조회 실패"}` (404)
  - `cvd_routes.py`: `{"error": "데이터 조회 실패", "symbol": symbol}` (500)
  - `dashboard_routes.py`: 해당 필드를 `None`으로 반환 (200)
- **개선**: 통일 스키마 `{"error": {"code": str, "message": str}}` 적용

### 1-6. 코드 중복
- **현재**:
  - `_get_fear_greed()` — `dashboard_routes.py`와 `market_routes.py`에 거의 동일하게 중복
  - `_get_onchain()` — 위 두 파일에 중복
  - `fmt()` — `Dashboard.tsx`와 `Whale.tsx`에 동일한 숫자 포매팅 함수 중복
  - `ScoreBar` — `SPF.tsx`와 `Research.tsx`에 중복 구현
  - `LEVEL_COLORS/LEVEL_BG` — `Market.tsx`와 `Research.tsx`에 동일 상수 중복
- **개선**: 공통 유틸/컴포넌트로 추출

### 1-7. API 응답에 타임스탬프 없음
- **현재**: 대부분의 API 응답에 `generated_at` 등 데이터 수집 시각 없음 (예외: `research_analyzer.py`만 포함)
- **개선**: 주요 엔드포인트 응답에 `generated_at` 필드 추가

---

## 2. 보안

### 2-1. API 인증/인가 부재
- **현재**: `PIN_CODE`, `ADMIN_KEY` 환경변수가 `.env.example`에 정의되어 있지만, 어떤 라우터에서도 검증 코드가 없음
- **위치**: 전체 라우터
- **개선**: 관리용 엔드포인트(POST `/spf-refresh`, `/scheduled-run` 등)에 `ADMIN_KEY` 검증 미들웨어 추가

### 2-2. CORS 설정 없음
- **현재**: FastAPI 앱에 `CORSMiddleware` 미추가
- **위치**: `main.py`
- **개선**: `CORSMiddleware` 추가 + 허용 도메인 환경변수 관리

### 2-3. Rate Limiting 없음
- **현재**: API 레벨 rate limiting 전무. 악의적 대량 호출 시 외부 API rate limit 소진 가능
- **개선**: `slowapi` 등으로 IP 기반 rate limiting 추가

### 2-4. Telegram Webhook 검증 없음
- **현재**: `webhook_server.py:25-39`에서 요청 출처 검증 없음. 누구나 가짜 webhook 전송 가능
- **개선**: Telegram Bot API의 `secret_token` 파라미터 활용하여 검증

### 2-5. POST 엔드포인트 무인증
- **현재**: `/spf-refresh`, `/scheduled-run`, `/scheduled-report` 누구나 호출 가능
- **위치**: `spf_routes.py`, `webhook_server.py`
- **개선**: ADMIN_KEY 또는 IP 화이트리스트 적용

### 2-6. 에러 메시지 내부 정보 노출
- **현재**: `cvd_routes.py:73` 등에서 `str(e)` 그대로 클라이언트 반환 → 내부 경로/스택 노출 위험
- **개선**: 클라이언트에는 일반화된 에러 메시지, 서버 로그에만 상세 정보

### 2-7. PIN 코드 클라이언트 번들 노출
- **현재**: `VITE_PIN_CODE`가 프론트엔드 번들에 포함, 소스 보기로 확인 가능. 기본값 `'0000'` (`App.tsx:30`)
- **개선**: PIN 검증을 서버 측 API로 이동, 클라이언트에서는 서버에 검증 요청

---

## 3. 프론트엔드/UX

### 3-1. 반응형 레이아웃 없음 (모바일 사용 불가)
- **현재**: 모든 화면에서 고정 그리드 사용
  - Volume: `repeat(4, 1fr)` — 모바일에서 4컬럼 불가
  - SPF/Liquidity: `1fr 1fr 1fr` — 모바일 비대응
  - Whale: 7컬럼 그리드 `'32px 1fr 90px 90px 80px 90px 1fr'` — 완전 비대응
  - `@media` 쿼리나 반응형 breakpoint가 전혀 없음
- **개선**: CSS 미디어 쿼리 또는 Tailwind 반응형 유틸리티 적용

### 3-2. URL 라우팅 없음
- **현재**: `react-router-dom`이 설치되어 있지만 미사용. `useState`로 탭 전환 관리. 브라우저 뒤로가기/북마크/직접 URL 접근 불가
- **위치**: `App.tsx`
- **개선**: `react-router-dom` 활용하여 URL 기반 라우팅 구현

### 3-3. 탭 전환 시 상태 소실
- **현재**: 조건부 렌더링(`{activeTab === 'x' && <X />}`)이라 탭 전환 시 스크롤 위치, 선택 종목 등 모든 상태 소실
- **개선**: `display: none` 패턴 또는 탭 상태 캐싱

### 3-4. PIN 인증 새로고침 시 초기화
- **현재**: `useState`만 사용하므로 페이지 새로고침마다 PIN 재입력 필요
- **개선**: `sessionStorage` 활용하여 세션 유지

### 3-5. useApi 훅 한계
- **현재**:
  - 재시도 로직 없음 — 일시적 네트워크 장애 시 다음 폴링까지 에러 유지
  - `AbortController` 없음 — path 변경 시 이전 요청 응답이 늦게 도착하면 잘못된 데이터 설정 (경쟁 조건)
  - 탭 전환 시 매번 새로 fetch (stale-while-revalidate 전략 없음)
- **위치**: `dashboard/frontend/src/hooks/useApi.ts`
- **개선**: 자동 재시도(3회), AbortController, 이전 데이터 캐시 유지

### 3-6. 에러 상태에 재시도 버튼 없음
- **현재**: `refetch` 함수가 useApi에서 반환되지만 어떤 화면에서도 미사용. 에러 시 빨간 텍스트만 표시
- **개선**: 공통 `ErrorDisplay` 컴포넌트에 재시도 버튼 포함

### 3-7. 로딩 스켈레톤 미통일
- **현재**: Dashboard만 `LoadingSkeleton` 사용, Research는 자체 `SkeletonCard`. 나머지 6개 화면은 단순 텍스트 "로드 중..."
- **개선**: 공통 `Skeleton` 컴포넌트 추출하여 전체 화면에 적용

### 3-8. 비활성 탭에서 불필요한 폴링
- **현재**: 백그라운드 탭에서도 모든 API 폴링 계속 실행
- **개선**: `document.hidden` 체크하여 비활성 탭에서 폴링 중지

### 3-9. 마지막 갱신 시간 미표시
- **현재**: 데이터가 언제 마지막으로 갱신되었는지 알 수 없음 (예외: Research만 `generated_at` 표시)
- **개선**: 각 화면에 "마지막 업데이트: X분 전" 표시

### 3-10. @keyframes 미정의 버그
- **현재**: `LoadingSkeleton`의 `animation: 'pulse 1.5s infinite'`, PinScreen의 `animation: 'shake 0.5s'`가 CSS에 정의되지 않아 실제 작동하지 않음
- **위치**: `Dashboard.tsx:169`, `App.tsx(PinScreen):50`
- **개선**: `index.css`에 `@keyframes pulse`, `@keyframes shake` 정의 추가

---

## 4. 인프라/테스트

### 4-1. CI/CD 파이프라인 없음
- **현재**: `.github/workflows/` 미존재. 커밋/PR 시 테스트/린팅/보안 스캔 자동 실행 안 됨
- **개선**: GitHub Actions 워크플로우 추가 (pytest, ruff, mypy, npm build)

### 4-2. APM/에러 추적 없음
- **현재**: Sentry, Prometheus, DataDog 등 모니터링 도구 전무. 서비스 장애 감지 체계가 Railway 기본 healthcheck에만 의존
- **개선**: 최소한 Sentry Free tier 연동으로 에러 추적

### 4-3. dashboard 테스트 전무
- **현재**: `crypto-volatility-bot/tests/`에만 테스트 존재 (봇 코어 80%+ 커버리지). dashboard 백엔드 27파일 + 프론트엔드 전체 테스트 0개
- **추가**: `derivatives_analyzer.py`도 테스트 없음, `tests/integration/` 디렉토리 비어 있음
- **개선**: 최소한 API 라우터 통합 테스트, 프론트엔드는 vitest 설정

### 4-4. Python lock 파일 없음
- **현재**: `requirements.txt`에 `>=` 범위만 사용. `pip freeze` 결과나 `poetry.lock` 없음. 빌드 재현성 미보장
- **개선**: `pip-compile`로 lock 파일 생성 또는 poetry 도입

### 4-5. 환경 분리 없음
- **현재**: dev/staging/prod 구분 없이 단일 `.env` + Railway 환경변수로 운영
- **개선**: 환경별 설정 파일 분리 (최소 dev/prod)

---

## 추가하면 좋을 기능

### 분석 파이프라인 확장
- **OBV (On-Balance Volume)**: 가격-거래량 다이버전스 탐지
- **VWAP**: 기관 참조 가격 — 현재 거래량 기반 지표가 `volume_spike.py`(단순 비율) 뿐
- **MFI (Money Flow Index)**: 거래량 가중 RSI — RSI만으로는 거래량 정보 누락
- **주봉(1w) 타임프레임**: 현재 1d + 4h 두 개만 사용. 장기 추세 확인 부재

### 알림 시스템 강화
- **MEDIUM 레벨 알림**: `score_aggregator.py`에서 MEDIUM을 정의하지만 알림 로직 없음
- **알림 이력 DB 저장**: 발송된 알림을 DB에 기록 → 대시보드에서 과거 알림 조회
- **쿨다운 영속화**: `AlertCooldown._timestamps`가 메모리 dict — 서버 재시작 시 초기화 → 중복 알림

### 잡 실행 이력
- **job_runs 테이블**: `(job_name, started_at, finished_at, status, error_msg)` 추가
- 대시보드에서 잡 실행 현황 조회 가능

---

## 권장 착수 순서

| 순서 | 항목 | 효과 |
|------|------|------|
| 1 | 3-1 반응형 레이아웃 | 모바일에서 사용 가능해짐 (현재 완전 불가) |
| 2 | 1-1 API 캐싱 + 1-2 잡 재시도 | 운영 안정성 대폭 개선 |
| 3 | 2-1~2-3 보안 기본기 (CORS + 인증 + rate limit) | 보안 취약점 해소 |
| 4 | 3-5 useApi 개선 (재시도 + AbortController) | 프론트엔드 안정성 |
| 5 | 4-1 CI/CD 파이프라인 | 코드 품질 게이트 확보 |
| 6 | 나머지 항목 | 점진적 개선 |

---

## 비고

- 본 문서는 코드 기반 전수 분석 결과이며, 라인 단위 감사(audit)는 아님
- 각 항목의 세부 구현은 별도 설계/계획 문서로 분리하여 진행 권장
- 코덱스 전수 점검(`full-repo-review-summary-2026-04-08.md`)의 P0~P2 이슈는 2026-04-09에 수정 완료됨
