# 학습 탭 보조 지표 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 학습 차트에 이동평균·볼린저·거래량·RSI·MACD를 서버 저장 설정으로 켜고 끌 수 있게 한다.

**Architecture:** 설정은 `learning_settings`의 새 `indicators` 키(기존 깊은 병합·검증 구조), 계산은 `learning_indicators.py` 순수 함수, 차트 API가 켜진 지표만 `indicators` 필드로 돌려준다. 프론트는 lightweight-charts 5의 pane으로 아래 칸을 쌓는다.

**Spec:** `docs/plans/learning-indicators-spec-2026-11-19.md`

## Global Constraints
- 설정 기본값(정확히): `indicators = { ma: {enabled: false, type: "sma", periods: [5, 20, 60, 120]}, bb: {enabled: false, period: 20, stddev: 2.0}, volume: {enabled: false}, rsi: {enabled: false, period: 14}, macd: {enabled: false, fast: 12, slow: 26, signal: 9} }`
- 범위: ma.type ∈ {"sma","ema"}, ma.periods 1~6개 각 2~400 정수, bb.period 5~200 정수, bb.stddev 0.5~4, rsi.period 2~100 정수, macd.fast 2~200·slow 3~400·signal 2~100 정수이고 fast < slow, 모든 enabled는 bool. 위반은 `LearningError`(HTTP 400), 메시지 형식은 기존 `wyckoff.n` 류와 같게
- 워밍업 봉 = max(52, max(ma.periods), bb.period, rsi.period × 3, (macd.slow + macd.signal) × 3), 상한 1500. 켜진 지표만 워밍업 계산에 넣는다
- 색은 스펙 3절 표 그대로(`C.*`/`softBg`, 캔버스에는 hex·rgba만)
- 새 패키지·스키마 변경·백엔드의 다른 화면 변경 금지. 주석·커밋 한국어 `type: 한국어 설명`, master 로컬 커밋만

## Review Focus
1. 예전에 저장된 설정 행(indicators 없음)에서 GET·PUT이 400 없이 기본값으로 동작해야 한다 → Task 1 테스트
2. 봉 수가 기간보다 적으면(신규 상장, 월봉) 계산이 예외 없이 빈 결과 → Task 1 테스트
3. MACD fast ≥ slow, periods 빈 목록·7개·소수·bool 거부 → Task 1 테스트
4. 칩 토글 저장 실패 시 화면이 원래 상태로 돌아가야 한다 → Task 2
5. 아래 칸을 껐다 켤 때 pane·시리즈가 새지 않아야 한다(시리즈 제거 후 빈 pane 정리) → Task 2

---

### Task 1: 서버 — 설정·계산·차트 응답

**Files:** Modify `dashboard/backend/services/learning_settings.py`, `dashboard/backend/services/learning_indicators.py`, `dashboard/backend/api/learning_routes.py`(get_chart만). Test `dashboard/tests/test_learning_indicators_extra.py`(새 파일), 기존 `test_learning_chart_api.py`에 차트 응답 테스트 추가

**Interfaces (Produces):**
- `learning_indicators.sma(values: list[float], n: int) -> list[float | None]`, `ema(values, n) -> list[float | None]`(첫 값 = 첫 n개 SMA), `bollinger(values, n, k) -> list[dict | None]`(`{upper, mid, lower}`, 모표준편차), `rsi(values, n) -> list[float | None]`(와일더), `macd(values, fast, slow, signal) -> list[dict | None]`(`{macd, signal, hist}`) — 입력과 같은 길이, 정의 안 되는 앞부분 None
- `learning_indicators.indicator_warmup(cfg: dict) -> int` — Global Constraints 공식, 켜진 지표만
- 차트 응답에 `indicators` 추가: `{ ma?: [{period, points: [{time, value}]}], bb?: [{time, upper, mid, lower}], rsi?: [{time, value}], macd?: [{time, macd, signal, hist}] }` — 켜진 것만 키가 있고 None 점은 뺀다, `time`은 캔들 `open_time`, 보이는 봉(`t0` 이후)만. 거래량은 캔들 volume을 쓰므로 응답에 넣지 않는다
- `get_chart`가 `_load_candles(symbol, interval, limit + max(_EXTRA_BARS, indicator_warmup(cfg)))`

