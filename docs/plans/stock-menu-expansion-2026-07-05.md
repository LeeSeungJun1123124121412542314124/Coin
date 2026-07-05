# 주식 데이터 메뉴 확장 구현 계획 (미국·한국 주식)

- 작성일: 2026-07-05
- 근거 스펙: ouroboros seed `seed_033ab09abc75` (A등급, 모호도 0.115)
- 상태: 계획 확정 — 구현 미착수
- 범위: 계획 문서만 산출. 코드 구현은 이 문서 승인 후 별도 작업.

## 1. 목표

코인 중심 투자분석 대시보드의 기존 3개 메뉴(고래추적·볼륨트래커·시장분석)에 미국/한국 주식 데이터를 통합한다. **새 메뉴는 추가하지 않고**, 각 메뉴 내부에 자산군 탭 토글(코인/한국/미국)을 둔다.

## 2. 제약 (전 트랙 공통)

- 유료 API 금지. 무료 소스만: 네이버 금융, 야후 파이낸스, CNN 비공식 엔드포인트
- 새 패키지 설치 금지 (httpx, apscheduler, yfinance 등 기존 의존성만)
- 기존 수집기·스케줄러(`main.py _register_jobs`)·DB 패턴(`schema.sql CREATE TABLE IF NOT EXISTS`) 재사용
- 기존 코인 테이블 스키마 변경 금지
- SPF·리더보드·알림 파이프라인 미변경

## 3. 코드베이스 확인 결과 (계획 보정 근거)

계획 수립 전 실제 코드를 확인한 결과, 시드 스펙 대비 다음을 보정했다.

| 확인 사실 | 위치 | 계획 반영 |
|---|---|---|
| DXY(`DX-Y.NYB`)·미 10년물(`^TNX`)·KOSPI·KOSDAQ이 이미 수집됨 | `collectors/yahoo_finance.py` `_TICKERS` | 시장분석 트랙 신규 티커는 `KRW=X`(원달러) 1개뿐 |
| 야후 수집은 라이브+캐시 방식, DB 히스토리 테이블 없음. `fetch_index_history`가 30일 히스토리를 야후에서 직접 조회 | `collectors/yahoo_finance.py`, `api/stock_index_routes.py` | 시장분석 트랙은 **DB 백필 불필요** — 야후 chart API `range` 파라미터로 90일 조회 |
| `volume_daily.krx_krw` 컬럼이 스키마에 있으나 수집 job이 채우지 않는 dead column | `db/schema.sql:71`, `jobs/collect_volume.py` | 삭제·재활용하지 않음(코인 테이블 무변경 원칙). KOSPI/KOSDAQ 거래대금은 신규 테이블로 분리 |
| job 패턴: `@async_retry(max_retries=3, on_failure=notify_job_failure)` | `jobs/collect_volume.py` | 신규 job 3개 모두 동일 데코레이터 사용 |
| 스케줄러는 UTC 기준 cron | `main.py:85` | 수집 시각은 UTC로 명기, KST 병기 |
| 프론트 데이터 조회는 `useApi<T>(경로, 폴링ms)` 훅 | `screens/*.tsx` | 신규 API도 동일 훅으로 소비 |
| 라우터는 `/api` prefix + 인증 의존성으로 등록 | `main.py:255-273` | 신규 라우트도 동일 방식 |

## 4. 트랙별 계획

### 트랙 1 — 고래추적: 한국주식 외국인·기관 매매동향

"큰손이 어느 쪽에 서 있나"를 코인(Hyperliquid 지갑)과 같은 개념으로 한국주식(외국인·기관 수급)에 적용한다.

- **수집**: `collectors/naver_finance.py`에 투자자별 매매동향 조회 함수 추가. 네이버 금융 시장별(KOSPI/KOSDAQ) 일별 외국인·기관·개인 순매수 데이터.
- **주기**: 평일 1일 1회, 08:30 UTC (KST 17:30, 장 마감 후 수급 확정 시점 이후). `CronTrigger(day_of_week="mon-fri", hour=8, minute=30)`
- **백필**: 최초 실행 시 30영업일. 네이버 일별 페이지가 과거 데이터를 제공하므로 별도 소스 불필요.
- **테이블** (신규):
  ```sql
  CREATE TABLE IF NOT EXISTS kr_investor_flow (
      date            TEXT NOT NULL,   -- KST 거래일 (YYYY-MM-DD)
      market          TEXT NOT NULL CHECK(market IN ('KOSPI','KOSDAQ')),
      foreign_net     REAL,            -- 외국인 순매수 (억원)
      institution_net REAL,            -- 기관 순매수 (억원)
      individual_net  REAL,            -- 개인 순매수 (억원)
      PRIMARY KEY (date, market)
  );
  ```
