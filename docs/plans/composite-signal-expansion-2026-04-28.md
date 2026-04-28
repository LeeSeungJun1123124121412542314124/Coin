# Composite 신호 확장 plan — 기술 지표 + 파생 + 매크로 통합

**작성일:** 2026-04-28
**선행 plan:** `backtest-tuning-infra-2026-04-28.md`, `tuning-runbook.md`
**대상:** `dashboard/backend/services/composite_backtest.py` 신호 점수 시스템

---

## 1. Context — 왜 이 plan이 필요한가

### 1-1. 튜닝 인프라 본 실행 결과 (2026-04-28)

자동 튜닝 인프라(walk-forward + Optuna 12파라미터)로 본 실행 + A(임계값 하한↓) + B(trade_count factor) 두 단계 개선:

| 지표 | 본 실행 | A 단계 | B 단계 | 변화 |
|------|--------|--------|--------|------|
| `avg_oos_expectancy` | +1.39 | +4.54 | **+7.18** | 5x ↑ |
| `avg_oos_profit_factor` | 1.14 | 2.45 | **3.55** | 3x ↑ |
| `avg_oos_win_rate` | 27.4% | 38.9% | **40.8%** | ↑ |
| `avg_oos_mdd` | 3.15% | 5.21% | **3.36%** | 양호 |
| `avg_oos_trade_count` | 5 | 5 | **4** | 변화 없음 ❌ |

**결론:** PF 3.55 / 음의 expectancy 해소 / MDD 3.4%로 신호 품질은 매우 우수. 단 거래 빈도 OOS 4건/월에서 **본질적 한계** 도달.

### 1-2. 한계 진단

현재 시스템:
- 기술 점수 = RSI + MACD + BB + ADX 4지표 단순/가중 평균
- 매크로 = 단일 점수 `macro_bullish` (튜닝 시 55.0 고정값)

**문제:**
1. **신호 빈도 한계** — 4지표가 동시에 한 방향으로 정렬되는 시장 상황이 1h봉에서 월 5~10번. 임계값을 낮춰봐도 노이즈 거래 증가로 expectancy 무너짐.
2. **매크로 단순화** — 시점별 매크로 변동 미반영. 모든 윈도우에 동일한 macro_bullish=55.0이 적용되어 시장 레짐(강세/약세/유동성 사이클) 차이를 못 잡음.
3. **사용 가능 자원 미활용** — 프로젝트에 이미 구현된 OBV, MFI, VWAP, Volume Spike, Stoch RSI, OI/Funding Rate(`DerivativesAnalyzer`), MVRV(`OnchainAnalyzer`) 등이 composite_backtest에서 안 쓰임.

### 1-3. 사용자 요구

- 매크로 5개 추가: **TGA, M2, OI, Funding Rate, BTC Dominance** (TGA는 방향성만)
- 기술 지표는 **리서치(가이드/구현된 모듈)에 있는 것 참고**

---

## 2. 기존 자산 인벤토리 — "이미 있는 것부터 쓰자"

### 2-1. 기술 지표 모듈 (구현 완료, composite 미사용)

| 모듈 | 경로 | 시그니처 | 활용 방향 |
|------|------|----------|-----------|
| **OBV** | `app/analyzers/indicators/obv.py` | `calculate(df, period)` + `get_divergence(df, lookback)` | 가격-거래량 다이버전스 (가짜 상승/반등 감지) |
| **MFI** | `app/analyzers/indicators/mfi.py` | `calculate(df, period=14)` → 0~100 | 거래량 가중 RSI (RSI 보완) |
| **VWAP** | `app/analyzers/indicators/vwap.py` | `calculate(df, period=20)` + `get_deviation_pct(df, period)` | 기관 평균가 이탈률 (추세/되돌림) |
| **Volume Spike** | `app/analyzers/indicators/volume_spike.py` | `calculate(df, period=20)` → 비율 | 단기 거래량 폭발 (관심 집중) |
| **Stoch RSI** | `app/analyzers/indicators/stoch_rsi.py` | K/D 라인 + 크로스오버 dict | 단기 모멘텀 전환 (추가 진입 트리거) |
| ATR | `app/analyzers/indicators/atr.py` | `calculate(df, period=14)` | 변동성 기반 SL/TP 동적화 (현재 % 고정 → 후속 plan) |

