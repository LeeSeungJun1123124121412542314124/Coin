# 리서치 카드 "어제 · 7일 전 대비" 표시 — 스펙과 구현 계획 (2026-11-24)

- 요청: "리서치 다른 항목들도 변화가 어떻게 되고 있는지에 대한 설명이 부족한거 같은데"
- 사용자 선택: 변화 표시 = **공통 방식**, 비교 기준 = **어제 + 7일 전**
- Seed: `seed_04b15d01e149`

## 1. 배경

리서치 항목(매크로·온체인·파생상품·알트코인·기술적분석·시장분석·주식심리·주식수급 — 작성 당시 10개, 아래 6절에서 8개로 줄임)은
요청할 때마다 현재 값만 계산해 내려주고, 분석 결과를 어디에도 저장하지 않는다.
그래서 카드에는 "지금 값"만 있고 어제와 무엇이 달라졌는지 알 수 없다.

## 2. 하는 일

1. 분석 결과를 날짜별로 저장한다 (항목마다 하루 1행, 날짜는 한국 시간).
2. 응답의 각 항목에 이전 저장분을 붙인다 (`compare.prev`, `compare.week`).
3. 카드에 같은 형식으로 보여준다.

```
온체인  중립
온체인 중립 42/100
어제 38 → 오늘 42 (▲4) · 등급 그대로
7일 전 35 (▲7)

오늘: 유입/유출 비율 1.07 | 유입 14,442 BTC
어제: 유입/유출 비율 0.98 | 유입 12,310 BTC
```

## 3. 규칙

### 저장
- 테이블 `research_snapshot(date, key, level, score, title, summary, updated_at)`, 기본키 `(date, key)`.
- `date`는 KST 날짜. 같은 날 다시 저장하면 덮어쓴다 → 그날 행은 그날의 마지막 값.
- 오류·적재 중 상태(`_error_category`가 만든 결과)는 저장하지 않는다. 구분은 결과의 `placeholder: true` 표시로 한다.
- 저장 작업 `snapshot_research`는 스케줄러가 매시 20분에 실행한다. 실패해도 화면 응답과는 무관하다.

### 비교값
- `compare.prev`: 오늘(KST) 이전의 가장 최근 저장분 — `date, days_ago, score, level, summary`
- `compare.week`: 7일 전 이전의 가장 최근 저장분, 단 14일보다 오래된 것은 쓰지 않는다 — `date, days_ago, score, level`
- 해당 저장분이 없으면 `null`. 비교값 조회가 실패하면 `compare` 없이 기존 응답을 그대로 반환한다.
- 과거 값은 소급해 만들 수 없다. 저장을 시작한 다음 날부터 "어제", 7일 뒤부터 "7일 전"이 보인다.

### 표시
- 이전 저장분이 있으면 제목 아래에 `어제 38 → 오늘 42 (▲4) · 등급 그대로`.
  등급이 바뀌었으면 `· 등급 중립 → 경계`. `days_ago`가 1이 아니면 "어제" 대신 "N일 전".
- `compare.week`가 있으면 바로 아래에 `7일 전 35 (▲7)` (실제 `days_ago` 사용).
- 점수 변화는 `▲n` / `▼n` / `–`(변화 없음). 색으로 좋고 나쁨을 표시하지 않는다 — 점수는 위험도라 항목마다 의미가 다르다.
- 이전 저장분이 있으면 요약을 `오늘: …` / `어제: …` 두 줄로, 없으면 지금처럼 한 줄로.
- 점수 계산·등급 판정·기존 요약 문구는 바꾸지 않는다.

## 4. 바꾸는 파일

| 파일 | 내용 |
|---|---|
| `dashboard/backend/db/schema.sql` | `research_snapshot` 테이블 |
| `dashboard/backend/services/research_history.py` (신규) | `kst_today`, `save_snapshot`, `load_comparisons`, `attach_comparisons` |
| `dashboard/backend/services/research_analyzer.py` | `_error_category`에 `placeholder: true` |
| `dashboard/backend/jobs/snapshot_research.py` (신규) | 분석 후 저장하는 job |
| `dashboard/backend/main.py` | 스케줄러 등록 (매시 20분) |
| `dashboard/backend/api/research_routes.py` | 응답에 비교값 붙이기 (실패 시 그대로) |
| `dashboard/frontend/src/components/screens/researchView.ts` | `toCompareLines` 순수 함수 |
| `dashboard/frontend/src/components/screens/Research.tsx` | 카드에 줄 표시 |
| `dashboard/tests/test_research_history.py` (신규), `dashboard/frontend/tests/researchView.test.ts` | 테스트 |

