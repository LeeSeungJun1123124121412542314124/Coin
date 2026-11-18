# 학습 탭 1차 스펙 — 차트 국면 판단 → 근거 모의매매 → 포지션 복기 (2026-11-18)

- 출처: ouroboros 인터뷰 `interview_20261118_010039` → Seed `seed_387bc0fe5a21` (모호도 0.18)
- 배경 분석: 기존 기능·겹침 표는 `D:\Dev\coolify-migration\docs\coin-feature-inventory-2026-11-18.md`
- 상태: 스펙 확정(미결 항목 결정 완료). 다음 단계는 구현 계획(writing-plans)

## 1. 목표
기존 코인 대시보드(FastAPI + React, SQLite, APScheduler, 발송 전용 텔레그램 봇)에 **'학습' 탭 하나**를 추가해,
아래 학습 루프 하나를 끝까지 쓸 수 있게 한다.

> 바이낸스 현물 USDT 일봉·4시간봉 차트에서 일목·와이코프·엘리엇을 보고 국면 판단 →
> 근거를 적어 10,000 USDT 가상 계좌로 현물 모의매매(체결 시 온체인 스냅샷 저장) →
> 포지션 단위로 14일·28일 뒤 복기 → 국면 판단 적중률·승률·DCA 대비 수익률 확인

같은 작업에서 쓸모없는 기존 수동 모의투자는 백업 후 제거한다.

