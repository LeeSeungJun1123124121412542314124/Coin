# 주식 확장 2차 구현 계획 — Form 4 내부자 매매 · 리서치 주식수급 · 심리지수 설명

- 작성일: 2026-07-12
- 근거: [stock-backlog-followups-2026-07-05.md](stock-backlog-followups-2026-07-05.md) §1(축소판)·§4 + 사용자 인터뷰 (2026-07-12)
- 스펙 경로 비고: ouroboros MCP가 초기화 타임아웃으로 불능이어서 직접 인터뷰(질문 4건 확정) 후 본 계획으로 대체

## 0. 인터뷰 확정 사항

| 질문 | 확정 답 |
|---|---|
| Form 4 추적 대상 | 미국 관심종목 슬롯(us, 5개) 연동 — 슬롯 변경 시 추적 대상도 따라감 |
| 미국 탭 표시 내용 | 종목별 최근 90일 내부자 순매수 합산 요약 + 개별 거래 목록 |
| 리서치 '주식수급' 범위 | 한국 수급·거래대금만 (`kr_investor_flow` + `kr_market_volume`) — 지수그림자·Form 4 미반영 |
| 심리지수 설명 방식 | 주식심리 카드 펼침(상세) 영역에 지수별 한 줄 고정 설명 |

## 1. 공통 제약 (기존 계획 문서에서 확립)

- 유료 API 금지, 새 패키지 설치 금지 (EDGAR는 무료·User-Agent만 요구)
- 기존 카테고리 응답 구조 무변경 (프론트 key별 렌더러 회귀 금지)
- 수집 job: `@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)` 패턴
- analyzer 내부 경보 호출 금지 — 폴백만
- SPF·리더보드·알림 파이프라인 미변경

## 2. 트랙 A — 주식심리 카드 지수 설명 (최소)

- [researchView.ts](../../dashboard/frontend/src/components/screens/researchView.ts)에 상수 `STOCK_SENTIMENT_INDEX_NOTES: Array<[string, string]>` 추가:
  - 공포탐욕지수(F&G): CNN 산출 0~100 투자심리. 0 극단 공포 ~ 100 극단 탐욕, 높을수록 과열(고점 경계)
  - Put/Call 비율: CBOE 풋/콜 옵션 거래량 비율. 1.0 초과 = 하락 베팅 우세(공포), 0.7 미만 = 낙관 과열
- [Research.tsx](../../dashboard/frontend/src/components/screens/Research.tsx) `_renderDetails`의 `stock_sentiment` 케이스: 기존 값 그리드 아래에 설명 블록 렌더
- **검증**: 프론트 테스트·빌드 통과, 주식심리 카드 펼침 시 설명 표시

## 3. 트랙 B — 리서치 '주식수급' 카테고리 (10번째)

### 입력·판정
- 입력: `kr_investor_flow`(KOSPI, 최근 20영업일), `kr_market_volume`(최근 20영업일). 수집 job이 매 실행 30영업일 백필하므로 즉시 표본 충족 — 단 폴백은 필수 유지.
- 스코어 (모듈 상단 상수, 0~100 위험도):
  ```python
  KR_FLOW_BAND = (50_000.0, -50_000.0)   # 외국인+기관 20일 누적(억원): +5조 → 0점, -5조 → 100점 선형
  KR_VOLUME_BAND = (0.7, 1.5)            # 최근5일/20일 거래대금 비율: 0.7 → 0점, 1.5 → 100점 선형
  KR_STOCK_FLOW_WEIGHTS = (0.7, 0.3)     # (수급, 거래대금)
  ```
  - flow_score: KOSPI `foreign_net + institution_net` 20영업일 합계를 밴드 선형 매핑 (순매도 클수록 위험↑)
  - volume_score: (KOSPI+KOSDAQ 합산 최근 5영업일 평균) / (20영업일 평균) 비율을 밴드 선형 매핑 (거래대금 급증 = 과열·분배 의심)
  - score = 0.7×flow + 0.3×volume → 기존 `_score_to_level` 재사용
- **폴백**: 어느 입력이든 20영업일 미만이면 `_error_category` 패턴에 `summary="데이터 적재 중 (N/20영업일)"` — 적재가 차면 자동으로 살아남
- `analyze_all`에 `key="kr_stock_flow"`, `name="주식수급"` 10번째로 추가. details: 외국인/기관 각 20일 누적, 거래대금 비율, 기준일 구간

### 프론트
- researchView: `RESEARCH_CATEGORIES`·`RESEARCH_CATEGORY_COLORS`에 '주식수급' 추가
- Research.tsx `_renderDetails`에 `kr_stock_flow` 케이스 (라벨-값 그리드, stock_sentiment 패턴 복제)

### 검증
| # | 기준 | 방법 |
|---|---|---|
| B-1 | 스코어 경계 | +5조→0, -5조→100, 0→50 / 비율 0.7→0, 1.5→100 (pytest) |
| B-2 | 폴백 | 20영업일 미만 fixture → "데이터 적재 중" (pytest) |
| B-3 | 회귀 | `/api/research-analysis` 기존 9개 카테고리 구조 무변경 + 10번째 존재 (pytest) |

## 4. 트랙 C — EDGAR Form 4 내부자 매매 (고래추적 미국 탭)

