# PLAN_2: Feb 5 이벤트 진단 및 스코어링 개선

## 분석 배경

2026-02-05 BTC/USDT 급락/급등 이벤트를 현재 기술적 지표 시스템(11점 체계)이 탐지할 수 있는지 진단.

---

## 1. 이벤트 개요 (실제 가격 데이터)

| 시간 | 종가 | 비고 |
|------|------|------|
| 2026-02-04 12:00 | 76,181 | 하락 시작 |
| 2026-02-04 14:00 | 74,360 | 첫 큰 하락 봉 |
| 2026-02-05 15:00 | 67,489 | 급락 가속 (고가→저가 66,720) |
| 2026-02-05 20:00 | 63,776 | 대량 매도 (거래량 13,269 BTC) |
| 2026-02-06 00:00 | 63,509 | **절대 저점** (저가 60,000) |
| 2026-02-06 01:00 | 65,715 | 반등 시작 |
| 2026-02-06 16:00 | 69,954 | 강반등 (+17% from 60K) |
| 2026-02-06 17:00 | 70,754 | 회복 완료 |

- **총 낙폭**: 76,972 → 60,000 = **-22%** (4일)
- **변동폭**: 28.3% (Feb 4-7 high/low)
- **거래량**: 평소 대비 3.3~3.4× 급등 (outlier 탐지 작동)

---

## 2. 진단 결과: 기술적 지표 퍼포먼스

### 점수 시계열 (1h, signal_threshold=3.0)

| 시간 | 종가 | 점수/11 | 방향 | Signal |
|------|------|---------|------|--------|
| Feb4 14:00 | 74,360 | 3.00 | BEARISH | LOW |
| Feb4 19:00 | 73,923 | 3.49 | NEUTRAL | LOW |
| Feb5 20:00 | 63,776 | **3.84** | BEARISH | LOW ← 최고점수 |
| Feb5 23:00 | 62,910 | 3.38 | NEUTRAL | LOW |
| Feb6 04:00 | 64,906 | 3.46 | BULLISH | LOW |
| Feb6 16:00 | 69,954 | 3.73 | BULLISH | LOW |

**결론**: 방향 탐지는 올바르나, 최대 3.84pt로 MEDIUM(5pt) 임계값 미달.

---

## 3. 지표별 점수 드릴다운 (Feb5-20:00, 급락 극점)

```
TOTAL: 2.46/11 (22.4%)  Signal=LOW  Dir=BEARISH

Stage1: 0.46/2  ← ADX declining=False (ADX가 오히려 상승: 58.7)
Stage2: 0.00/6  ← 전부 0점 (핵심 문제)
Stage3: 2.00/3  ← BB expansion + ATR increase 작동

[Stage1]
  ADX decline: False  (ADX=58.7, 급락 중 추세강도 오히려 강화 → declining 아님)
  ATR spike: False    (ATR=1527 vs prev=1239, 46% 강도 — 1.5× 임계 미달)

[Stage2]
  RSI divergence: False (RSI=17.9 oversold, 하지만 다이버전스 없음)
  StochRSI crossover: None (K=6.9, D=14.1, K<D — 크로스 아직 미발생)
  MACD crossover: None (MACD=-2159 vs Signal=-1681, 깊은 베어리시)
  MACD histogram zero cross: None

[Stage3]
  BB middle break: False
  BB squeeze→expansion: True ✓ (1pt)
  ATR increase: True ✓ (1pt)

[기타]
  Heikin Ashi: filter_bearish=True (방향 올바름)
  Hull RSI ribbon: bearish (방향 올바름)
  Sideways filter: False (ADX=58.7, 횡보 아님 — 억제 없음)
  OUTLIER: 거래량 급등 3.4× (탐지됨, action="flag" 로 점수 영향 없음)
```

---

## 4. 근본 원인 분석

### 4-1. Stage1 미작동: ADX가 급락 중 오히려 상승
- 급락이 강한 **하락 추세**이므로 ADX는 하락하지 않고 상승 (58.7까지)
- Stage1의 ADX 조건: "추세 약화" 신호인데, 급락은 추세 강화
- **설계 철학 문제**: Stage1은 "횡보 → 변동성 전환"을 위한 것으로, 이미 트렌드가 강한 급락은 Stage1으로 탐지 불가