## 2. 확정된 결정
| 항목 | 결정 |
|---|---|
| 키울 능력 | 국면 판단·매매 타이밍·사이클 판단·규칙 검증 모두. 1차 루프는 국면 판단 + 매매 타이밍(a+b) |
| 기준 거래소 | 바이낸스 현물 USDT (차트·체결·손익 모두). 수수료 0.1%. 업비트 캔들 수집 안 함 |
| 시간 단위 | 일봉, 4시간봉 (`docs/plans/learning-tab-timeframes-spec-2026-11-18.md`로 대체됨: 1h·4h·1d·1w·1M 5종) |
| 대상 자산 | 바이낸스 현물 USDT 페어 중 선택 추가, 동시 최대 5종목. 추가 시 상장일부터 전부 백필 |
| 저장소 | 기존 SQLite에 새 테이블 추가 (Postgres 전환 없음, 약 10만 행·10MB 수준 — 1h 추가로 대체됨: BTC 한 종목만 약 10만 5천 행(약 9MB), 5종목이면 약 50만 행·45MB 수준) |
| 가상 자금 | 10,000 USDT. 계산은 USDT, 화면에 원화 환산 병기(기존 환율 수집 재사용) |
| 매매 | 현물만. 매수·부분 매도·전량 매도. **매수·매도 모두 근거 필수** |
| 근거 입력 | 국면: 와이코프 4단계(매집·상승·분산·하락) + 불명확. 일목 신호 고정 선택지(구름 위/안/아래, 전환·기준선 교차, 후행스팬 위치, 미래 구름 색)를 현재 상태로 미리 채움. 자유 메모 선택. 현재 감지된 와이코프 후보·일목 상태를 자동 표시 |
| 일목균형표 | 전체 요소(전환선·기준선·선행스팬1·2·미래 구름·후행스팬) |
| 와이코프 후보 | 박스권 N=30봉, 폭 15% 이내, 거래량 급증 = 직전 20봉 평균 2배. 스프링/업스러스트 = 박스 이탈 후 종가 복귀. 거래량 동반 시 '강한 후보'. N·폭·배수는 화면 설정에서 변경 |
| 엘리엇 | 지그재그(일봉 10%·4시간봉 5% 되돌림 시 피벗 확정), 피보나치 0.382·0.5·0.618·1.0·1.618. 설정 변경 가능. 파동 번호는 사용자가 판단 (지그재그 임계값은 `docs/plans/learning-tab-timeframes-spec-2026-11-18.md`로 대체됨: 시간봉별 5종) |
| 온체인 스냅샷 | 체결마다 저장. CoinMetrics MVRV·활성주소, NUPL·실현가격(MVRV로 계산), mempool.space, DefiLlama(스테이블코인·SOL TVL), 바이낸스 선물 펀딩비·OI, BGeometrics 무료 SOPR, 기존 TGA·M2. 값마다 기준 날짜·출처 기록. BTC 외 종목은 종목 지표 + BTC 맥락 |
| 수집 시각 | 일봉·온체인 KST 09:10(UTC 00:10), 미갱신 항목은 낮에 1회 재시도. 4시간봉은 마감 5분 뒤 (수집 시각은 `docs/plans/learning-tab-timeframes-spec-2026-11-18.md`로 대체됨: 1h 포함·1w·1M 추가) |
| 수집 실패 | 해당 항목 비우고 사유 기록, 체결은 허용. 실패는 텔레그램 알림(기존 잡 실패 알림 방식) |
| 복기 단위 | 포지션(첫 진입~전량 청산). 기준일 = 첫 진입일 + 14일·28일. 판정 가격 = 바이낸스 일봉 종가 |
| 복기 수익률 | 실현+평가 손익 / 끝까지 보유 가정 수익률을 나란히 |
| 국면 자동 판정 | X=5%, 14일·28일 각각. 매집·상승: +5%↑ 맞음, ±5% 부분, −5%↓ 틀림. 분산·하락은 반대. 시스템은 제안만, 사용자가 확정·수정(이유 포함) |
| 성과 지표 | 국면 판단 적중률(사용자 확정값, 불명확 제외), 승률(청산 포지션 단위), DCA 대비 수익률 |
| DCA 기준선 | 계좌 전체 기간. 기준 종목은 설정에서 선택(기본 BTC). 10,000 USDT를 52주로 나눠 매주 약 192.3 USDT, 수수료 0.1%, 미매수분은 현금 |
| 화면 | 기존 탭 10개 유지 + '학습' 탭 1개(차트·매매·일지·복기·성과·백테스트 하위 화면) |
| 기존 수동 모의투자 | 제거. 6개 `sim_*` 테이블 데이터를 파일로 백업 후 삭제, 관련 API·잡·테스트 제거. Simulator에서만 쓰던 조회 API `/sim/signals`·`/sim/macro-context`·`/sim/projection`·`/sim/win-rate-analysis`도 삭제 |
| 백테스트 화면 | 지금은 메뉴에 없는 Simulator 안에만 있던 `CompositeSimulator`(종합 백테스트·튜닝)·`AutoBacktest`·`TuningResultTable`을 학습 탭 '백테스트' 하위 화면으로 연결(기능 변경 없이 위치만 이동) |
| 유지 대상 | 종합 백테스트·Optuna 튜닝·자동 백테스트(`/sim/auto-backtest`)·리더보드(paper_engine) API와 테스트, 나머지 탭·알림·12시간 리포트 |
| 적중률 '부분' | 적중률 = 맞음 ÷ (맞음+부분+틀림). 부분 비율은 따로 표시. 14일·28일 각각 |
| 1차 제외 | 주간 텔레그램 리포트, 학습 루틴(콘텐츠·퀴즈·일일 과제·복기 알림), 목표 수치·최소 표본 수, 최대 낙폭, 규칙 백테스트 신규 확장(기존 화면 연결만 함) |