### 수집기 `collectors/edgar.py`
- User-Agent 상수 (SEC 요구: 식별 가능한 UA): `coin-dashboard yadunghouse@gmail.com`
- ticker→CIK: `https://www.sec.gov/files/company_tickers.json` (실행당 1회, 메모리 캐시)
- 종목별 공시 목록: `https://data.sec.gov/submissions/CIK{cik:010d}.json` → `form == "4"` 필터, 최근 90일(`_LOOKBACK_DAYS = 90`)
- Form 4 원문 XML: `https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{primaryDocument}` — `primaryDocument`의 `xslF345X*/` 프리픽스는 제거해 raw XML 접근
- 파싱(stdlib `xml.etree`): 보고자 이름·직함, `nonDerivativeTransaction`의 거래일·코드·수량·단가. **코드 P(장내매수)·S(장내매도)만 저장** — 수여(A)·세금(F) 등 잡음 제외
- rate limit: 요청 간 0.15s sleep (SEC 10 req/s 제한)

### 테이블 (신규 1개)
```sql
CREATE TABLE IF NOT EXISTS us_insider_trades (
    accession_no     TEXT NOT NULL,   -- SEC 공시 접수번호
    seq              INTEGER NOT NULL,-- 공시 내 거래 순번
    ticker           TEXT NOT NULL,
    filed_at         TEXT NOT NULL,   -- 공시 접수일
    transaction_date TEXT NOT NULL,
    insider_name     TEXT NOT NULL,
    insider_title    TEXT,
    code             TEXT NOT NULL CHECK(code IN ('P','S')),
    shares           REAL,
    price            REAL,
    value            REAL,            -- shares × price (달러, 매도는 음수)
    PRIMARY KEY (accession_no, seq)
);
```

### job `jobs/collect_us_insider.py`
- `collect_us_insider_trades`: 평일 09:00 UTC (미국 공시일 마감 후, KST 18:00) — main.py `_register_jobs` 등록
- 매 실행: `stock_slots(market='us')` 티커 조회 → 각 티커의 90일 내 Form 4 중 DB에 없는 accession만 수집 (첫 실행 = 90일 백필 겸용)
- 이미 저장된 accession은 스킵 (멱등)
- 슬롯에 없는 티커의 기존 행은 삭제하지 않음 (이력 보존, 조회 시 슬롯 기준 필터)

### API — [whale_routes.py](../../dashboard/backend/api/whale_routes.py)
- `GET /whale/us-insider-trades`: 현재 us 슬롯 티커 기준
  ```json
  {
    "summaries": [{"ticker", "name", "buy_value", "sell_value", "net_value", "trade_count"}],
    "trades": [{"ticker", "transaction_date", "filed_at", "insider_name", "insider_title", "code", "shares", "price", "value"}]
  }
  ```
  - summaries: 슬롯 순서, 최근 90일 합산. trades: 거래일 역순 최대 50건

### 프론트 — [Whale.tsx](../../dashboard/frontend/src/components/screens/Whale.tsx)
- `allowedTabs`를 `['coin', 'kr', 'us']`로 확장 (`AssetTab 'us'` 라벨 "미국/환율"은 공용이므로 유지)
- us 뷰: 종목별 순매수 요약 칩(FlowChip 패턴, 순매수 녹색/순매도 적색) + 거래 목록 테이블(날짜·종목·임원(직함)·매수/매도·수량·단가·금액). 데이터 없으면 "내부자 거래 없음(최근 90일)" 안내

### 검증
| # | 기준 | 방법 |
|---|---|---|
| C-1 | Form 4 XML 파서 | 실응답 기반 fixture → 보고자·거래 추출, P/S 외 코드 제외 (pytest) |
| C-2 | primaryDocument 경로 정규화 | `xslF345X05/...xml` → raw 경로 (pytest) |
| C-3 | 멱등 | 동일 accession 2회 수집 → 행 수 불변 (pytest) |
| C-4 | API 형태 | 시드 DB → summaries 합산·부호, trades 정렬·limit (pytest) |
| C-5 | 프론트 | 테스트·빌드 통과, us 탭 렌더 |

## 5. 구현 순서

1. 트랙 A (설명 텍스트 — 완전 독립, 최소)
2. 트랙 B (analyzer 카테고리 + 프론트 칩·렌더러)
3. 트랙 C 수집 (파서 → 테이블 → job) → API → 프론트 탭
4. 전체 회귀 (pytest + 프론트 테스트·빌드)

## 6. Non-Goals

- 13F 기관 보유 (백로그 §1 원안 — 수요 확인 후 별도)
- KRX 프로그램매매, CVD 주식판 (백로그 §2·§3 — 착수 조건 미충족)
- 지수그림자·Form 4의 리서치 판정 반영, 리더보드/SPF 연동
- Form 4 파생상품 거래(derivativeTransaction) — 장내 P/S만
- 알림 발송 추가 (수집 실패 경보는 기존 job 패턴으로 자동 커버)

## 7. 검증 갭 (로컬에서 확인 불가, 명시)

- EDGAR 실응답 포맷 — fixture는 구현 시점 실응답으로 작성, 이후 구조 변경 시 job 경보 경로로 감지
- 주식수급 밴드(±5조원, 0.7~1.5)의 타당성 — 운영하며 판정 분포 보고 조정 (상수화)
- Railway 배포 후 첫 job 실행 확인 필요 (`us_insider_trades` 적재, 실패 시 텔레그램 경보)