## 5. 검증

| 기준 | 방법 |
|---|---|
| 하루 1행 저장, 같은 날 덮어쓰기 | pytest — 같은 날 두 번 저장 후 행 수와 값 |
| 오류 상태는 저장 안 함 | pytest — `_error_category` 결과가 섞여도 빠지는지 |
| prev·week 경계 | pytest — 1일 전·6일 전·7일 전·14일 전·15일 전 저장분으로 선택 확인 |
| 조회 실패 시 기존 응답 유지 | pytest — 비교 함수가 예외를 내도 라우트가 200과 원래 항목을 반환 |
| 카드 문구 | node 테스트 — 등급 유지/변경, 어제/N일 전, ▲/▼/– |
| 기존 동작 유지 | 전체 pytest, `npm test`, `npm run build` |
| 화면 | 로컬에서 이전 날짜 행을 넣고 PC·모바일(390px) 폭 확인 |

## 6. 같은 날 추가 변경 — 카드 2개 제거와 기준일 표시

사용자 요청("2, 3번 빼, 그리고 늦게 나오는 데이터는 기준 붙혀주고")으로 다음을 함께 바꿨다.

### 카드 제거 (10개 → 8개)
- **기타(고래)**: 추적 지갑 10개(환경변수 고정)가 거의 비어 "롱 0 · 숏 0 · 중립 10"만 나왔다. 리서치 카드만 빼고, 별도 메뉴인 고래추적 화면과 `whale_snapshots` 수집은 그대로 둔다.
- **반도체 정점**: 시그널 9개 중 7개가 2026-07-04에 손으로 넣은 값이라 143일째 갱신되지 않았다. 카드와 함께 이 카드만을 위한 코드도 걷어냈다 —
  갱신 필요 알림(`direction_watch`의 stale 알림), 종목별 수급 수집(`collect_kr_stock`의 삼성전자·SK하이닉스 수집, `naver_finance.fetch_stock_investor_trend`), `kr_stock_investor_flow` 테이블 정의.
  운영 DB에 이미 있는 `kr_stock_investor_flow` 테이블과 데이터는 지우지 않았다(더 이상 쓰이지 않을 뿐).
- 이미 저장된 `research_snapshot`의 `whale`·`semiconductor_signals` 행은 남아 있어도 화면에 나오지 않는다.

### 기준일 표시
원본이 늦게 나오는 값은 며칠째 같아 보여 "수집이 멈춘 것"으로 읽혔다. 요약에 언제 값인지 붙인다.

| 카드 | 표시 | 이유 |
|---|---|---|
| 온체인 | `11-22 기준 · 유입/유출 비율 …` | Coin Metrics 무료 API가 하루치 값을 이틀쯤 늦게 준다 |
| 주식심리 | `F&G 17.0 (11-23) \| Put/Call 0.77 (11-20)` | 풋콜 비율은 1영업일 늦게 나온다 |
| 매크로 | `TGA … (11-18 기준 · YoY …)`, `M2 YoY … (9월 기준 · …)` | TGA는 주간, M2는 월간 발표 |

주식수급은 이미 요약 앞에 날짜가 있다. 나머지(파생상품·알트코인·기술적분석·시장분석)는 실시간이라 붙이지 않는다.

### 온체인 "유입 0 BTC | 유출 0 BTC" 수정
기준일을 붙인 직후 운영 스냅샷에 `11-23 기준 · 유입 0 BTC | 유출 0 BTC`가 찍혀 드러났다.
Coin Metrics는 새 날짜 행을 먼저 만들고(활성 주소 수만 채움) 거래소 유출입 값은 나중에 채운다.
수집기(`crypto-volatility-bot/app/data/data_collector.py`의 `fetch_onchain_data`)가 값이 빈 최신 행을 그대로 써서
그 시간대에는 유입·유출이 0으로 나갔다. 유출입 값이 있는 가장 최근 날을 쓰도록 고쳤고, 그런 날이 하나도 없으면 0 대신 "데이터 없음"을 돌려준다.