## 3. 수용 기준 (검증 방법)
| # | 기준 | 검증 |
|---|---|---|
| 1 | 바이낸스 현물 USDT 페어 추가(없는 페어·6번째 거부), 일봉·4시간봉 상장일부터 저장·조회 | pytest |
| 2 | 수집 스케줄(09:10, 낮 재시도, 4시간봉 마감 5분 뒤), 실패 텔레그램 알림, 비밀값 미노출 | pytest |
| 3 | 일목 전체 요소 계산(미래 구름 포함) | pytest |
| 4 | 와이코프 박스권·거래량 급증·스프링/업스러스트·강한 후보, 설정값 변경 재계산 | pytest |
| 5 | 엘리엇 지그재그 피벗·피보나치 레벨, 설정값 변경 재계산, 파동 번호 자동 부여 없음 | pytest |
| 6 | 10,000 USDT 계좌, 바이낸스 현물가 체결, 0.1% 수수료, 잔고·보유·손익, 원화 환산, 초과 매수·매도 거부 | pytest |
| 7 | 매수·매도 근거 필수, 미리 채운 와이코프·일목 상태, 메모 없이도 체결 | pytest |
| 8 | 체결 시 온체인 스냅샷(기준 날짜·출처), 비BTC 종목 처리, 실패 항목 사유 기록 후 체결 성공 | pytest |
| 9 | 포지션 단위 일지, 14·28일 복기(근거·실현+평가·보유 가정) | pytest |
| 10 | 국면 자동 판정 제안 ±5%, 사용자 확정·수정 저장 | pytest |
| 11 | 적중률(확정값, 불명확 제외)·승률(청산 포지션) | pytest |
| 12 | 계좌 가치 vs DCA 기준선(52주, 기준 종목 설정, 미매수 현금) | pytest |
| 13 | 수동 모의투자 제거(백업 후 테이블 삭제, API 404, 관련 잡 미등록) | pytest |
| 14 | 종합 백테스트·Optuna·리더보드 기존 테스트 통과 | pytest |
| 15 | 화면: 탭 10개 유지 + 학습 탭, 차트에 일목·와이코프 마커·엘리엇·피보, 원화 환산 | 브라우저 확인 |
| 16 | 학습 탭 '백테스트' 하위 화면에서 종합 백테스트 실행·튜닝 결과·자동 백테스트가 기존과 같이 동작, `/sim/signals`·`/sim/macro-context`·`/sim/projection`·`/sim/win-rate-analysis`는 404 | 브라우저 확인 + pytest(404) + `npm test`·`npm run build` |

## 4. 사실 확인 결과 (2026-11-18, 코드 기준)
- 리더보드 `services/paper_engine.py`는 `sim_*` 테이블을 쓰지 않는다 → 수동 모의투자 제거와 무관
- 제거 대상 테이블: `sim_accounts`, `sim_predictions`, `sim_positions`, `sim_settlements`, `sim_funding_events`, `sim_account_resets` (SPF용 `predictions`는 별개, 유지)
- 바이낸스 현물·선물 공개 API는 OCI 도쿄 서버에서 접근 가능(200 응답 확인)
- 프론트 테스트 하네스 있음(`dashboard/frontend/tests/*.test.ts`, `npm test`)
- `/sim/*` 프론트 사용처
  - 메뉴에 연결된 화면: `Leaderboard.tsx` → `/sim/leaderboard` (유지)
  - 메뉴에 없는 `Simulator.tsx` 안에서만 쓰는 것: `/sim/accounts`, `/sim/predictions`, `/sim/scorecard`, `/sim/macro-context`, `/sim/signals`, `/sim/projection`, `/sim/win-rate-analysis`, 그리고 하위 컴포넌트 `SimScorecard`·`CompositeSimulator`(종합 백테스트·튜닝 UI)·`AutoBacktest`·`TuningResultTable`

## 5. 미결 항목 → 결정 완료 (2026-11-18)
1. 백테스트 화면 컴포넌트: **1차에 학습 탭 '백테스트' 하위 화면으로 연결** (2장 반영)
2. `/sim/signals`·`/sim/macro-context`·`/sim/projection`(+`/sim/win-rate-analysis`): **삭제**. `/sim/auto-backtest`는 유지
3. 적중률 '부분': **맞음만 적중, 부분 비율은 따로 표시** (2장 반영)

남은 가정(구현 중 그대로 적용, 문제 생기면 보고)
   - 체결가: 주문 시점 바이낸스 현물 최신 시세로 즉시 체결, 슬리피지 없음(가정)
   - 일목 파라미터: 9·26·52, 26봉 이동(표준값 가정)
   - 낮 재시도 시각: KST 13:00 전후(가정)
   - 체결 시 스냅샷은 실시간 호출 대신 DB에 저장된 최신 시계열 값을 읽음(한도 때문, 가정)

