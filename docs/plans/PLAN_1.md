# 분석 엔진 품질 보완 (2차 개선) 계획서

## Context

기술적 분석 엔진 재설계(3단계 점수 + RSI 다이버전스 + 멀티 TF + 방향 태깅)가 완료됨.
현재 **155 테스트, 91% 커버리지**. 하지만 실전 운영에 필요한 핵심 보완 항목 존재.

### 현재 상태 갭 분석

| 항목 | 현재 | 문제 |
|------|------|------|
| 횡보장 필터 | ADX/BB squeeze 감지하지만 **신호 억제 없음** | 횡보장에서 오신호 쏟아짐 |
| 점수 강도 | 이진(0/1) 점수 — 약/강 구분 불가 | 점수 3점이나 9점이나 같은 "on" |
| RSI 다이버전스 | order=5 하드코딩, 거리/강도 필터 없음 | 파라미터 튜닝 불가 |
| 이상치 감지 | ATR spike(>150%)만 존재 | 거래량/가격 급변 미감지 |
| DCA 계수 | "축소 고려" 텍스트만 출력 | 실행 가능한 숫자 없음 |
| 백테스트 | 인프라 없음 | 검증 없이 운영 = 도박 |
| 멀티 TF 충돌 | primary(4h)만 집계, 나머지 무시 | 1h↔1d 충돌 감지 불가 |

---

## Phase 1: RSI 다이버전스 파라미터 정의 (HIGH)

가장 작고 안전한 변경. 하드코딩된 값을 YAML 설정으로 전환.

### 수정 파일

**`config/technical.yaml`** — rsi 섹션 확장:
```yaml
rsi:
  period: 14
  divergence_lookback: 60
  overbought: 70
  oversold: 30
  divergence_order: 5           # NEW: 피크 탐색 좌우 비교 봉 수
  min_peak_distance: 10         # NEW: 피크 간 최소 거리 (봉)
  min_divergence_pct: 0.5       # NEW: 최소 가격 변화율 (%) — 너무 작은 다이버전스 필터
```

**`app/analyzers/indicators/rsi.py`**:
- `calculate()` 시그니처에 `divergence_order`, `min_peak_distance`, `min_divergence_pct` 추가
- `_find_local_peaks/valleys`: `order=5` 하드코딩 → 파라미터 전달
- `_detect_divergence`: 피크 거리 필터 + 최소 가격 변화율 검증 추가
- 반환 dict에 `"divergence_magnitude"` 키 추가 (Phase 2에서 강도 점수에 사용)

**`app/analyzers/technical_analyzer.py`** (line 65-71):
- `rsi_cfg`에서 새 파라미터 읽어 `rsi.calculate()`에 전달 (`.get()` + 기본값)

### 테스트
- 기존 8개 RSI 테스트: 기본값으로 동작하므로 변경 없이 통과
- 신규 4-6개: `divergence_order` 변경 시 동작 변화, `min_peak_distance` 필터, `min_divergence_pct` 필터

### 검증
```bash
pytest tests/unit/test_indicators/test_rsi.py tests/unit/test_technical_analyzer.py -v
```

---

## Phase 2: 점수 강도 기반 전환 (MUST)

**핵심 변경**: 이진(0/1) → 연속(0.0~1.0) 강도 점수. 모든 이후 개선의 기반.

### 설계 원칙

- `StageResult.points`: `int` → `float` (0.0 ~ max_points)
- `max_points`는 동일 유지 (9점)
- 각 체크의 `passed` = `intensity >= 0.5` (✅/❌ 표시용)
- `intensity.enabled: false` 안전 스위치 → 기존 이진 모드 복귀

### 수정 파일

**`config/technical.yaml`** — intensity 섹션 추가:
```yaml
intensity:
  enabled: true
  adx_decline:
    max_decline_pct: 20.0       # ADX 20% 이상 하락 = 강도 1.0
  atr_anomaly:
    spike_multiplier_full: 2.0  # ATR 2배 = 강도 1.0
    contraction_ratio_full: 0.5 # ATR 50% = 강도 1.0
  rsi_divergence:
    max_magnitude_pct: 5.0      # 가격-RSI 괴리 5% = 강도 1.0
  macd_crossover:
    max_gap_pct: 1.0            # MACD-시그널 갭 1% = 강도 1.0
  macd_histogram:
    max_histogram_pct: 0.5      # 히스토그램 0.5% = 강도 1.0
  bb_middle_break:
    max_distance_pct: 2.0       # 중간선 2% 이탈 = 강도 1.0
  bb_expansion:
    min_expansion_ratio: 1.5    # 밴드폭 1.5배 확장 = 강도 1.0
  atr_increase:
    max_increase_ratio: 1.5     # ATR 1.5배 증가 = 강도 1.0
```

