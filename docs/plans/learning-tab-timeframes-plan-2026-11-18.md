# 학습 탭 시간봉 확장 (1h·1w·1M) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 학습 탭 차트·수집·매매 근거를 1h·4h·1d·1w·1M 5개 시간봉으로 넓힌다.

**Architecture:** 캔들 테이블은 그대로 두고 interval 값만 늘린다. 마감 판정과 페이지 커서를 kline closeTime 기준으로 바꿔 길이가 다른 월봉도 정확히 다룬다. 1h는 별도 잡과 별도 소스명으로 수집해 알림 없이 기록만 한다.

**Tech Stack:** FastAPI, SQLite, APScheduler, httpx / React 19 + TypeScript, lightweight-charts 5, node 내장 test

**Spec:** `docs/plans/learning-tab-timeframes-spec-2026-11-18.md` (Seed `seed_e552b30de236`)

## Global Constraints
- 시간봉 값은 정확히 `"1h"`, `"4h"`, `"1d"`, `"1w"`, `"1M"` (바이낸스 kline interval 표기, 대소문자 그대로)
- 지그재그 기본값: `threshold_1h` 3.0, `threshold_4h` 5.0, `threshold_1d` 10.0, `threshold_1w` 20.0, `threshold_1M` 30.0, 각각 1~50
- 1h·1w·1M 모두 상장일(start_ms=0)부터 백필. 아직 마감 안 된 봉은 저장하지 않는다
- 1h 수집 잡: `CronTrigger(minute=5, timezone="UTC")`, id `learning_1h`, 소스명 `binance-spot-1h`, 실패는 `learning_collection_runs`에 기록만 하고 텔레그램 알림 없음
- 1w·1M은 일봉 수집 러너(소스명 `binance-spot`)에서 1d와 함께 수집, 실패 알림은 기존과 같음
- 복기 판정 가격·DCA·성과는 기존처럼 1d 종가만 쓴다
- 새 패키지 설치 금지, 스키마 변경 없음, 기존 다른 탭 동작 변경 없음, 비밀값 출력 금지
- 코드 주석·커밋 메시지는 한국어, 커밋 형식 `type: 한국어 설명`

## Review Focus
1. 진행 중인 이번 달 월봉(closeTime ≥ now)이 저장되면 안 된다 → Task 1 `test_monthly_open_bar_dropped_and_cursor_uses_close_time`
2. 1h 잡의 성공 기록이 같은 날 일봉 실패의 재시도를 가리면 안 된다 → Task 2 `test_1h_run_does_not_mask_daily_failure`
3. 백필 done 종목에 새 시간봉만 없을 때, 그 시간봉만 받고 전체 재백필(1h 8만 봉 포함)을 하지 않는다 → Task 2 `test_missing_interval_filled_without_full_backfill`
4. 예전에 저장된 설정(threshold_1d·4h만 있는 행)에서도 새 임계값 3개가 기본값으로 나온다 → Task 3 `test_stored_settings_get_new_threshold_defaults`
5. 상장이 짧아 월봉이 52개 미만인 종목도 차트가 200으로 오고 일목 상태는 판단 불가(null) → Task 3 `test_short_monthly_history_returns_200`

---

### Task 1: 수집기 closeTime 기준 전환 + 일목 미래 시각 달력 처리

**Files:**
- Modify: `dashboard/backend/collectors/binance_spot.py` (`INTERVAL_MS` 삭제, `fetch_klines`)
- Modify: `dashboard/backend/services/learning_indicators.py` (`INTERVALS`, `next_open_time`, `ichimoku` 인자)
- Modify: `dashboard/backend/api/learning_routes.py:118,147` (ichimoku 호출 2곳만)
- Modify: `dashboard/backend/jobs/learning_collect.py:124` (증분 시작점만)
- Test: `dashboard/tests/test_learning_binance.py`, `dashboard/tests/test_learning_ichimoku.py`