### 4-2. Stage2 전구간 0점: 지연 지표의 한계
- **StochRSI**: 급락 중 K는 6.9, D는 14.1 (K<D). 크로스오버는 반등 후 발생 → 신호가 바닥 이후에 나옴
- **RSI 다이버전스**: 가격이 계속 하락 중이라 "가격 저점↓ RSI 저점↑" 패턴 형성 안됨
- **MACD**: 크로스오버까지 lag가 매우 큼 (수십 봉)

### 4-3. Outlier 탐지는 작동하나 점수에 미반영
- `outlier.is_outlier = True`, `alerts = ['거래량 급등 (3.4배)']`
- 현재 `action: "flag"` 설정 → 점수에 영향 없음
- `action: "override"` 로 변경하면 score=100 강제, 하지만 과도한 false positive 위험

---

## 5. 개선 방향 (우선순위 순)

### 개선안 A: ATR 스파이크 임계값 조정 (즉시 효과)
**현재**: spike_multiplier_full=1.5 (즉, ATR이 1.5× 증가해야 강도 1.0)
**문제**: Feb5-20:00의 ATR 강도는 46% — 2점짜리 Stage1 ATR 체크 부분 기여
**개선**: spike_multiplier_full=1.2로 낮추면 → 급락 시 강도 75% 이상으로 Stage1 점수 증가

```yaml
intensity:
  atr_anomaly:
    spike_multiplier_full: 1.2   # 1.5 → 1.2
```
예상 효과: Stage1 ATR 점수 0.46 → 0.75, 총점 2.46 → 2.75

### 개선안 B: ATR 스파이크 임계 ratio 별도 설정 (Stage1 ATR 스파이크 적극 탐지)
현재 ATR_spike 조건: `atr / atr_prev > spike_multiplier` (아직 미달)
Feb5 ATR ratio = 1527/1239 = **1.23**
spike_multiplier를 1.2로 낮추면 → `spike=True`로 ATR anomaly Stage1 활성화

```yaml
indicators:
  atr:
    period: 14
    comparison_bars: 5
    spike_multiplier: 1.2   # 별도 파라미터 추가 필요
```

### 개선안 C: Volume 스파이크를 Stage1 조건으로 추가 (신규 지표)
현재 거래량 분석: `outlier_detection`에만 있고 스코어링에 미반영
Volume 3.4× 급증 = 강한 이벤트 신호
Volume spike check를 Stage1 (또는 Stage2)에 추가하면 Feb5 같은 이벤트를 직접 탐지 가능

```yaml
indicators:
  volume:
    lookback: 20
    spike_threshold: 2.5   # 2.5× 이상 = 스파이크 (현재 3.0 → 완화)
scoring:
  stage1:
    volume_spike: 1   # 신규 1점 (총점 12점으로 상향)
```

### 개선안 D: RSI oversold/overbought 직접 점수화 (가장 단순, 즉시 효과)
현재: RSI=17.9 oversold이지만 Stage2에 점수 없음
Stage2에 "RSI 극단값" 체크 추가 (다이버전스 없이도):

```yaml
scoring:
  stage2:
    rsi_extreme: 1   # RSI <20 or >80 시 1점 (신규)
```
Feb5-20:00 RSI=17.9 → 1점 추가, 총점 3.46 → 4.46 (여전히 MEDIUM 미달)

### 개선안 E: BB 중간선 이탈 조건 완화 또는 BB 하단 돌파 별도 추가
현재: BB 중간선 이탈이 stage3에 있으나 Feb5에서는 이미 하단 돌파 상태
BB 하단 돌파(percent_b < 0) = 강한 베어 신호인데, 현재는 탐지 안됨

---

## 6. 권장 즉시 조치 (복합 적용 시 예상 점수)

| 조치 | 점수 증가 | 비고 |
|------|-----------|------|
| A: ATR spike_multiplier 1.5→1.2 | +0.3~0.5pt | config만 변경 |
| C: Volume spike Stage1 추가 | +1.0pt | 코드 수정 필요 |
| D: RSI extreme Stage2 추가 | +1.0pt | 코드 수정 필요 |

**복합 적용 시**: 2.46 + 0.5 + 1.0 + 1.0 = **4.96pt** → MEDIUM(5pt)에 거의 도달
MEDIUM 임계값을 5→4.5로 소폭 조정 시 → **탐지 성공**

