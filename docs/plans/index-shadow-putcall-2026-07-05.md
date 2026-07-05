# 지수 방향 그림자 기록 + CBOE Put/Call 조기 수집 구현 계획

- 작성일: 2026-07-05
- 근거 스펙: ouroboros seed `seed_033c945c8938` (A등급, 모호도 0.118)
- 상태: 구현 완료 (2026-07-05) — 리뷰 지적 반영: 200 응답인데 파싱 실패 시 휴장 스킵과 구분해 예외 → 재시도·경보 경로 처리
- 목적: 소급 불가능한 두 데이터의 **적재 시계를 지금부터 돌리는 것**.
- 노출 범위 (2026-07-05 확정): 트랙 A는 그림자 기록만(UI·알림·SPF·리더보드 비노출), **트랙 B는 UI 노출까지 포함**. 트랙 A를 메인에 올리지 않는 이유: ① `predictions`가 date PK의 BTC 단일 전제 스키마라 편입 시 핵심 테이블 개편이 필요하고 진행 중인 SPF 재가중과 충돌, ② 리더보드는 자본을 자산 수로 균등 분할하는 구조(`N_ASSETS`)라 지수 추가 시 진행 중인 2~4주 실측 에쿼티 곡선이 오염됨, ③ 지수는 주말·휴장이 있어 24/7 코인 전제의 일일 리밸런스·정산 캘린더와 맞지 않음.

## 1. 왜 조기 구축인가

| 트랙 | 소급 가능성 | 근거 |
|---|---|---|
| A. 지수 방향 그림자 기록 | **원리적으로 불가** | 포워드 판정 기록은 "그때 시스템이 뭐라고 판정했는가"가 본질이라 사후 재현은 검증 가치가 없음 |
| B. CBOE Put/Call 비율 | **부분만 가능 (갭 존재)** | 공식 무료 아카이브는 2006-11~2019-10 구간만 제공. 2019-10 이후~현재는 당일 통계만 공개 → 매일 적재하지 않으면 영영 빈다 |

## 2. 공통 제약

- 유료 API 금지, 새 패키지 설치 금지 (httpx, apscheduler, pandas 등 기존 의존성만)
- 기존 job 패턴 재사용: `@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)`
- 스키마는 `db/schema.sql`에 `CREATE TABLE IF NOT EXISTS`로 추가
- **비변경 목록** (이 계획이 절대 건드리지 않는 것):
  - `predictions`, `spf_records` 테이블과 SPF 판정 로직
  - `paper_portfolios`, `paper_positions` 등 리더보드 테이블과 `paper_rebalance` job
  - 알림 파이프라인 (`alert_history`, 텔레그램 발송 경로)
  - 기존 코인 테이블 전체

## 3. 트랙 A — 지수 방향 판정 그림자 기록

### 3.1 대상과 신호

- 대상 지수: KOSPI(`^KS11`), S&P500(`^GSPC`) — 둘 다 기존 `yahoo_finance.py` `_TICKERS`에 이미 있음
- 판정 지표: 봇 지표 레지스트리(`crypto-volatility-bot/app/macro/signals.py` `INDICATORS`)에서 지수 일봉에 적용 가능한 것만 재사용:

| 지표 | 유형 | 지수 적용 방법 |
|---|---|---|
| RSI(과열회귀의 재료) | 기술 | 지수 종가에 `_rsi_sig` 그대로 |
| 볼린저밴드 | 기술 | 지수 종가에 `_bollinger_sig` 그대로 |
| 과열회귀 | 기술 결합 | RSI+볼린저 균등 평균 그대로 |
| VIX | 매크로 공통 | `macro_z["vix_level"]` 재사용 (주식에도 같은 방향성) |
| 순유동성 | 매크로 공통 | `macro_z["net_liquidity_13w"]` 재사용 |
| 긴축환경 | 매크로 결합 | DXY+미10년물 결합 재사용 |
| 유동성 | 매크로 결합 | 순유동성+TGA 결합 재사용 |

- **제외**: 복합방향(9팩터에 온체인 포함), MVRV(온체인), 도미넌스(코인 로테이션), 펀딩비 계열, 매수보유(벤치마크 — 정산 시 지수 자체 수익률로 대체 계산 가능하므로 저장 불요)
- **복합 판정**: 위 7개 지표 z의 등가중 평균 `mean_z`. `mean_z ≥ +0.5 → long`, `≤ −0.5 → short`, 그 외 `neutral`. 지표명 `'복합'`으로 개별 지표와 같은 테이블에 병렬 적재.

### 3.2 데이터 흐름

- 지수 종가: 야후 chart API `range=1y`로 일봉 조회 (z 워밍업에 90일 이상 필요 — 13주 변화·rolling z 윈도 고려해 1년 확보)
- 매크로 z: `paper_rebalance` job이 쓰는 소스 빌더 경로를 재사용해 `build_context` 호출 (`main.py`가 봇 경로를 `sys.path`에 추가하는 기존 방식 그대로), `closes`만 지수 종가로 교체

### 3.3 테이블 (신규 1개 — 판정·정산 통합, 기존 `predictions` 패턴)