남은 가정 결과 (2026-11-18 구현 후 추가)
   - 체결가 가정: 유지됨. 바이낸스 현물 최신 시세 즉시 체결, 슬리피지 없음. 시세 조회 실패 시 503(`test_price_failure_503`)
   - 일목 파라미터 9·26·52, 26봉 이동: 유지됨(`test_ichimoku_linear`)
   - 낮 재시도 시각: UTC 04:00(KST 13:00)로 확정, 잡 이름 `learning_daily_retry`(`test_jobs_scheduled`)
   - 스냅샷은 저장된 최신 시계열 값 사용: 유지됨(`test_snapshot_non_btc_includes_btc_context`)
   - BGeometrics 무료 SOPR: 키 없이 쓰는 `bitcoin-data.com/v1/sopr/last`로 구현했다. 무료 값은 약 7일 지연되며(실시간은 유료 구독), 스냅샷에 `as_of`(응답 날짜)를 기록해 지연이 화면에서 드러난다. 호출 한도는 자체 예산으로 관리하고, 초과 시 `rate_limited`로 기록한다

## 6. Seed 정정 메모
- Seed의 수용 기준 마지막 3개 항목은 인터뷰 원문이 그대로 들어간 것으로, 그중 "학습용 원화 현물 모의매매"는 이후 결정(바이낸스 USDT)으로 대체됨. 위 3장의 15개 기준이 유효하다
- Seed의 "바이낸스 API 접근 가능(확실하지 않음)"은 4장에서 확인 완료

## 7. 구현 결과 (2026-11-18)
검증 기준선: `pytest crypto-volatility-bot/tests dashboard/tests` 716 passed, `ruff check`(E,F,W, E501 제외) 통과, `npm test` 통과, `npm run build` 통과(청크 500kB 경고는 기존).