- **API**: `GET /api/whale/kr-investor-flow?market=KOSPI&days=30` → `{market, stale, records: [{date, foreign_net, institution_net, individual_net}]}` (최대 `days`개, 날짜 오름차순)
- **UI**: `Whale.tsx`에 자산군 탭(코인/한국). "한국" 탭에서 시장 선택(KOSPI/KOSDAQ) + 외국인·기관 2계열 막대차트(개인은 보조 표시), 누적 순매수 라인 오버레이.
- **검증**:
  - pytest: 수집 파서 단위 테스트(네이버 응답 fixture → 파싱 결과), API 응답 스키마 테스트
  - curl: `GET /api/whale/kr-investor-flow?market=KOSPI&days=30` → 200, 레코드 ≤ 30
  - 브라우저: 고래추적 → 한국 탭 → 차트 렌더 확인

### 트랙 2 — 볼륨트래커: 주식판 Fear & Greed + KOSPI/KOSDAQ 거래대금

"시장 열기 측정" 개념을 주식으로 확장한다.

- **수집 A — CNN Fear & Greed(주식판)**:
  - 신규 수집기 `collectors/cnn_fear_greed.py`. 엔드포인트: `https://production.dataviz.cnn.io/index/fearandgreed/graphdata` (비공식 JSON, User-Agent 헤더 필요)
  - 주기: 1시간 (`IntervalTrigger(hours=1)`). 백필 없음 — CNN 응답에 자체 히스토리가 포함되므로 수집 시점부터 적재.
  - 테이블 (신규):
    ```sql
    CREATE TABLE IF NOT EXISTS stock_fear_greed (
        date       TEXT PRIMARY KEY,  -- KST 기준일
        value      REAL NOT NULL,     -- 0~100
        rating     TEXT,              -- extreme fear ~ extreme greed
        updated_at TEXT NOT NULL      -- UTC ISO
    );
    ```
    (하루 1행 UPSERT — 시간 단위 이력은 비목표)
- **수집 B — KOSPI/KOSDAQ 일별 거래대금**:
  - `collectors/naver_finance.py` 확장 (트랙 1과 같은 시장별 일별 시세 페이지에서 거래대금 추출 — 수집 함수 공유 검토)
  - 주기: 트랙 1과 동일 job에서 함께 수집 (평일 08:30 UTC)
  - 백필: 30영업일
  - 테이블 (신규):
    ```sql
    CREATE TABLE IF NOT EXISTS kr_market_volume (
        date         TEXT PRIMARY KEY, -- KST 거래일
        kospi_value  REAL,             -- 거래대금 (조원)
        kosdaq_value REAL
    );
    ```
    `volume_daily.krx_krw`는 그대로 두고 사용하지 않는다 (dead column 현상 유지).
- **API**:
  - `GET /api/volume/stock-fear-greed` → `{value, rating, updated_at, stale}`
  - `GET /api/volume/kr-market-volume?days=30` → `{stale, records: [{date, kospi_value, kosdaq_value}]}`
- **UI**: `Volume.tsx`에 자산군 탭(코인/한국/미국).
  - 미국 탭: 주식판 F&G 게이지 (기존 코인 F&G 게이지 컴포넌트 재사용)
  - 한국 탭: KOSPI/KOSDAQ 거래대금 30일 막대차트
  - 코인 탭: 기존 화면 그대로
- **검증**:
  - pytest: CNN 응답 fixture 파싱 테스트, 거래대금 파싱 테스트, API 스키마 테스트
  - curl: 두 엔드포인트 200 + 필드 존재 확인
  - 브라우저: 볼륨트래커 3개 탭 전환 렌더 확인

### 트랙 3 — 시장분석: DXY·미 10년물·원달러 환율

- **수집**: `yahoo_finance.py` `_TICKERS`에 `KRW=X`(원달러 환율) 1개만 추가. DXY·^TNX는 이미 존재.
- **히스토리**: DB 저장·백필 없음. `fetch_index_history` 패턴을 확장해 야후 chart API `range=3mo`로 90일 종가를 직접 조회 (기존 30일 함수에 range 파라미터 추가 또는 대상 티커 확장 — 구현 시 기존 함수 시그니처 유지 우선).
- **API**: 기존 `/api/market-analysis` 응답에 매크로 섹션 확장 또는 `GET /api/market/macro-history?ticker=DX-Y.NYB` 신설. 기존 응답 구조를 확인 후 **기존 소비자(코인 카드)가 깨지지 않는 쪽**으로 결정 — 기본안은 신규 엔드포인트 (기존 응답 무변경).
- **UI**: `Market.tsx`에 "미국/환율" 탭. DXY·미 10년물·원달러 3개 라인차트(90일) + 현재가·등락률 카드.
- **검증**:
  - curl: `GET /api/market/macro-history?ticker=KRW=X` (URL 인코딩 `KRW%3DX`) → 200, 히스토리 ≥ 60개
  - 회귀: 기존 `/api/market-analysis` 응답 구조 무변경 확인 (구현 전 스냅샷 → 구현 후 비교)
  - 브라우저: 시장분석 → 미국/환율 탭 3개 차트 렌더