---

## 7. 다음 단계

- [x] **즉시**: ATR spike_multiplier 1.5 → 1.2 변경 (config only) — `intensity.atr_anomaly.spike_multiplier_full`
- [x] **단기**: Volume spike → Stage1 점수화 (config `scoring.stage1.volume_spike: 1` + `_evaluate_stage1()` 코드)
- [x] **단기**: RSI extreme (RSI <20 or >80) → Stage2 1pt 추가 (config `scoring.stage2.rsi_extreme: 1` + `_evaluate_stage2()` 코드)
- [x] **중기**: MEDIUM 임계값 5 → 4.5 조정 (`thresholds.medium: 4.5`)
- [x] **검증**: 위 변경 후 Feb5 이벤트 재실행, 전체 500봉 false positive 확인
  - Feb5-20:00: **5.00/13 MEDIUM BEARISH** → 탐지 성공 (기존 2.46/11 LOW → 개선)
  - Stage1 기여: ATR 100% + 거래량 3.43× = 2.00pt
  - Stage2 기여: RSI 극단값(17.9) = 1.00pt
  - Stage3 기여: BB확장 + ATR증가 = 2.00pt
  - 500봉 MEDIUM+ 유니크 신호: 8개 (신호밀도 0.026/봉)
  - 방향 적중률: 16.7% — 변동성 탐지용 지표이므로 허용 범위

---

## 8. 현재 시스템 강점 확인

- **방향 탐지 정확**: 급락 중 BEARISH, 반등 중 BULLISH 올바르게 판단
- **Sideways filter 미작동**: ADX=58.7로 횡보 억제 없음 (정상)
- **Outlier 탐지 작동**: 거래량 3.3~3.4× 감지 (flag 모드)
- **Stage3 작동**: BB expansion + ATR increase = 2/3pt 기여
- **Hull RSI ribbon**: bearish→bullish 전환 올바르게 반영
- **Heikin Ashi**: filter_bearish→filter_bullish 전환 올바름

---

*분석일: 2026-02-20*
*데이터: BTC/USDT 1h 500봉 (Binance)*
*엔진: BacktestEngine window=100, signal_threshold=3.0*

---

## 9. Signal Booster 통합 결과 (2026-02-21)

PLAN_2 지표들을 signal booster 레이어로 TechnicalAnalyzer에 통합 완료.
- **방식**: 2-layer scoring (Base 변동성 점수 + Signal Boost 이벤트 가산)
- **커밋**: `9b140a8` — 214개 테스트 전체 통과

### 백테스트 결과 (BTC/USDT 1h, 2025-08-14 ~ 2025-12-28, 3265봉)

| 지표 | 결과 |
|------|------|
| 이벤트 탐지율 | **100%** (10/10) |
| 오탐률 | **75%** (118 신호 중 88개가 3% 변동 없음) |
| HIGH 신호 | 129개 |
| MEDIUM 신호 | 943개 |
| 평균 점수 | 35.1 |

### 문제점: 오탐률 75%

부스터들이 각각 독립적으로 점수를 더하는 구조 → 노이즈 누적.
- 진짜 이벤트: 부스터 4~6개 동시 발동, score 67~100
- 오탐: 부스터 1~2개만 발동, score 40~55
- `bb_expansion`: 평상시에도 ~50% 확률로 발동 (가장 큰 노이즈원)
- `volume_spike_strong`: 2.5x 기준이 1h봉에서 너무 낮음
- `stochrsi_extreme`: K<20 or K>80이 빈번
- Pine Script 원본의 HA 필터 + 카테고리 구조가 반영 안됨

---

## 10. 오탐률 개선 계획: Pine Script 기반 카테고리 + HA 필터 (2026-02-21)

### 근본 원인

Pine Script 원본은 **추세 신호 + HA 필터** 구조인데, 현재 코드는 이 구조를 반영하지 않음.