**지표 반환값 확장** (추가 키만, 기존 키 유지):
- `adx.py`: `"adx_prev"` 추가 (이미 line 54에서 계산됨, dict에 미포함)
- `rsi.py`: `"divergence_magnitude"` 추가 (Phase 1에서 추가)
- `macd.py`, `bollinger_bands.py`: 이미 필요한 값 모두 있음

**`app/analyzers/technical_analyzer.py`** — 8개 강도 계산 메서드 추가:

각 체크 변경 패턴:
```python
# 기존 (이진)
passed = adx_data["adx_declining"]
if passed: points += pts["adx_decline"]

# 변경 (연속)
intensity = self._calc_adx_decline_intensity(adx_data)
earned = pts["adx_decline"] * intensity
points += earned
```

각 `_calc_*_intensity()` 메서드: 조건 미충족 → 0.0, 충족 시 비율 기반 0.0~1.0

**`app/notifiers/message_formatter.py`**:
- 점수 표시: `{points:.1f}/{max_points}` (소수점 1자리)
- 강도 표시 옵션: `ADX 하락 전환 (강도: 73%)`

### 테스트
- `intensity.enabled: false`로 기존 20개 테스트 그대로 통과
- 신규 10-15개: 각 강도 함수 단위 테스트, 범위 검증, 레거시 호환성

### 검증
```bash
pytest tests/unit/test_technical_analyzer.py -v
```

---

## Phase 3: 횡보장 필터 (MUST)

**포스트-스코어링 수정자**: 횡보 감지 시 점수에 억제 계수(0.3x~1.0x) 적용.

### 횡보 감지 조건 (2개 이상 충족 시 활성화)

1. ADX < 임계값 (기본 22) — 추세 없음
2. BB squeeze 활성 — 변동성 압축
3. ATR 수축 중 — 저변동성 확인

### 수정 파일

**`config/technical.yaml`**:
```yaml
sideways_filter:
  enabled: true
  adx_threshold: 22.0
  min_conditions: 2             # 최소 충족 조건 수
  suppression_factor: 0.3       # 횡보 시 점수 억제율
  graduated: true               # true → ADX에 따라 억제율 점진 조절
  adx_floor: 10.0              # ADX 바닥 (최대 억제)
```

**`app/analyzers/technical_analyzer.py`** — `analyze()` 내:
```python
# 3단계 점수 계산 후, 최종 스코어 산출 전
sideways_info = self._evaluate_sideways(adx_data, bb_data, atr_data)
if sideways_info["active"]:
    total_points *= sideways_info["suppression_factor"]
```

새 메서드 `_evaluate_sideways()`:
- 3개 조건 체크 → `min_conditions` 이상이면 활성
- `graduated=true`: ADX 값 기반 점진적 억제 (ADX floor~threshold → factor 선형 보간)
- 반환: `{"active": bool, "suppression_factor": float, "conditions": [...], "adx_value": float}`

**`app/notifiers/message_formatter.py`**:
- 횡보 필터 활성 시 메시지에 표시:
  ```
  ⚠️ 횡보장 감지 (ADX: 18.3) — 신호 억제 70%
  ```

### 테스트
- 기존 테스트: `sideways_filter` 섹션 없으면 비활성 → 영향 없음
- 신규 8-12개: 횡보 감지/미감지, 억제율, graduated, 메시지 표시

### 검증
```bash
pytest tests/unit/test_technical_analyzer.py tests/unit/test_message_formatter.py -v
```

---

## Phase 4: 이상치 감지 / 블랙스완 (HIGH)

멀티 인디케이터 서킷 브레이커. 극단적 시장 이벤트 감지.

### 신규 파일

**`app/analyzers/indicators/volume_spike.py`** (NEW):
```python
def calculate(df, lookback=20, spike_threshold=3.0) -> dict:
    return {
        "volume": float,         # 현재 거래량
        "volume_avg": float,     # 최근 N봉 평균
        "volume_ratio": float,   # 현재/평균 비율
        "spike": bool,           # ratio > threshold
    }
```

**`app/analyzers/indicators/outlier_detector.py`** (NEW):
```python
def detect(atr_data, bb_data, volume_data, price_df, config) -> dict:
    # 4가지 체크:
    # 1. ATR 극단 스파이크 (>200% of prev avg)
    # 2. 거래량 스파이크 (>3x 평균)
    # 3. 가격 BB 밖 극단 이탈 (%B > 2.0 또는 < -1.0)
    # 4. 단일 캔들 N% 이상 변동
    return {
        "is_outlier": bool,       # severity >= 1
        "is_critical": bool,      # severity >= 2
        "severity": int,          # 0/1/2
        "alerts": list[str],
        "single_candle_pct": float,
    }
```

### 수정 파일