## 5. 공통 구조 결정 (확정 사항)

### 5.1 자산군 탭 라우팅
- URL 쿼리스트링 `?asset=coin|kr|us`. 기본값·잘못된 값은 `coin` 폴백.
- 탭 전환 시 `history.replaceState`로 URL 갱신 (뒤로가기 히스토리 오염 방지). 딥링크·새로고침 시 탭 유지.
- 탭 UI는 3개 화면 공통 컴포넌트 1개로 구현 (`shared/AssetTabs.tsx`) — 이미 3곳에서 반복 확정이므로 공통화 조건 충족.

### 5.2 장애 대응 (fallback)
- 수집 실패 시: 기존 패턴 그대로 `@async_retry(max_retries=3, on_failure=notify_job_failure)`. 스케줄러는 중단하지 않음.
- API는 항상 DB의 마지막 성공 데이터를 서빙하고, 신선도 SLA(수집 주기의 2배) 초과 시 `stale: true` 플래그.
- UI는 `stale: true`일 때 "N시간 전 데이터" 회색 배지 표시.
- 신선도 기준: 일별 수집(트랙1·2B) = 48시간(주말 고려 시 영업일 기준 판정), 시간별 수집(트랙2A) = 2시간.

### 5.3 타임존 규약
- 신규 테이블 `date` 컬럼: KST 거래일 (`YYYY-MM-DD`) — 한국 시장 데이터의 자연 단위.
- `updated_at` 컬럼: UTC ISO 문자열 — 기존 테이블 `datetime('now')` 관례와 동일.
- 표시단(UI)에서만 KST 변환.

### 5.4 알려진 위험
- 네이버 금융·CNN은 비공식 소스 — 구조 변경 시 수집 중단 가능. 파싱 실패는 ERROR 로그 + 기존 `notify_job_failure` 경보로 감지.
- 이 PC 환경에서 새 도메인(CNN) 첫 연결 시 Avast TLS 가로채기로 실패할 수 있음 — 발생 시 기존 CA 번들 우회 방식 적용.

## 6. Non-Goals (이번 범위 제외)

- 미국 개별주 종목 데이터·스크리너 (13F, 내부자 거래 포함 — 후순위 별도 계획)
- KRX 프로그램매매, 옵션 기반 F&G, Put/Call 비율
- CVD 스크리너 주식판, SPF·리더보드·알림 파이프라인의 주식 심볼 편입
- 실시간 WebSocket, 인증·배포 구성 변경, 유료 API

## 7. 구현 단계 (구현 착수 시)

| 단계 | 내용 | 검증 |
|---|---|---|
| 1 | 스키마 추가 (신규 테이블 3개) | 서버 기동 후 `sqlite3 .tables`로 생성 확인, 기존 테스트 전체 통과 |
| 2 | 트랙 3 (가장 작음): `KRW=X` 티커 + 히스토리 API + 미국/환율 탭 | 트랙 3 검증 절차 + `/api/market-analysis` 회귀 |
| 3 | 공통 `AssetTabs` 컴포넌트 + 쿼리스트링 라우팅 | 딥링크/새로고침/잘못된 값 폴백 수동 확인 |
| 4 | 트랙 1: 네이버 수급 수집기 + job + API + 고래추적 한국 탭 | 트랙 1 검증 절차 |
| 5 | 트랙 2: CNN F&G + 거래대금 + 볼륨트래커 탭 | 트랙 2 검증 절차 |
| 6 | 회귀 전체: 기존 코인 API(`/api/volume-data`, `/api/market-analysis`, `/api/hyperliquid-whales`) 200 + 기존 pytest 전체 통과 | 실패 시에만 보고 |

각 단계는 독립 커밋 (`feat: ...` 한국어 메시지, 하나의 목적 = 하나의 커밋).

## 8. 미결 사항 (구현 시 결정)

- 네이버 투자자별 매매동향의 정확한 엔드포인트/페이지 구조 — 구현 시 실제 응답 확인 후 파서 확정 (모바일 API `m.stock.naver.com` 우선 검토, 기존 `naver_finance.py`가 같은 도메인 사용 중)
- 트랙 3 API를 기존 `/api/market-analysis` 확장으로 할지 신규 엔드포인트로 할지 — 기본안은 신규 (기존 응답 무변경)