```sql
CREATE TABLE IF NOT EXISTS index_shadow_judgments (
    date            TEXT NOT NULL,   -- 심볼별 최신 거래일 (KST 기준 YYYY-MM-DD)
    symbol          TEXT NOT NULL CHECK(symbol IN ('^KS11','^GSPC')),
    indicator       TEXT NOT NULL,   -- '복합' 또는 개별 지표명
    z               REAL,
    direction       TEXT NOT NULL CHECK(direction IN ('long','short','neutral')),
    price           REAL NOT NULL,   -- 판정 시점 종가
    price_after_7d  REAL,
    price_after_14d REAL,
    price_after_30d REAL,
    result_7d       TEXT,            -- hit / miss / neutral
    result_14d      TEXT,
    result_30d      TEXT,
    created_at      TEXT NOT NULL,   -- UTC ISO
    PRIMARY KEY (date, symbol, indicator)
);
```

분리 테이블(판정/정산) 대신 통합 1테이블로 확정 — 기존 `predictions`가 같은 구조로 잘 돌고 있고, 그림자 기록은 조인할 소비자도 아직 없다.

### 3.4 판정 job

- 신규 `jobs/index_shadow.py` — `judge_index_shadow()`
- 스케줄: 평일 1일 1회 **08:10 UTC (KST 17:10)** — KOSPI 당일 종가(15:30 KST 마감)와 S&P500 최신 종가(당일 새벽 KST 마감분)가 모두 확보된 시점. `CronTrigger(day_of_week="mon-fri", hour=8, minute=10)`
- `date`는 야후 응답의 심볼별 최신 거래일 사용 (내 실행일이 아님 — 휴장일 중복 실행에도 안전)
- 멱등: `INSERT OR REPLACE` (같은 date·symbol·indicator 재실행 시 덮어씀)
- 실패: 기존 패턴 그대로. 야후 응답 없으면 해당 심볼 건너뛰고 WARNING (전체 job 실패 아님)

### 3.5 정산 job

- 같은 파일에 `settle_index_shadow()` — `update_predictions` 패턴 복제
- 스케줄: 판정 직후 **08:20 UTC**. 미정산 스캔 범위: `result_* IS NULL AND date <= today - horizon`인 행 전부 (과거 밀린 정산도 자동 소화)
- 판정 규칙 (캘린더일 horizon 7/14/30일, 기존 `_judge_horizon`과 동일):
  - `long` & 변화 > +1% → hit / `short` & 변화 < −1% → hit / `direction = neutral` → 'neutral' / 그 외 → miss
  - 비교가는 date+horizon 이후 가장 가까운 거래일 종가 (야후 히스토리에서 조회)

### 3.6 검증 (구현 시 성공 기준)

| # | 기준 | 검증 명령 |
|---|---|---|
| A1 | 1회 실행 후 지수 2개 × 지표 8종(7개+복합) 적재 | `sqlite3 DB "SELECT COUNT(*) FROM index_shadow_judgments WHERE date=(SELECT MAX(date) FROM index_shadow_judgments)"` → 16 |
| A2 | 재실행 멱등 | 같은 날 2회 실행 후 A1 카운트 불변 |
| A3 | 방향 값 유효 | `SELECT COUNT(*) ... WHERE direction NOT IN ('long','short','neutral')` → 0 |
| A4 | 정산 로직 | 과거 날짜 fixture 행 삽입 → `settle_index_shadow()` → result_7d 채워짐 (pytest) |
| A5 | 비변경 보장 | 기존 pytest 전체 통과 + `/api/spf-*`, `/api/leaderboard` 응답 구조 무변경 |

## 4. 트랙 B — CBOE Put/Call 비율 일별 수집

### 4.1 수집

- 신규 수집기 `collectors/cboe.py` — CBOE 당일 시장 통계에서 total/equity/index put/call 비율 3종 추출
- 엔드포인트: `cdn.cboe.com`의 일별 통계 (미결 — §6 참고. 후보: `https://cdn.cboe.com/data/us/options/market_statistics/daily/` 계열 JSON. 구현 첫 단계에서 실제 응답 확인 후 파서 확정)
- User-Agent 헤더 필수 가정 (CDN 차단 회피), httpx 사용

### 4.2 테이블 (신규 1개)

```sql
CREATE TABLE IF NOT EXISTS cboe_putcall (
    date       TEXT PRIMARY KEY,  -- 미국 거래일 (ET 기준 YYYY-MM-DD)
    total_pc   REAL,
    equity_pc  REAL,
    index_pc   REAL,
    updated_at TEXT NOT NULL      -- UTC ISO
);
```

### 4.3 job

- 신규 `jobs/collect_putcall.py`
- 스케줄: 평일 1일 1회 **22:30 UTC (KST 07:30, ET 17:30/18:30)** — 미국 장 마감 후 통계 확정 시점. `CronTrigger(day_of_week="mon-fri", hour=22, minute=30)`
- 미국 휴장일: 응답 404 → INFO 로그 후 정상 종료 (스킵, 실패 아님)
- 200 응답인데 파싱 실패: 페이지 구조 변경 의심 → 예외 처리 (휴장 스킵과 구분 — 조용한 수집 중단은 소급 불가 데이터라 영구 갭이 되므로 반드시 경보)
- 그 외 오류 포함: `@async_retry` 3회 후 `notify_job_failure`
- 멱등: `INSERT OR REPLACE`