**`config/technical.yaml`**:
```yaml
indicators:
  volume:
    lookback: 20
    spike_threshold: 3.0

outlier_detection:
  enabled: true
  atr_spike_multiplier: 2.0
  single_candle_pct: 5.0
  action: "flag"               # "flag" = 리포트에 표시, "override" = 점수 100으로 강제
```

**`app/analyzers/technical_analyzer.py`**:
- `volume_spike` + `outlier_detector` import
- `analyze()` 내: 기존 지표 계산 후 outlier 감지 실행
- details에 `"outlier"` 키 추가
- `action: "override"` + critical → score=100, signal="HIGH"

**`app/notifiers/message_formatter.py`**:
- outlier 감지 시: `🚨 이상치 감지: ATR 극단, 거래량 급등 (심각도: 2)`

### 테스트
- `test_volume_spike.py` 신규 (5-8개)
- `test_outlier_detector.py` 신규 (8-10개)
- `test_technical_analyzer.py` 추가 (outlier 통합)

### 검증
```bash
pytest tests/unit/test_indicators/ tests/unit/test_technical_analyzer.py -v
```

---

## Phase 5: DCA 계수 명시 (HIGH)

점수 → 실행 가능한 DCA 배수로 매핑. 출력 레이어만 변경.

### 수정 파일

**`config/technical.yaml`** (또는 별도 `config/dca.yaml`):
```yaml
dca:
  enabled: true
  mapping:
    - max_score: 30
      multiplier: 1.0
      label: "정상 DCA"
    - max_score: 50
      multiplier: 0.8
      label: "DCA 소폭 축소"
    - max_score: 70
      multiplier: 0.5
      label: "DCA 절반 축소"
    - max_score: 85
      multiplier: 0.2
      label: "DCA 대폭 축소"
    - max_score: 100
      multiplier: 0.0
      label: "DCA 중단"
```

**`app/analyzers/score_aggregator.py`**:
- `AggregatedResult`에 `dca_multiplier: float = 1.0`, `dca_label: str = ""` 필드 추가
- `aggregate()`에서 final_score 기반 매핑 계산

**`app/notifiers/message_formatter.py`**:
```
💰 DCA 계수: 0.5x (DCA 절반 축소)
💡 기존 DCA 금액의 50%만 투자 권장
```

### 테스트
- 기존 aggregator 테스트: 새 필드에 기본값 → 그대로 통과
- 신규 6-8개: 각 점수 구간별 매핑, 경계값, 메시지 포함

### 검증
```bash
pytest tests/unit/test_score_aggregator.py tests/unit/test_message_formatter.py -v
```

---

## Phase 6: 백테스트 모듈 (MUST)

완전 독립 모듈. 기존 코드 수정 없음. 히스토리컬 데이터 리플레이.

### 신규 파일

**`app/backtest/__init__.py`** (empty)

**`app/backtest/engine.py`** (~200 lines):
```python
@dataclass
class BacktestSignal:
    bar_index: int
    score: float
    signal: str             # HIGH/MEDIUM/LOW
    direction: str          # BEARISH/BULLISH/NEUTRAL
    points: float
    sideways_active: bool

@dataclass
class BacktestResult:
    signals: list[BacktestSignal]
    metrics: dict[str, float]
    parameters: dict[str, Any]

class BacktestEngine:
    def __init__(self, config_path=None, window_size=100):
        self._analyzer = TechnicalAnalyzer(config_path)
        self._window = window_size

    def run(self, df, evaluation_bars=10, signal_threshold=4) -> BacktestResult:
        """슬라이딩 윈도우로 히스토리컬 데이터 리플레이."""
        # window를 한 봉씩 밀면서 TechnicalAnalyzer.analyze() 실행
        # 각 시그널의 방향 예측 vs 실제 가격 변동 비교
        # 적중률(hit_rate), 신호 빈도, 평균 점수 산출
```

**`app/backtest/data_loader.py`** (~80 lines):
- `from_exchange()`: ccxt로 히스토리컬 OHLCV 가져오기
- `from_csv()`: CSV 파일 로드 (오프라인 백테스트)

**`app/backtest/reporter.py`** (~60 lines):
- 백테스트 결과 텍스트 요약 포맷

### 핵심 메트릭
- `hit_rate`: 방향 예측 적중률
- `total_signals`: 총 신호 수
- `signals_per_bar`: 신호 빈도 (너무 높으면 오신호)
- `avg_score`: 평균 점수
- `high/medium_signals`: 레벨별 분포

### 테스트
- `tests/unit/test_backtest_engine.py` 신규 (12-18개)
- conftest의 `_make_ohlcv(1000, ...)` 활용

### 검증
```bash
pytest tests/unit/test_backtest_engine.py -v
```

---

## Phase 7: 멀티 타임프레임 충돌 처리 (MEDIUM)