| # | 기준(요약) | 증거 | 결과 |
|---|---|---|---|
| 1 | 페어 추가(없는 페어·6번째 거부), 일봉·4h 상장일부터 저장 | `test_learning_symbols.py`: test_add_up_to_five_then_reject, test_unknown_pair_rejected, test_backfill_from_listing, test_delete_symbol / `test_learning_binance.py`: test_klines_paginate_and_drop_open_bar, test_symbol_info_rejects_non_usdt_and_unknown, test_save_candles_idempotent | 충족 |
| 2 | 수집 스케줄·실패 알림·비밀값 미노출 | `test_learning_collect.py`: test_jobs_scheduled, test_source_failure_recorded_and_alerted, test_retry_only_failed_or_stale_sources, test_list_symbols_failure_recorded_and_alerted_daily/_4h, test_retry_runner_unexpected_error_recorded_and_alerted | 충족 |
| 3 | 일목 전체 요소(미래 구름 포함) | `test_learning_ichimoku.py`: test_ichimoku_linear, test_state_above_cloud_golden, test_state_insufficient_data_returns_none | 충족 |
| 4 | 와이코프 박스·거래량 급증·스프링/업스러스트·강한 후보·설정 재계산 | `test_learning_wyckoff.py`: test_spring_strong, test_upthrust_not_strong, test_width_pct_recalculation, test_vol_mult_recalculation, test_both_sides_breakout_yields_both_candidates | 충족 |
| 5 | 지그재그·피보 레벨·설정 재계산·파동 번호 없음 | `test_learning_elliott.py`: test_zigzag_threshold_10pct, test_zigzag_same_path_recalculates_with_threshold, test_zigzag_no_wave_field, test_fib_levels, test_zigzag_outside_bar_no_duplicate_time | 충족 |
| 6 | 10,000 USDT 계좌·체결·수수료 0.1%·원화 환산·초과 거부 | `test_learning_trading.py`: test_buy_sell_fee_math, test_full_sell_closes_position_and_stores_times, test_overspend_and_oversell_rejected, test_krw_shown, test_get_account_created_once | 충족 |
| 7 | 근거 필수·미리 채움·메모 없이 체결 | `test_learning_rationale.py`: test_rationale_required_for_buy_and_sell, test_validate_rationale_rules, test_memo_optional, test_order_context_prefill / `test_learning_chart_api.py`: test_order_context_has_state_keys | 충족 |
| 8 | 체결 시 스냅샷(기준 날짜·출처), 비BTC, 실패 사유 후 체결 | `test_learning_snapshot.py`: test_snapshot_non_btc_includes_btc_context, test_snapshot_missing_reason_uses_latest_failure / `test_learning_rationale.py`: test_order_succeeds_with_empty_snapshot / `test_learning_collect.py`: test_ok_run_saves_metrics_with_upsert, test_nupl_realized | 충족 |
| 9 | 포지션 단위 일지, 14·28일 복기 | `test_learning_review.py`: test_journal_groups_fills_by_position, test_review_pnl_and_hold_return, test_review_pending_when_due_in_future, test_pnl_excludes_fills_after_due_date | 충족 |
| 10 | 국면 자동 판정 ±5%, 확정·수정 저장 | `test_learning_phase_judgement.py`: test_judge_phase, test_judge_phase_custom_pct / `test_learning_review.py`: test_review_upserts_suggested, test_confirm_overrides_and_persists, test_confirm_rejections | 충족 |
| 11 | 적중률(확정값, 불명확 제외)·승률(청산 포지션) | `test_learning_metrics.py`: test_hit_rate_excludes_unclear_counts_partial_separately, test_hit_rate_counts_confirmed_not_suggested, test_hit_rate_filters_by_horizon, test_win_rate_closed_only | 충족 |
| 12 | 계좌 가치 vs DCA(52주, 기준 종목, 미매수 현금) | `test_learning_dca.py`: test_dca_52_weeks, test_dca_skips_missing_close_to_next_day, test_account_equity_series_hand_computed, test_performance_dca_null_when_ref_untracked, test_performance_dca_series_when_tracked | 충족 |
| 13 | 수동 모의투자 제거(백업 후 삭제, API 404, 잡 미등록) | `test_legacy_sim_removal.py`: test_legacy_tables_backed_up_and_dropped, test_no_legacy_tables_no_backup, test_legacy_endpoints_404, test_legacy_jobs_not_registered, test_deleted_paths_absent_from_router | 충족 |
| 14 | 종합 백테스트·Optuna·리더보드 기존 테스트 통과 | `test_sim_routes_kept.py`: test_kept_routes_registered, test_leaderboard_ok / 기존 `test_paper_engine.py`, `test_spf_composite.py` 포함 전체 716 passed | 충족 |
| 15 | 탭 10개 유지 + 학습 탭, 차트 일목·마커·엘리엇·피보, 원화 환산 | 브라우저 확인(내장 브라우저, 로컬 테스트 서버·임시 DB): 탭 10개+학습, 캔들·전환/기준/후행·선행 A/B·채운 구름·미래 구름·스프링/업스러스트 마커·지그재그·피보 가격선, 4h 전환, 설정 검증 오류(n=3 → HTTP 400)와 폭 변경 재계산, 100 USDT 매수 체결(수수료 0.10·원화 병기), 일지·복기 대기·성과 / 보조: `learningChartData.test.ts`(마커·구름·원화 포맷) | 충족 |
| 16 | 백테스트 하위 화면 동작, 삭제 API 404 | 브라우저 확인: 종합 시뮬레이션 실행(POST /api/sim/composite-backtest 200, 결과·자본곡선·거래표)·지표별 분석 토글 / pytest: test_legacy_endpoints_404, test_deleted_paths_absent_from_router / `npm test`·`npm run build` 통과 | 충족 |

