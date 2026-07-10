# 리서치 메뉴 확장 구현 계획 — 반도체 시그널 자동화 + 주식심리 카테고리

- 작성일: 2026-07-05
- 근거 스펙: ouroboros seed `seed_52ae35239243` (A등급, 모호도 0.138)
- 상태: 구현 완료 — 트랙 2 (주식심리) 2026-07-05 완료(f27bd9c), 트랙 1 (반도체 자동화) 2026-07-11 완료
- 트랙 1 구현 편차: 네이버 종목별 데이터가 수량(주) 기준이라 금액은 `순매매량 × 종가`로 환산(억원). HTML 파싱 대신 모바일 JSON API(`m.stock.naver.com/api/stock/{code}/trend`) 사용. 실측 검증: 2026-07-11 기준 삼성 4주 누적 -15.85조 / 하이닉스 -20.92조 → 둘 다 red 판정, 수동 상수와 정합.
- 성격: 둘 다 데이터 적재 대기가 불필요한 "지금 가능한" 작업. 트랙 1은 기존 수동 카드의 유지보수 제거, 트랙 2는 이미 쌓이기 시작한 심리 데이터의 현재값 활용.

## 1. 배경

리서치 메뉴는 8개 카테고리를 병렬 자동 분석하는데([research_analyzer.py](../../dashboard/backend/services/research_analyzer.py) `analyze_all`), 반도체 정점 카드만 9개 시그널을 사람이 손으로 갱신하는 수동 상수(`SEMICONDUCTOR_SIGNALS`, `as_of` 21일 초과 시 갱신 알림)다. 이 중 외국인 순매도 시그널 2개는 우리가 이미 만든 네이버 수집 인프라로 자동화 가능하다. 또 주식 F&G·Put/Call 데이터가 2026-07-05부터 쌓이기 시작했고, 현재값 기반 심리 판정은 표본 축적 없이 바로 가능하다.

## 2. 공통 제약

- 유료 API 금지, 새 패키지 설치 금지
- 기존 패턴 재사용: naver_finance 수집기, `@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)` job 패턴, `schema.sql` DDL 패턴
- **기존 8개 카테고리의 응답 구조 무변경** (프론트가 key별 렌더러를 쓰므로 회귀 금지)
- SPF·리더보드·알림 파이프라인 미변경
- analyzer 내부에서 `notify_job_failure` 호출 금지 — 경보는 수집 job 책임, 분석은 폴백만

## 3. 트랙 1 — 반도체 외국인 순매도 시그널 자동화

### 3.1 자동화 대상 (9개 중 2개만)

| 시그널 id | 종목 | 현재 | 자동화 후 |
|---|---|---|---|
| `samsung_foreign_selling` | 삼성전자 005930 | 수동 상수 (status/note 손 갱신) | 4주 누적 외국인 순매수로 매일 자동 판정 |
| `hynix_foreign_selling` | SK하이닉스 000660 | 수동 상수 | 동일 |

나머지 7개(DRAM 가격·재고·LTA·EPS 컨센서스·capex)는 무료 소스로 자동화 불가 — 수동 유지, `as_of`/21일 stale 알림도 **수동 7개 기준으로 그대로 유지**.

### 3.2 수집

- `collectors/naver_finance.py`에 종목별 투자자 매매동향 조회 함수 추가 (기존 시장 단위 함수와 별개, 같은 도메인)
- 대상 티커: 모듈 상단 상수 `_INVESTOR_FLOW_TICKERS = ("005930", "000660")`
- job: 기존 `jobs/collect_kr_stock.py`의 `collect_kr_investor_flow`(평일 08:30 UTC)에 종목별 수집을 합류 — 신규 job 등록 없음
- 백필: 최초 실행 시 30영업일 (4주 누적 계산에 20영업일 필요 + 여유)

### 3.3 테이블 (신규 1개)