### 4.4 UI 노출 — 볼륨트래커 미국 탭

- **선행 조건**: 1차분([stock-menu-expansion-2026-07-05.md](stock-menu-expansion-2026-07-05.md)) 머지 후. 볼륨트래커의 자산군 탭 구조와 미국 탭(주식 F&G 게이지)이 1차분에서 만들어지므로, 그 위에 얹는다. 1차분 구현과 동시 진행 금지(같은 화면 충돌).
- **API**: `GET /api/volume/putcall?days=90` → `{stale, records: [{date, total_pc, equity_pc, index_pc}]}` (날짜 오름차순)
- **UI**: 볼륨트래커 미국 탭에 주식 F&G 게이지 아래 배치 — equity P/C 현재값 카드(0.7 미만 과열/1.0 초과 공포 안내) + 90일 라인차트(equity 기본, total/index 토글)
- **stale 규칙**: 1차분 공통 fallback 정책과 동일 (일별 수집 48시간 초과 시 `stale: true`, UI 회색 배지)

### 4.5 선택 항목 — 과거 아카이브 백필 (이번 범위 아님, 별도 결정)

- CBOE 공식 무료 아카이브: Total 1995-09~2003-12, Total/Index/Equity 2006-11~2019-10 (.xls/.csv)
- 실행하면 2019-10 이전 장기 히스토리 확보. 단 **2019-10~수집 시작일 갭은 무엇으로도 못 메움** — 이것이 조기 구축의 이유.
- 백필은 1회성 스크립트로 충분하므로 상시 job에 넣지 않는다.

### 4.6 검증

| # | 기준 | 검증 명령 |
|---|---|---|
| B1 | 1회 실행 후 당일 1행, 3개 비율 NOT NULL | `sqlite3 DB "SELECT total_pc, equity_pc, index_pc FROM cboe_putcall ORDER BY date DESC LIMIT 1"` |
| B2 | 재실행 멱등 | 2회 실행 후 행 수 불변 |
| B3 | 휴장일 처리 | 휴장일 fixture 응답 → 0행 삽입·0알림·exit 정상 (pytest) |
| B4 | 값 범위 타당성 | 비율이 0.3~2.0 범위 밖이면 WARNING 로그 (수집은 함) |
| B5 | UI 노출 (4.4 단계) | curl `GET /api/volume/putcall?days=90` → 200 + 필드 확인, 볼륨트래커 미국 탭 렌더 확인 |

## 5. 구현 단계

| 단계 | 내용 | 검증 |
|---|---|---|
| 1 | 스키마 2개 테이블 추가 | 서버 기동 후 테이블 존재 확인, 기존 테스트 통과 |
| 2 | 트랙 B (작고 독립적): CBOE 수집기 + job (적재만) | B1~B4 |
| 3 | 트랙 A 판정: 지수 종가 조회 + 지표 z 계산 + 적재 | A1~A3 |
| 4 | 트랙 A 정산 | A4 |
| 5 | 회귀 전체 | A5 |
| 6 | 트랙 B UI 노출 (§4.4) — **1차분 머지 후에만** | B5 |

단계별 독립 커밋. 트랙 B 적재를 먼저 하는 이유: 의존성이 없고, CBOE 엔드포인트 확인(§6)이 실패하더라도 트랙 A는 영향 없이 진행 가능. 6단계만 1차분 머지에 블로킹되며, 1~5단계는 1차분과 독립적으로 즉시 진행 가능.

## 6. 미결 사항 (구현 시 결정)

- CBOE 일별 통계의 정확한 URL·응답 포맷 — 구현 1단계에서 실제 확인. 만약 무료 당일 데이터가 JSON으로 제공되지 않으면 daily statistics 페이지 파싱으로 대체하고, 그것도 불가하면 트랙 B를 보류하고 사용자에게 보고.
- 봇 지표 함수를 dashboard job에서 import하는 방식 — `paper_rebalance`가 이미 쓰는 경로를 그대로 따르되, 지수 closes 주입이 `build_context`의 `ASSETS` 가정과 충돌하면 신호 함수(`_rsi_sig` 등)만 직접 호출하는 얇은 우회로 전환 (봇 코드는 수정하지 않음).

## 7. Non-Goals

- **트랙 A의 UI 노출** (그림자 기록이 몇 주 쌓인 뒤 hit rate를 보고 노출·편입 여부 결정)
- 알림 발송, SPF·리더보드 편입 (트랙 A·B 공통 — 문서 상단 "노출 범위"의 구조적 이유 참고)
- 미국 개별주, KOSDAQ 지수 판정 (KOSPI·S&P500 2개로 시작)
- CBOE 과거 아카이브 백필 (선택 — §4.5)