현재 primary(4h)만 집계. 가중 합산 + 충돌 감지 추가.

### 수정 파일

**`config/technical.yaml`**:
```yaml
multi_timeframe:
  mode: "weighted"              # "primary_only" | "weighted" | "conflict_detect"
  weights:
    "1h": 0.2
    "4h": 0.5
    "1d": 0.3
  conflict_threshold: 3         # 포인트 차이 N점 이상이면 충돌 경고
```

**`app/analyzers/score_aggregator.py`**:
- `mode: "weighted"` → 모든 TF 가중 합산하여 기술적 점수 산출
- `mode: "conflict_detect"` → primary 사용 + 충돌 시 경고 플래그

**`app/pipeline.py`**:
- weighted 모드: `technical_results` → 가중 합산 기술적 점수 계산
- conflict_detect 모드: TF간 포인트 차이 체크 → `AggregatedResult.details`에 충돌 정보

**`app/notifiers/message_formatter.py`**:
- 충돌 경고: `⚠️ 타임프레임 충돌: 4H(높음) vs 1D(낮음) — 주의 필요`

---

## Phase 8-10: MEDIUM 우선순위 (개요)

### Phase 8: 신호 이력/적중률 추적
- SQLite 기반 `app/storage/signal_repository.py`
- 신호 저장 + 일정 시간 후 실제 가격 대비 적중률 계산

### Phase 9: 데이터 캐싱/거래소 대안
- `app/data/cache.py` — TTL 기반 인메모리 캐시
- `data_collector.py`에 캐시 래핑 + fallback 거래소 설정

### Phase 10: 발송 실패 처리
- `app/notifiers/dead_letter.py` — 실패 메시지 파일 저장

---

## 구현 순서 및 의존성

```
Phase 1 (RSI 파라미터) ← 독립, 가장 안전
    ↓
Phase 2 (강도 점수) ← Phase 1의 divergence_magnitude 사용
    ↓
Phase 3 (횡보 필터) ← Phase 2의 연속 점수 기반 점진적 억제
    ↓
Phase 5 (DCA 계수) ← Phase 2의 연속 점수로 세밀한 매핑

Phase 4 (블랙스완) ← 독립, Phase 2-3과 병렬 가능
Phase 6 (백테스트) ← Phase 2+3 안정화 후 (검증 대상이 안정적이어야 의미)
Phase 7 (멀티TF) ← Phase 2 이후
```

---

## 파일 수정 전체 목록

### 신규 생성 (9개)

| 파일 | 내용 |
|------|------|
| `app/analyzers/indicators/volume_spike.py` | 거래량 스파이크 감지 |
| `app/analyzers/indicators/outlier_detector.py` | 블랙스완 서킷 브레이커 |
| `app/backtest/__init__.py` | 백테스트 패키지 |
| `app/backtest/engine.py` | 슬라이딩 윈도우 리플레이 엔진 |
| `app/backtest/data_loader.py` | 히스토리컬 데이터 로더 |
| `app/backtest/reporter.py` | 백테스트 결과 포맷터 |
| `tests/unit/test_indicators/test_volume_spike.py` | |
| `tests/unit/test_indicators/test_outlier_detector.py` | |
| `tests/unit/test_backtest_engine.py` | |

### 수정 (7개)

| 파일 | 변경 |
|------|------|
| `config/technical.yaml` | intensity, sideways_filter, outlier, dca, volume, multi_timeframe 섹션 추가 |
| `app/analyzers/indicators/rsi.py` | 파라미터 확장 + divergence_magnitude |
| `app/analyzers/indicators/adx.py` | adx_prev 키 추가 |
| `app/analyzers/technical_analyzer.py` | 강도 계산 + 횡보 필터 + outlier 통합 |
| `app/analyzers/score_aggregator.py` | DCA 계수 + 멀티TF 가중 합산 |
| `app/pipeline.py` | 멀티TF 모드 분기 |
| `app/notifiers/message_formatter.py` | 강도/횡보/블랙스완/DCA 표시 |

---

## 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 강도 점수로 기존 테스트 깨짐 | 높음 | `intensity.enabled: false` 안전 스위치 |
| 횡보 필터 과잉 억제 | 실제 전환 신호 놓침 | graduated 모드 + `suppression_factor` 조절 |
| 백테스트 성능 (1000봉 × analyze) | 느림 | `@pytest.mark.slow` + 윈도우 크기 조절 |
| 블랙스완 override 모드 | 잘못된 100점 강제 | `action: "flag"` 기본값 |
| DCA 매핑이 시장 상황 맞지 않음 | 잘못된 투자 가이드 | YAML 설정으로 유연 조절 |

---

## 검증

Phase별 테스트 후 전체 검증:
```bash
pytest tests/ -v --tb=short
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
```