**Interfaces:**
- Produces: `learning_indicators.INTERVALS: tuple[str, ...] = ("1h", "4h", "1d", "1w", "1M")`
- Produces: `learning_indicators.next_open_time(t_ms: int, interval: str) -> int` — 1h 3_600_000, 4h 14_400_000, 1d 86_400_000, 1w 604_800_000을 더하고, 1M은 다음 달 1일 00:00 UTC(ms). 모르는 interval은 `ValueError`
- Produces: `learning_indicators.ichimoku(candles, interval: str, tenkan=9, kijun=26, senkou_b=52, shift=26)` — 기존 `interval_ms: int` 자리를 `interval: str`로 바꾸고 미래 시각을 `next_open_time`으로 이어 만든다
- `binance_spot.fetch_klines` 시그니처는 그대로. 행의 closeTime `int(row[6]) >= now_ms`이면 제외, 다음 페이지 `startTime = int(rows[-1][6]) + 1`
- `_collect_candles`의 증분 시작점은 `last + 1`

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_learning_binance.py::test_monthly_open_bar_dropped_and_cursor_uses_close_time`: 가짜 응답 1페이지 1000행(월봉, 각 행 closeTime = 다음 달 1일 ms − 1), 2페이지 2행(마지막 행 closeTime ≥ now_ms). 결과에 마지막 행이 없고, 2번째 요청의 `startTime`이 1페이지 마지막 행 closeTime + 1인지 단언
  - `test_learning_ichimoku.py::test_next_open_time`: `2024-01-01`→`2024-02-01`, `2024-02-01`→`2024-03-01`, `2024-12-01`→`2025-01-01`(1M), 1w는 +604_800_000, 1h는 +3_600_000, `"15m"`은 ValueError
  - `test_learning_ichimoku.py::test_ichimoku_monthly_future_times`: 마지막 봉 open_time `2024-11-01` 월봉 60개 → 미래 첫 시각 `2024-12-01`, 26번째 `2027-01-01`
  - 기존 ichimoku 테스트의 `ichimoku(candles, 86_400_000)` 호출은 `ichimoku(candles, "1d")`로 바꾼다 (값 기대는 그대로)
- [ ] **Step 2:** `pytest dashboard/tests/test_learning_binance.py dashboard/tests/test_learning_ichimoku.py -q` → 새 테스트 FAIL
- [ ] **Step 3:** 위 Interfaces대로 구현. `INTERVAL_MS` 참조가 남지 않게 learning_routes 2곳·learning_collect 1곳도 바꾼다
- [ ] **Step 4:** `pytest dashboard/tests -q -k learning` → 전부 PASS, `ruff check dashboard` 경고 없음
- [ ] **Step 5:** 커밋 `feat: 학습 캔들 수집을 closeTime 기준으로 바꾸고 일목 미래 시각에 월봉 달력 반영`

### Task 2: 5개 시간봉 백필·수집 잡

**Files:**
- Modify: `dashboard/backend/services/learning_symbols.py` (`backfill_symbol`)
- Modify: `dashboard/backend/jobs/learning_collect.py` (`_collect_candles`, 일봉 러너, `collect_learning_4h`, 새 `collect_learning_1h`)
- Modify: `dashboard/backend/main.py:290-292, 355-370` (import·잡 등록)
- Test: `dashboard/tests/test_learning_collect.py`, `dashboard/tests/test_learning_symbols.py`

**Interfaces:**
- Consumes: Task 1의 `INTERVALS`, `fetch_klines`
- Produces: `backfill_symbol(symbol)` — 1d를 먼저 받아 비어 있으면 기존처럼 failed, 이어서 4h·1h·1w·1M을 받아 모두 저장 후 done
- Produces: `_collect_candles(intervals: tuple[str, ...], is_retry: bool = False, source: str = SPOT_SOURCE, alert: bool = True)` — 종목마다·시간봉마다:
  - 종목 `backfill_status != "done"` → 기존처럼 `backfill_symbol` (종목당 한 번)
  - done인데 그 시간봉 `last_open_time`이 None → `fetch_klines(sym, interval, 0)`만 받아 저장
  - 그 외 → `fetch_klines(sym, interval, last + 1)`
  - 오류가 있으면 `alert`가 True일 때 `_fail(source, …)`, False일 때 `_record_run(source, "failed", …)`; 없으면 `_record_run(source, "ok")`
- 일봉 러너 `SPOT_SOURCE` = `_collect_candles(("1d", "1w", "1M"), is_retry)`, `collect_learning_4h` = `("4h",)`
- Produces: `collect_learning_1h()` — `_collect_candles(("1h",), source="binance-spot-1h", alert=False)`를 부르고, 러너 밖 예외도 알림 없이 `binance-spot-1h` failed로 기록
- `main._register_jobs`에 `learning_1h` 잡 등록(`CronTrigger(minute=5, timezone="UTC")`)

- [ ] **Step 1: 실패하는 테스트 작성** (`test_learning_collect.py`의 기존 state_db·sent 픽스처 사용)
  - `test_jobs_scheduled`에 `assert str(scheduler.get_job("learning_1h").trigger) == "cron[minute='5']"`와 UTC 단언 추가
  - `test_1h_failure_recorded_without_alert`: fetch_klines가 예외 → `learning_collection_runs`에 source `binance-spot-1h`·status `failed` 1행, 텔레그램 발송 0건
  - `test_1h_run_does_not_mask_daily_failure`: 오늘 `binance-spot` failed 기록 후 1h 성공 실행 → `_stale_sources()`에 `binance-spot`이 남아 있다
  - `test_daily_collects_weekly_and_monthly`: done 종목 1개, 1d·1w·1M 캔들 있음 → 일봉 러너가 `fetch_klines`를 `"1d"`, `"1w"`, `"1M"`으로 각각 `last + 1`부터 호출
  - `test_missing_interval_filled_without_full_backfill`: done 종목, 1d 캔들만 있음 → 일봉 러너가 `("1w", 0)`, `("1M", 0)`으로 호출하고 `backfill_symbol`은 호출되지 않는다
  - `test_learning_symbols.py::test_backfill_from_listing`: 저장된 interval 집합이 `{"1h","4h","1d","1w","1M"}`
- [ ] **Step 2:** `pytest dashboard/tests/test_learning_collect.py dashboard/tests/test_learning_symbols.py -q` → 새 테스트 FAIL
- [ ] **Step 3:** 위 Interfaces대로 구현
- [ ] **Step 4:** `pytest dashboard/tests -q` 전부 PASS, `ruff check dashboard` 경고 없음
- [ ] **Step 5:** 커밋 `feat: 학습 탭 1시간봉·주봉·월봉 백필과 수집 잡 추가`

### Task 3: 설정·API 5개 시간봉 허용

**Files:**
- Modify: `dashboard/backend/services/learning_settings.py` (DEFAULTS·검증)
- Modify: `dashboard/backend/api/learning_routes.py` (interval 타입 3곳, 지그재그 임계값 선택)
- Test: `dashboard/tests/test_learning_chart_api.py`, `dashboard/tests/test_learning_trading.py`

**Interfaces:**
- Produces: `learning_routes.Interval = Literal["1h", "4h", "1d", "1w", "1M"]` — `get_chart`, `get_order_context`, `OrderRequest.interval`에 사용, 기본값 `"1d"` 유지
- 지그재그 임계값은 `settings["elliott"][f"threshold_{interval}"]`
- DEFAULTS elliott에 Global Constraints의 5개 키, `_validate`가 5개 모두 1~50 검사(메시지 형식은 기존 `elliott.threshold_1d`와 같게)

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_chart_accepts_all_intervals` (5개 parametrize): 각 interval 캔들 60개 시드 → 200, `candles` 60개
  - `test_chart_rejects_unknown_interval`: `interval=15m` → 422
  - `test_stored_settings_get_new_threshold_defaults`: `learning_settings`에 `{"elliott": {"threshold_1d": 12, "threshold_4h": 6, "levels": [...]}}`만 저장 → `GET` 설정에 `threshold_1h` 3.0, `threshold_1w` 20.0, `threshold_1M` 30.0, `threshold_1d` 12
  - `test_threshold_out_of_range_rejected`: `threshold_1M` 51 → 400
  - `test_short_monthly_history_returns_200`: 1M 캔들 10개 → 200, `state`의 일목 판정 필드가 null
  - `test_learning_trading.py::test_order_uses_requested_interval_context`: 1M 캔들 시드, `interval: "1M"` 매수 → 201, `_order_context`가 `"1M"`으로 호출됨(monkeypatch로 감싸 확인)