```pine
// Pine Script 원본
rawTrendBuy = MHULL > SHULL and MHULL[1] <= SHULL[1]  // Hull MA 크로스오버
rawStochBuy = ta.crossover(stochK, hullrsi1)           // StochRSI × Hull RSI
filterBuy = useHAFilter ? haConditionBuy : true         // HA 필터 게이트
finalTrendBuy = rawTrendBuy AND filterBuy               // 신호 × 필터

// RSI Trend Line
frsi = ta.hma(ta.rsi(close, rsiLengthInput), 10)       // fast Hull RSI
srsi = ta.hma(ta.rsi(close, rsiLengthInput2), 10)      // slow Hull RSI
rsic = frsi > srsi ? bullish : bearish                  // frsi/srsi 크로스오버
```

### Pine Script → 우리 코드 매핑

| Pine Script | 우리 코드 | 현재 상태 |
|---|---|---|
| `MHULL/SHULL` crossover | `hull_ma.py:hma()` 함수 존재 | 추세 신호로 미사용 |
| `stochK crossing hullrsi1` | `stoch_rsi.py` `hull_rsi_crossover` 파라미터 있음 | `hull_rsi_value` 미전달 → 항상 None |
| `frsi/srsi` crossover (RSI Trend Line) | `rsi.py` + `hull_ma.py:hma()` | 미구현 |
| HA 필터 (safe mode) | `heikin_ashi.py` `filter_bullish/filter_bearish` | 게이트로 미사용 |
| MACD crossover | `macd.py` `crossover` (golden/death) | 부스터로 사용 중 |
| ADX DI crossover | `adx.py` `di_crossover` (bullish/bearish) | 미사용 |

**결론: 필요한 빌딩 블록이 모두 있지만 연결이 안 되어 있다.**

### 새 아키텍처: 카테고리 기반 신호 + HA 필터 게이트

**기존** (flat booster list → 독립 합산):
```
boost = rsi_extreme(10) + bb_expansion(10) + volume_spike(10) + ...
```

**변경** (카테고리 + HA 필터 게이트):
```
1. HA 필터 확인 (filter_bullish OR filter_bearish?)
   → 실패시 boost = 0 (시장이 방향 없이 횡보 중)

2. 카테고리별 신호 확인:
   Trend(3):     hull_ma_crossover, macd_crossover, adx_di_crossover
   Momentum(4):  rsi_extreme, rsi_divergence, rsi_trend_crossover, hull_rsi_crossover
   Volatility(4): atr_spike, bb_expansion(강화), volume_spike(강화), outlier(critical만)

3. boost 적용 조건:
   - HA 필터 통과 AND
   - Trend/Momentum 중 최소 1개 AND
   - Volatility 중 최소 1개
```

### 신규/변경 부스터 상세

| 부스터 | 카테고리 | 상태 | 설명 |
|--------|---------|------|------|
| `hull_ma_crossover` | Trend | **신규** | Pine Script MHULL/SHULL 크로스오버 |
| `adx_di_crossover` | Trend | **신규** | ADX +DI/-DI 교차 |
| `rsi_trend_crossover` | Momentum | **신규** | frsi/srsi 교차 (Hull RSI fast/slow) |
| `hull_rsi_crossover` | Momentum | **신규** | StochK × HullRSI 교차 (기존 파라미터 연결) |
| `bb_expansion` | Volatility | **강화** | bandwidth/prev >= 1.3 (단순 expanding 제거) |
| `volume_spike_strong` | Volatility | **강화** | threshold 2.5 → 4.0 |
| `atr_spike` | Volatility | **강화** | multiplier 1.2 → 1.5 |
| `outlier` | Volatility | **강화** | critical_only (half-boost 제거) |
| `stochrsi_extreme` | - | **제거** | hull_rsi_crossover로 대체 |
| `bb_middle_break` | - | **제거** | 노이즈만 추가 |

### 수정 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `app/analyzers/technical_analyzer.py` | HA 필터 게이트, 카테고리 분류, Hull MA/RSI Trend/Hull RSI 크로스 계산 |
| `config/technical.yaml` | 카테고리 태그, 신규 4개 부스터, 2개 비활성화, 임계값 강화 |
| `tests/unit/test_technical_analyzer.py` | HA 게이트, 카테고리 게이트, 신규 부스터 테스트 |

### 검증 방법

1. `pytest tests/ -v` — 기존 214개 + 신규 테스트 전체 통과
2. `python scripts/backtest_real_data.py` 재실행:
   - 목표: 탐지율 >= 80%, 오탐률 < 40%
   - 신호 수 118개 → 20~30개로 대폭 감소 예상

---

*업데이트: 2026-02-21*