### 2-2. 파생/온체인 분석기 (구현 완료, composite 미사용)

| 분석기 | 경로 | 입력 | 출력 |
|--------|------|------|------|
| **DerivativesAnalyzer** | `app/analyzers/derivatives_analyzer.py` | `DerivativesData(oi_current, oi_3d_ago, funding_rate)` | `score(0~90) + signal(NEUTRAL/OI_SURGE/SHORT_CROWDED/...)` + details |
| **OnchainAnalyzer** | `app/analyzers/onchain_analyzer.py` | `{mvrv: float, ...}` | `score + mvrv_signal` + boost |

이미 백테스트로 임계값 튜닝까지 끝나 있다. 데이터만 공급하면 즉시 통합 가능.

### 2-3. 매크로 데이터 인프라 (대시보드 코드 일부 존재)

- **FRED API**: `WTREGEN` (TGA), `M2SL` (M2) — `docs/가이드2.md`에 API 사용법 명시. 키만 있으면 수집 가능.
- **CoinGecko API**: BTC Dominance — 무료 API. 일간 해상도.
- **Bybit API (ccxt)**: OI, Funding Rate — 인증 없이 시간봉 단위 수집 가능.

---

## 3. 추가 신호 분류 — 3개 카테고리

### A. 기술 지표 확장 (단기 신호 빈도↑)

이미 구현된 5개 모듈을 composite의 점수 계산에 통합. 외부 데이터 의존성 0.

- **OBV divergence** — bearish/bullish/None을 -1/+1/0 신호로
- **MFI** — `>80` 과매수(short bias), `<20` 과매도(long bias), 그 사이는 0
- **VWAP deviation** — 양수 = 추세 추종, 음수 = 평균회귀 기회
- **Volume Spike** — `>2.0` 비율 시 high-conviction 신호 가산
- **Stoch RSI cross** — bullish_cross/bearish_cross를 진입 트리거로

### B. 파생 신호 (포지션 쏠림 + 청산 위험)

`DerivativesAnalyzer`를 그대로 호출, 결과 score를 composite에 합산.

- **OI 3일 변화율** — 추세 강화/약화 (가격 변화와 디버전스 분석)
- **Funding Rate** — 75th percentile 이상/음수 영역에서 역방향 신호
- **청산 위험 점수** — OI 급등 + FR 극단 동시일 때 진입 회피 (= 음의 가산점)

### C. 매크로 컨텍스트 (장기 환경)

5개 매크로 지표를 단일 `macro_score`로 집약.

| 지표 | 처리 방식 | 출력 신호 |
|------|-----------|-----------|
| **TGA** | 4주 MA 기울기 | -1 (상승=유동성 흡수=악재) / 0 / +1 (하락=공급=호재) |
| **M2** | 전월 대비 YoY 부호 | -1 / 0 / +1 |
| **BTC Dominance** | 60% 기준 + 8주 MA 추세 | -1 (50% 이하 = alt 시즌) / 0 / +1 (60% 이상 = 위험회피) |
| **OI** | (이미 B에 포함, 매크로에는 미사용) | — |
| **Funding Rate** | (이미 B에 포함, 매크로에는 미사용) | — |

→ macro_score = base(50) + sum(가중 × 각 신호) → 0~100 정규화

이렇게 하면 윈도우별로 시점별 macro_score가 자연스럽게 변동.

---

## 4. 구현 Phase

### Phase 1: 기술 지표 확장 (외부 의존성 0, 즉시 가능)

**목표:** OBV/MFI/VWAP/Volume Spike/Stoch RSI를 composite tech_score에 통합.