- [ ] Step 1 실패하는 테스트: SMA [1..5] n=3 → [None, None, 2, 3, 4] / EMA n=3 첫 값 2, 다음 (4−2)×0.5+2=3 / 볼린저 [2,4,4,4,5,5,7,9] n=8 k=2 → mid 5, 표준편차 2, upper 9, lower 1 / RSI 단조 증가 → 100, 단조 감소 → 0, 정의 안 되는 앞 n개 None / MACD 길이 = 입력, 앞부분 None, hist = macd − signal / 봉 수 < 기간 → 전부 None / 설정: 기본값, 예전 저장 행에 기본값 채움, 범위 위반 400들(fast ≥ slow, periods 빈·7개·1.5·True, type "wma") / `indicator_warmup` 공식(기본 꺼짐 → 52, ma 120 켬 → 120, macd 켬 → (26+9)×3=105, 상한 1500) / 차트 API: 켜진 지표만 키, 꺼짐이면 `indicators == {}`, 보이는 첫 봉 시각 이후만
- [ ] Step 2 RED 확인 → Step 3 구현 → Step 4 `pytest dashboard/tests -q` 전부, `ruff check` 변경 파일
- [ ] Step 5 커밋 `feat: 학습 차트 보조 지표 설정과 계산 추가(이동평균·볼린저·RSI·MACD)`

### Task 2: 프론트 — 칩·설정 폼·겹침 선·아래 칸

**Files:** Modify `dashboard/frontend/src/lib/learningApi.ts`(타입), `src/components/learning/LearningChart.tsx`, 필요하면 `learningShared.ts`. 새 순수 모듈 `src/components/learning/indicatorPanes.ts` + 테스트 `tests/indicatorPanes.test.ts`

**Interfaces:**
- Consumes: Task 1 응답 `indicators`, 설정 `indicators`
- `LearningSettings.indicators` 타입과 `ChartResponse.indicators?` 타입
- `indicatorPanes.ts`: `paneLayout(enabled: {volume: boolean; rsi: boolean; macd: boolean}): { key: 'volume'|'rsi'|'macd'; index: number }[]` — 켜진 순서(거래량 → RSI → MACD)로 pane 번호 1, 2, 3…, `chartHeight(base: number, paneCount: number, paneHeight = 110): number`, `maColor(i: number): string`(스펙 색 순서, 7번째부터 반복)
- 칩: 기존 칩 뒤 `이동평균`·`볼린저`·`거래량`·`RSI`·`MACD`. 누르면 `putSettings({ indicators: { <key>: { enabled } } })`, 성공 시 차트 다시 불러오기, 실패 시 상태 되돌리고 기존 설정 오류 표시 방식으로 메시지
- 설정 폼: 기존 폼에 "보조 지표" 묶음 — 이동평균 종류(select SMA/EMA)·기간(쉼표 구분 문자열 → 정수 배열), 볼린저 기간·표준편차, RSI 기간, MACD 빠른·느린·시그널
- 그리기: 이동평균 LineSeries(기간별, `maColor`), 볼린저 LineSeries 3개(상·하단 `C.text2`, 중단 `C.text3` 점선), 거래량 HistogramSeries(pane, 캔들 방향 up/down 50% 투명), RSI LineSeries + 70·30 priceLine(pane), MACD LineSeries 2개 + HistogramSeries(pane, 양수 up·음수 down 50%). 지표를 끄면 시리즈를 제거하고 빈 pane은 지운다(`chart.removePane` 등 v5 API — typings에서 확인)
- 십자선 일반 모드(이미 적용)와 로그 토글은 본 칸에만 적용

- [ ] Step 1 실패하는 테스트 `tests/indicatorPanes.test.ts`: `paneLayout({volume:false, rsi:true, macd:true})` → `[{key:'rsi',index:1},{key:'macd',index:2}]`, 모두 꺼짐 → `[]` / `chartHeight(460, 2) === 680` / `maColor(0) === C.accent`, `maColor(6) === maColor(0)`. package.json test 스크립트에 추가
- [ ] Step 2 RED → Step 3 구현 → Step 4 `npm test`, `npm run build`, `npx eslint src/components/learning src/lib/learningApi.ts`
- [ ] Step 5 커밋 `feat: 학습 차트에 이동평균·볼린저·거래량·RSI·MACD 칩과 아래 칸 추가`
