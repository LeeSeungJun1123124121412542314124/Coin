# 계획: 고래추적 미국 탭 — 13F 기관 보유 (백로그 §1 나머지)

작성일: 2026-08-23 (v2 — claude-opus-5 검토 반영)
원안: [stock-backlog-followups-2026-07-05.md](stock-backlog-followups-2026-07-05.md) §1
선행 완료: Form 4 축소판 (`dc6a096`) — 본 계획은 같은 미국 탭에 **13F 기관 보유**를 추가한다.

## 확정 요구사항

- **방식**: 기관 화이트리스트 (사용자 확정 2026-08-23) — 유명 펀드의 분기 13F-HR을 수집해 관심종목(us 슬롯) 보유만 추출
- **제약 인지**: 분기·45일 지연 공시 → "분기 큰손 포지션"임을 UI에 명시
- **소스**: SEC EDGAR (무료, `_EDGAR_UA` 재사용)

## 설계 (검토 반영 결정사항)

### D1. issuer 매칭 — EDGAR 회사명 대조 (usTicker 필드는 존재하지 않음)

infoTable XML에는 티커 컬럼이 없다(`nameOfIssuer, titleOfClass, cusip, figi?, value, sshPrnamt, sshPrnamtType, putCall?, investmentDiscretion, otherManager, votingAuthority` 전부). 슬롯 name은 사용자 편집 가능(한글)해서 이름 직접 비교 불가.

→ **`edgar.py`에 `fetch_ticker_title_map()` 신규**: company_tickers.json의 `title`(EDGAR 공식 회사명) 반환 `{ticker_upper: title}`. 수집 job에서 us 슬롯 티커 목록의 공식명 집합을 만들고 infoTable의 `nameOfIssuer`와 **대소문자 무시 정확 일치** 매칭. 실패 행은 seq 유지 위해 파싱은 하되 필터에서 탈락(warning 로그).

### D2. value 단위 — 배율 곱하지 않음

SEC 사양: 2023-01-03 제출분부터 **달러 단위**, 이전은 천달러. 백필 창 4분기(≈1년)면 전부 달러 단위 → **환산 배율 없음**, 근거를 코드 주석으로 남긴다.

### D3. 수정본(13F-HR/A) 규칙 — (cik, quarter) 최신 접수만 유지

- form 필터: `form == "13F-HR" or form == "13F-HR/A"`
- RESTATED 수정본이 원본과 같은 분기에 공존하면 합산이 두 배가 됨
- 규칙: job이 filing 처리 시 **동일 (cik, quarter)의 기존 행을 DELETE 후 INSERT**(교체). 자연히 최신 접수만 남고 API는 단순 집계 가능

### D4. putCall — 저장하고 Put은 응답에서 제외

Citadel·RenTech은 옵션 비중이 크다. "AAPL 풋"을 "보유"로 표시하면 방향이 반대로 해석됨.
- 스키마에 `put_call TEXT` 컬럼 (None=주식, 'Call'/'Put')
- API 기본 응답은 `put_call IS NULL OR put_call != 'Put'` — 풋은 수집·보존만

### D5. 백필 창 4분기 — submissions recent 커버리지 내

`filings.recent`는 최근 ~1년/1000건 한정(Citadel급 다작 신고자는 초과 위험). `filings.files` 페이징은 Non-Goal. → `since = 오늘 - 400일`, 부족분은 다음 분기까지 대기.

### D6. 처리 완료 tracking 테이블 — 0매칭 filing 재수집 방지

보유 매칭 0건인 13F도 수십 MB XML이므로 매주 재다운로드 금지.
신규 테이블 `us_13f_filings`(메타): `(accession_no PK, cik, institution, filed_at, report_date, processed_at)`. known 체크는 이 테이블 기준.
infotable 다운로드 timeout은 15s → **60s** 상향(수천~만 행 대응).

### D7. 기타 확정

- quarter 출처: submissions API의 **`reportDate`** 필드 (primary_doc의 periodOfReport 아님)
- infotable 문서 식별: filing `index.json`에서 `type == "INFORMATION TABLE"` 우선, 없으면 파일명 `infotable` 휴리스틱 폴백
- CIK 오입력 방지: submissions 응답의 `name`이 기관명과 무관하면 warning 스킵 (404 스킵과 별개)
- 스케줄: **월요일 09:20 UTC** (Form 4 job 09:00와 분리 — 동시 실행 시 SEC 10req/s 초과)
- seq = **원본 XML 행 인덱스**(필터 전) — 슬롯 변경과 무관하게 안정
- API 응답 키는 기존과 동일하게 `summaries`

## 스키마 (`schema.sql` 추가)

```sql
-- 미국 기관 보유 (SEC EDGAR 13F-HR, 화이트리스트 기관 × us 슬롯 종목)
CREATE TABLE IF NOT EXISTS us_13f_holdings (
    accession_no  TEXT NOT NULL,
    seq           INTEGER NOT NULL,   -- 원본 infoTable 행 인덱스
    institution   TEXT NOT NULL,
    cik           INTEGER NOT NULL,
    ticker        TEXT NOT NULL,
    issuer_name   TEXT NOT NULL,
    quarter       TEXT NOT NULL,      -- reportDate 'YYYY-MM-DD'
    shares        REAL,
    value_usd     REAL,               -- 2023-01-03+ 접수분 = 달러 단위 (배율 없음)
    put_call      TEXT CHECK(put_call IN ('Call','Put')),
    PRIMARY KEY (accession_no, seq)
);
CREATE INDEX IF NOT EXISTS idx_us_13f_ticker_q ON us_13f_holdings(ticker, quarter);

-- 13F 접수 처리 이력 (0매칙 filing 재수집 방지)
CREATE TABLE IF NOT EXISTS us_13f_filings (
    accession_no  TEXT PRIMARY KEY,
    cik           INTEGER NOT NULL,
    institution   TEXT NOT NULL,
    filed_at      TEXT NOT NULL,
    report_date   TEXT NOT NULL,
    processed_at  TEXT NOT NULL
);
```
(_init_schema가 executescript로 자동 반영 — 별도 ALTER 불필요)