**변경 범위:**
- `composite_backtest.py`:
  - `CompositeBacktestParams`에 5개 weight 필드 추가 (`tech_weight_obv`, `_mfi`, `_vwap`, `_volume_spike`, `_stoch_rsi`) — 기본값 None (backward-compat)
  - `calc_tech_bullish_score / _bearish_score`에 5개 신호 점수화 로직 추가
  - 기존 4지표와 동일한 normalize-and-weighted-average 패턴
- `backtest_tuner.py`:
  - search space에 5개 weight 추가 (총 9개 기술 가중치 + 1 매크로 가중치)
  - 정규화는 9개 raw → 합 1.0
- `backtest_objectives.py`: 변경 없음

**Acceptance:**
- avg_oos_trade_count ≥ 8 (현재 4의 2배) AND
- avg_oos_profit_factor ≥ 2.0 AND
- avg_oos_expectancy > 0 ⟶ 통과

→ 통과 시 Phase 2로. 미통과 시 search space 재조정 또는 Phase 1 acceptance 재검토.

### Phase 2: 파생 신호 통합 (Bybit API, 외부 키 0)

**목표:** OI + Funding Rate를 score 계산에 합산.

**변경 범위:**
- 데이터 수집기 확장:
  - `DataCollector`에 `fetch_oi_funding(symbol, since, end)` 추가
  - ccxt: `bybit.fetch_open_interest_history()`, `bybit.fetch_funding_rate_history()`
  - 1h봉 align: 8h 단위 funding rate를 forward-fill
- `_run_backtest_sync` 루프에서 매 봉마다 `DerivativesAnalyzer.analyze()` 호출
  - 결과 score를 long_score/short_score에 가산 (signal 종류별 부호 결정)
  - `LIQUIDATION_RISK` 신호 시 진입 차단
- `CompositeBacktestParams`에 `derivatives_weight` 추가

**Acceptance:**
- avg_oos_trade_count ≥ 12 AND
- avg_oos_profit_factor ≥ 1.8 AND
- avg_oos_expectancy > 0

### Phase 3: 매크로 확장 (외부 API + 시계열 align)

**목표:** TGA + M2 + BTC Dominance를 시점별 macro_score로 변환.

**변경 범위:**
- 새 모듈 `dashboard/backend/services/macro_collector.py`:
  - FRED API 클라이언트 (TGA = `WTREGEN`, M2 = `M2SL`)
  - CoinGecko 클라이언트 (BTC Dominance)
  - 결과를 `pd.Series` 시계열로 반환 (datetime index)
- 새 모듈 `dashboard/backend/services/macro_score.py`:
  - `compute_macro_timeseries(start, end, interval) -> pd.Series` (값 0~100)
  - TGA/M2/Dominance 각 -1/0/+1 신호 → 가중합 → 50 + 가중합으로 0~100 매핑
- `composite_backtest._run_backtest_sync`:
  - 기존 `macro_bullish` 단일값 대신 시계열 사용 — 매 봉 시각의 macro_score 조회
- `backtest_tuner.run_walk_forward`:
  - 매크로 시계열을 windows 외부에서 한 번 수집하고 모든 윈도우에 공유
- 환경 변수 `FRED_API_KEY` (없으면 macro_score 시계열은 50.0 고정 = 기존 동작)

**Acceptance:**
- avg_oos_trade_count ≥ 12 AND
- avg_oos_profit_factor ≥ 2.0 AND
- avg_oos_expectancy > 0 AND
- avg_oos_win_rate ≥ 50% (매크로 컨텍스트로 잘못된 진입 줄어드는 효과 검증)

---

## 5. 데이터 수집 인프라 변경 요약

| 데이터 | 소스 | 인증 | 해상도 | Phase |
|--------|------|------|--------|-------|
| OI 시계열 | Bybit (ccxt) | 무 | 1h | 2 |
| Funding Rate | Bybit (ccxt) | 무 | 8h → 1h FF | 2 |
| TGA | FRED `WTREGEN` | 무료 키 | 일간 → 1h FF | 3 |
| M2 | FRED `M2SL` | 무료 키 | 월간 → 1h FF | 3 |
| BTC Dominance | CoinGecko | 무 | 일간 → 1h FF | 3 |