```sql
CREATE TABLE IF NOT EXISTS kr_stock_investor_flow (
    date            TEXT NOT NULL,   -- KST 거래일
    ticker          TEXT NOT NULL,   -- 6자리 종목코드
    foreign_net     REAL,            -- 외국인 순매수 (억원)
    institution_net REAL,            -- 기관 순매수 (억원)
    PRIMARY KEY (date, ticker)
);
```

### 3.4 판정 로직 (오버레이 방식)

- `_analyze_semiconductor_signals()`가 `SEMICONDUCTOR_SIGNALS`를 deepcopy한 뒤, 자동화 대상 시그널 id 2개만 DB 계산값으로 **덮어쓴다**. 상수 자체는 수정하지 않음 (수동 폴백값 겸용).
- 계산: 해당 티커의 최근 20영업일 `foreign_net` 합계 (단위: 조원 환산)
- 판정 임계값 (모듈 상단 상수, 운영하며 조정):
  ```python
  FOREIGN_FLOW_RED_KRW = -3.0     # 4주 누적 ≤ -3조원 → red "경보"
  FOREIGN_FLOW_YELLOW_KRW = 0.0   # < 0원 → yellow "순매도 진행"
                                  # ≥ 0원 → green "아직 아님"
  ```
- note 자동 생성: `"최근 4주 누적 {±N.N}조원 순매수/순매도 (자동)"` — 수동 note와 구분되도록 "(자동)" 접미사
- **폴백**: 다음 중 하나면 해당 시그널은 수동 상수값 유지 + `logger.warning` 1건 (경보 아님):
  - 해당 티커 행이 없음
  - 20영업일 창에 행이 20개 미만 (백필 미완/수집 공백)
  - 최신 행의 date가 오늘로부터 `FLOW_STALE_CALENDAR_DAYS = 7` 달력일 초과 (수집 중단 의심)

### 3.5 검증

| # | 기준 | 방법 |
|---|---|---|
| T1-1 | 종목별 파서 | 네이버 응답 fixture → 파싱 결과 (pytest) |
| T1-2 | 누적·임계 판정 | fixture 20행 → red/yellow/green 경계값 3케이스 (pytest) |
| T1-3 | 오버레이·폴백 | DB 있음 → 덮어씀 / 행 부족·stale → 수동값 유지 (pytest) |
| T1-4 | 회귀 | `/api/research-analysis` 기존 카테고리 8개 구조 무변경, 기존 테스트 전체 통과 |
| T1-5 | 멱등 | 수집 2회 실행 후 행 수 불변 |

## 4. 트랙 2 — 주식심리 카테고리 신설

### 4.1 구성

- `analyze_all`의 9번째 카테고리: `key="stock_sentiment"`, `name="주식심리"`
- 입력 (기존 테이블 읽기만, 수집 없음):
  - `stock_fear_greed` 최신 행 (value 0~100, rating)
  - `cboe_putcall` 최신 행 (equity_pc, NULL이면 total_pc로 대체)

### 4.2 스코어 공식 (모듈 상단 상수)

```python
STOCK_SENTIMENT_WEIGHTS = (0.5, 0.5)   # (F&G, Put/Call)
PUTCALL_BAND = (1.0, 0.5)              # P/C 1.0 이상 → 0점, 0.5 이하 → 100점 선형
```

- `FG_score` = stock_fear_greed value 그대로 (탐욕 100 = 위험 100)
- `PC_score` = `clamp((1.0 − equity_pc) / 0.5 × 100, 0, 100)`
- `score` = `round(0.5 × FG_score + 0.5 × PC_score)` → 기존 `_score_to_level` 재사용 (≥75 critical, ≥55 warning, ≤25 bullish …)
- 예시: F&G=75, equity P/C=0.60 → PC_score=80 → score=78 → "critical"
- **두 입력 중 하나라도 최신 행이 없으면** 부분 계산 없이 기존 `_error_category` 패턴 반환
- 데이터 신선도: 입력 테이블의 stale 판정은 이미 수집 job·API 계층에 있으므로 analyzer는 추가 판정하지 않음 (단, details에 각 입력의 date/updated_at 표기)