## Tasks (TDD — 각 Task: 실패테스트 → 구현 → 통과 → 커밋)

### Task 1 — edgar.py 13F collector 함수 + 파서
- Modify: `dashboard/backend/collectors/edgar.py` / Test: `dashboard/tests/test_edgar_13f.py` (신규)
- `parse_submissions_13f(payload, since)` → `{accession_no, filed_at, primary_document, report_date}` 목록 (form 13F-HR/-HR/A, reportDate 포함)
- `parse_filing_index(payload)` → information table 문서명 (type 우선, 휴리스틱 폴백)
- `parse_infotable_xml(xml)` → `{issuer_name, cusip, shares, value_usd, put_call}` 행 목록 (배율 없음)
- `fetch_filing_index(cik, acc)`, `fetch_infotable(cik, acc, doc)` — timeout 60s
- fixture: 최소 infoTable XML 3행(주식/콜/풋)을 테스트에 인라인 정의
- AC: 풋 행 put_call='Put', value 배율 미적용, 빈 문서 → ValueError

### Task 2 — schema + upsert/교체 로직
- Modify: `schema.sql`, `dashboard/backend/jobs/collect_us_13f.py`(신규) / Test: `dashboard/tests/test_collect_us_13f.py`(신규)
- 테이블 2종 DDL, `upsert_13f_filing`(메타 기록) / `replace_13f_holdings`(동일 cik+quarter DELETE→INSERT) / `known_13f_accessions()`
- AC: 같은 (cik, quarter) 재처리 시 이전 행 소멸, 메타 중복 무시

### Task 3 — 수집 job + 스케줄
- Modify: `collect_us_13f.py`, `main.py(_register_jobs)` / Test: `test_collect_us_13f.py`
- 흐름: 화이트리스트 순회 → known 스킵 → submissions(reportDate>=since) → 기관명 대조(EDGAR name 무관하면 스킵) → index→infotable→파싱→ticker/title 매칭 필터 → replace 저장 → 메타 기록
- `@async_retry(max_retries=3, on_failure=notify_job_failure)`, delay 0.15s, since=오늘-400일
- 화이트리스트: `_INSTITUTIONS = [("Berkshire Hathaway", 1067983), ...]` — **구현 첫 단계에서 4개 CIK를 company_tickers.json/browse-edgar로 검증하고 결과를 코드 주석+계획서에 기록**
- CIK 검증(2026-08-23, SEC submissions API `name`): Berkshire Hathaway `1067983` → `BERKSHIRE HATHAWAY INC`, Bridgewater Associates `1350694` → `Bridgewater Associates, LP`, Citadel Advisors `1423053` → `CITADEL ADVISORS LLC`, Renaissance Technologies `1037389` → `RENAISSANCE TECHNOLOGIES LLC`
- 스케줄: 월요일 09:20 UTC, id=`collect_us_13f`
- AC: mock httpx로 end-to-end 1회 수집, 2회차 전량 스킵

### Task 4 — API 엔드포인트
- Modify: `whale_routes.py` / Test: `dashboard/tests/test_whale_13f.py`(신규)
- `GET /whale/us-13f-holdings`: 최근 4분기, Put 제외, us 슬롯 한정
- 응답: `{quarters, holdings, summaries}` — summaries: `{ticker, latest_quarter, latest_value, prev_value, qoq_change}` (키명 기존 us-insider와 일관)
- 창 결합 주석(수집 400일 vs 표시 4분기) — `_US_INSIDER_WINDOW_DAYS` 스타일
- AC: fixture DB로 응답 스키마·Put 제외·분기 선정 검증

### Task 5 — 프론트 섹션
- Modify: `Whale.tsx` (+필요 시 tests/)
- UsInsiderView 아래 "기관 보유 (13F)" 섹션: 헤더에 "분기 · 45일 지연" 명시, summaries 카드 + holdings 테이블, 빈 상태는 기존 패턴 재사용(`Whale.tsx:354`)
- AC: `npm run build` 통과, `npm test` 통과

## AC (전체)

1. 각 Task 단위테스트 통과 + 전체 `pytest dashboard/tests crypto-volatility-bot/tests` 통과
2. **단위**: value 배율 미적용(달러 그대로)
3. **중복 방지**: 동일 (cik, quarter) 원본+수정본 → 최신 접수만 잔존
4. **putCall**: Put 행이 API 응답에 없음
5. **재수집 방지**: 0매칭 filing도 메타 기록 후 재처리 안 함
6. ruff clean(변경 파일) + frontend build/test 통과

## Non-Goals

- filings.files 페이징(1년 초과 백필), cusip→ticker 정규 테이블, 차트 시각화, 풋 데이터 활용 UI, 전수 스캔

## 제약

한국어 주석 · TDD · 외과적 변경 · 새 의존성 금지(httpx/xml.etree) · Form 4 패턴 준수 · 커밋 단위=Task