FF = forward-fill (이전 값 유지)

---

## 6. 튜닝 파라미터 변경 (현재 12 → 최종 약 22)

**Phase 1 종료 시점 (17개):**
- 기존 12개 그대로
- `tech_weight_obv, _mfi, _vwap, _volume_spike, _stoch_rsi` 5개 추가

**Phase 2 종료 시점 (18개):**
- + `derivatives_weight` (전체 점수에서 파생 신호 비중)

**Phase 3 종료 시점 (22개):**
- + `tga_weight, m2_weight, dominance_weight, macro_aggregation_window` 4개

n_trials는 Phase가 진행될수록 늘려야 함. 권장:
- Phase 1: 200 → 300
- Phase 2: 300 → 400
- Phase 3: 400 → 500

(Optuna `n_startup_trials=20`은 그대로, 추가 trial은 TPE 학습 단계)

---

## 7. 호환성 / 안전망

- **모든 신규 파라미터 default = None 또는 0.0** → 미설정 시 기존 동작 그대로 (= B 단계 결과 재현)
- **Phase 2/3에서 외부 API 실패 시 fallback**: 빈 시계열 반환 → composite는 자동으로 단일값 50.0으로 폴백
- **테스트:** 각 Phase 종료 후 `pytest dashboard/tests/` 회귀 + 본 실행으로 acceptance 검증

---

## 8. 비-목표 (이번 plan 범위 밖)

- ATR 기반 동적 SL/TP (% 고정 → ATR multiple로 전환) — 별도 후속 plan
- Multi-timeframe (15m + 1h 결합) — 별도 plan, 데이터 fetch 2배 부담
- 실시간 매매 연결 — Phase 3 통과 후 별도 plan
- ML 신호 (LSTM, XGBoost) — Phase 3 통과 + 매크로 데이터 누적 후 별도 plan

---

## 9. 의사결정 포인트 (사용자 결정 필요)

진행 전 다음 결정이 필요:

1. **Phase 1만 먼저 갈지, 1+2 묶어 갈지** — Phase 1은 외부 의존성 0이라 1~2시간이면 끝. Phase 2는 Bybit OI 데이터 수집 인프라 신규 작성 필요(반나절~1일).
2. **FRED API key 발급 의지** — Phase 3 진행 시 필수. 이메일만 있으면 무료 발급.
3. **Phase 1 acceptance 미통과 시** — 새 지표 추가가 효과 없으면 즉시 Phase 2로 넘어갈지, 아니면 search space/objective 재조정으로 더 시도할지.

---

## 10. 작업 순서 제안

1. (이 plan 승인) → Phase 1 구현 (composite_backtest + tuner search space) → 본 실행 → acceptance 판정
2. 통과 시 → Phase 2 구현 (Bybit OI/FR 수집 + DerivativesAnalyzer 통합) → 본 실행 → acceptance
3. 통과 시 → FRED key 발급 후 Phase 3 → 본 실행 → 최종 acceptance
4. 모든 Phase 통과 시 → `tuning-runbook.md` 업데이트 + 새 베이스라인 확정

각 Phase는 독립 git 커밋, acceptance 미통과 시 즉시 재검토.

---

## 부록: B 단계 best_params 참고 (Phase 1 baseline 비교용)

| w | L/S | buf | SL/TP | pos% | lev |
|---|-----|-----|-------|------|-----|
| 0 | 58/76 | 26 | 1.0/9.0 | 15 | 3 |
| 1 | 57/72 | 54 | 1.0/7.0 | 5 | 5 |
| 2 | 54/79 | 22 | 4.0/8.0 | 10 | 5 |
| 3 | 58/81 | 39 | 4.5/10.0 | 5 | 3 |
| 4 | 57/71 | 32 | 4.5/10.0 | 5 | 5 |
| 5 | 58/66 | 17 | 5.0/9.0 | 5 | 5 |

Phase 1 결과를 이 baseline과 비교해 새 지표가 신호 품질을 떨어뜨리지 않는지 확인.