### 4.3 details 구성 (카드 펼침 시)

- 주식 F&G: 현재값·rating·기준 시각
- Equity P/C: 현재값·과열(<0.7)/공포(>1.0) 라벨·거래일
- Total P/C: 참고 표기
- summary 문구: 스코어 구간별 고정 템플릿 (기존 카테고리들과 동일 방식)

### 4.4 프론트엔드 (소폭)

[Research.tsx](../../dashboard/frontend/src/components/screens/Research.tsx) 기준:
- `CATEGORIES` 배열에 `'주식심리'` 칩 추가, `CATEGORY_COLORS`에 색 1개 추가
- `AnalysisCard`의 key별 상세 렌더러에 `stock_sentiment` 케이스 추가 (F&G·P/C 값 나열 — 기존 단순 렌더러 패턴 복제)
- 그 외 구조 변경 없음

### 4.5 검증

| # | 기준 | 방법 |
|---|---|---|
| T2-1 | 스코어 공식 | 경계 케이스 (P/C 1.0→0점, 0.5→100점, 0.75→50점) + 예시 케이스 78점 (pytest) |
| T2-2 | equity NULL → total 대체 | fixture (pytest) |
| T2-3 | 입력 부재 → _error_category | 빈 DB fixture (pytest) |
| T2-4 | API 통합 | `/api/research-analysis` 응답에 9번째 카테고리 존재 + 기존 8개 무변경 (pytest) |
| T2-5 | 프론트 | `npm test` + `npm run build` 통과, 리서치 화면 칩·카드 렌더 확인 |

## 5. 구현 단계

| 단계 | 내용 | 검증 |
|---|---|---|
| 1 | 스키마 `kr_stock_investor_flow` 추가 | 테이블 생성 확인, 기존 테스트 통과 |
| 2 | 트랙 2 (독립적·작음): analyzer 카테고리 + 프론트 칩·렌더러 | T2-1~5 |
| 3 | 트랙 1 수집: 종목별 파서 + job 합류 + 백필 | T1-1, T1-5 |
| 4 | 트랙 1 판정: 오버레이 + 폴백 | T1-2, T1-3 |
| 5 | 회귀 전체 | T1-4 |

트랙 2를 먼저 하는 이유: 수집이 필요 없어 완전 독립적이고, 이미 쌓이는 데이터를 바로 소비한다.

## 6. 검증 갭 (로컬에서 확인 불가, 명시)

- 트랙 1의 실제 네이버 종목별 응답 포맷 — fixture는 구현 시점의 실응답으로 작성하되, 이후 구조 변경 위험은 기존 수집기와 동일 (파싱 실패 시 job 경보 경로)
- 4주 누적 임계값(-3조원)의 타당성 — 30영업일 실데이터 축적 후 실제 판정 분포를 보고 조정 (계획서의 초기값은 2026-06 삼성 -20.6조/하이닉스 -15.9조 사례가 red에 확실히 걸리도록 보수적으로 설정)
- 주식심리 스코어의 유용성 — 현재값 판정이므로 즉시 동작하지만, 가중치(0.5/0.5) 적정성은 운영하며 판단

## 7. Non-Goals

- 수급·거래대금 추세 분석 (4주 적재 후 별도 — [stock-backlog-followups-2026-07-05.md](stock-backlog-followups-2026-07-05.md) 4번과 통합 검토)
- 나머지 수동 시그널 7개의 자동화 (무료 소스 없음)
- 반도체 대상 종목 확대 (2개 고정), 알림 발송, 기존 카테고리 로직 변경
- Put/Call·F&G의 히스토리 차트 (리서치는 판정 카드만 — 차트는 볼륨트래커 미국 탭에 이미 있음)