### 적용된 Ruling 요약
구현 중 스펙을 구체화하거나 바꾼 컨트롤러 판단 중 동작에 영향을 준 것만 적는다(R2, R3은 테스트 구성·작업 방식이라 제외).
- R1: 구현 직전 단계에서 sim 테이블 삭제 직후 생기는 기존 sim 테스트 실패는 허용하고, sim 코드 제거 단계에서 0으로 정리
- R4: 설정 저장 시 `dca.symbol`이 있을 때만 추적 여부를 검증. 기본 BTCUSDT가 미추적이어도 다른 설정은 저장 가능
- R5: 일목에서 판단 불가한 필드는 허위 값 대신 null 반환(cloud_position, chikou, future_cloud, tk_cross 결측)
- R6: 박스 양방향 이탈 봉은 스프링·업스러스트 후보를 둘 다 낸다
- R7: 지그재그 방향 미정 상태에서 그 봉이 자기 극값이면 같은 봉에서 확정하지 않는다
- R8: 차트·주문 컨텍스트 경계: 추적됐지만 캔들 0개면 200과 빈 구조, limit 1~2000, 계산은 limit+52봉으로 하고 반환만 자름, 미추적 404
- R9: 수집 기록의 source 이름 규칙, BGeometrics는 키 가입 없이 무료 엔드포인트 사용, 재시도 대상은 오늘 실패 소스와 MVRV 지연분, 4h 잡은 4h 캔들만, 자체 호출 예산은 ok/failed만 집계
- R10: 주문 API 응답 코드(201/400/503), 종목당 열린 포지션 1개, 매수 usdt_amount는 수수료 포함 총 지출, 매도는 수수료 전 매도대금, 평단은 매수 기준, 가격 없는 종목은 평가액 null
- R11: 복기 손익은 기준일 이하 체결만 반영, 불명확은 suggested null로 저장하고 확정 거부, horizon은 14·28만 허용
- R12: DCA는 종가 없는 날 다음 종가일로 미룸, 계좌 시계열은 달력일 기준, 기준 종목 캔들이 없으면 dca null과 사유 반환, 적중률 n=0이면 null
- R13: 고아가 된 `_ms` 헬퍼 제거(프로젝트 고아 정리 규칙)
- R14: 프론트 타입은 실제 백엔드 응답 기준, 일목 4필드는 null 허용, 마커 문구·정렬 규칙, 숫자 포맷 결정적 처리
- R15: 브라우저 확인은 커밋 후 컨트롤러가 수행, 구름 채움·마커는 lightweight-charts v5 방식, 일목 근거 입력의 null은 "판단 불가" 선택지로 전송, 백테스트는 기존 composite/auto 토글 그대로 이전
- R16: 지그재그 up/down 상태에서 극값을 갱신한 봉은 같은 봉에서 되돌림을 확정하지 않아 피벗 시각이 엄격히 증가. 실데이터 브라우저 확인에서 같은 시각 피벗으로 차트가 중단된 문제를 근본 수정
- R17: 종목 추적 해제 거부 조건 추가 — 그 종목 포지션 중 첫 진입 UTC 날짜 + 29일이 오늘 이후인 것이 있으면(28일 복기 기준일 종가 수집 전) 해제 가능일을 안내하며 400, 현재 `dca.symbol`이면 400("성과 탭에서 DCA 기준 종목을 바꾼 뒤 해제하세요"). 열린 포지션 거부는 유지
- R18: 표시 정밀도 허용오차 — 매도 수량이 보유와 1e-8 미만 차이면 보유 전량으로 체결·청산, 매수 금액이 현금보다 0.005 미만 초과면 현금 전액으로 체결(현금 0이면 거부). 주문 화면 '전량' 버튼은 원본 보유 수량을 넣는다

### 최종 리뷰 수정 (2026-11-18)
- 위 R17·R18 반영, 캔들 수집 잡은 캔들이 없는(백필 pending·failed) 종목을 상장일부터 다시 백필하고 실패를 실행 오류로 기록·알림
- 입력 검증: 주문 `usdt_amount`·`qty`와 설정 숫자의 NaN·±inf는 400. 종목 추가 시 바이낸스 조회 오류(451·429·5xx·네트워크)는 503, 없는 종목은 400
- `GET /learning/account`에 `usd_krw` 추가(주문 화면 원화 환산에 사용). 일지 금액 열·복기 기준일(UTC)·저가 종목 차트 정밀도(0.001 미만 8자리) 표기 정리
- 범위 밖(보고만): `main.py` SPA catch-all이 정의되지 않은 `GET /api/*`에 HTML 200을 돌려주는 기존 동작
- 검증: `pytest crypto-volatility-bot/tests dashboard/tests` 747 passed, `ruff check` 통과, `npm test`·`npm run build` 통과, `npm run lint`는 학습 탭 밖 기존 6 errors·1 warning 그대로