- [ ] **Step 2:** 해당 테스트 파일 실행 → 새 테스트 FAIL
- [ ] **Step 3:** 구현
- [ ] **Step 4:** `pytest dashboard/tests -q` 전부 PASS, `ruff check dashboard` 경고 없음
- [ ] **Step 5:** 커밋 `feat: 학습 탭 차트·주문 API와 설정에 5개 시간봉 허용`

### Task 4: 프론트 토글·설정 + 문서

**Files:**
- Modify: `dashboard/frontend/src/lib/learningApi.ts:5,17`
- Modify: `dashboard/frontend/src/components/learning/learningShared.ts:46`
- Modify: `dashboard/frontend/src/components/learning/LearningChart.tsx:144,163,206,248-272`
- Modify: `dashboard/frontend/src/components/learning/TradePanel.tsx:121`
- Modify: `docs/plans/learning-tab-phase1-spec-2026-11-18.md` (시간 단위 행에 대체 안내 한 줄)
- Test: `dashboard/frontend/tests/learningChartData.test.ts`

**Interfaces:**
- `Interval = '1h' | '4h' | '1d' | '1w' | '1M'`, `LearningSettings.elliott`에 `threshold_1h|4h|1d|1w|1M: number`
- `learningShared.ts`: `INTERVALS: Interval[] = ['1h', '4h', '1d', '1w', '1M']`, `INTERVAL_LABELS = { '1h': '1시간봉', '4h': '4시간봉', '1d': '일봉', '1w': '주봉', '1M': '월봉' }`, `isIntraday(i: Interval): boolean` (1h·4h만 true)
- 차트 토글은 `INTERVALS` 순서, `timeVisible`·`withHour`는 `isIntraday`, 설정 폼 라벨은 `지그재그 임계값 1시간봉 (%)` 형식으로 5개

- [ ] **Step 1:** `learningChartData.test.ts`에 `INTERVALS` 순서·`isIntraday`(1h·4h true, 1d·1w·1M false) 테스트 추가 → `npm test` FAIL
- [ ] **Step 2:** 구현
- [ ] **Step 3:** `npm test`, `npm run build` PASS, `npx eslint src/components/learning src/lib/learningApi.ts` 새 오류 없음
- [ ] **Step 4:** 로컬 테스트 서버(ego-lite)로 BTCUSDT 5개 토글 확인: 월봉 캔들과 미래 구름, 1h 시:분 표시, 설정 화면 임계값 5개
- [ ] **Step 5:** 커밋 `feat: 학습 차트에 1시간봉·주봉·월봉 토글과 임계값 설정 추가`
