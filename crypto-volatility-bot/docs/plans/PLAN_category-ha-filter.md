# Implementation Plan: Pine Script 기반 카테고리 + HA 필터 오탐률 개선

**Status**: ✅ Complete
**Started**: 2026-02-21
**Last Updated**: 2026-02-21

---

## 📋 Overview

### Feature Description
Pine Script 원본의 **추세 신호 + HA 필터** 구조를 코드에 반영하여 오탐률을 개선.
기존 flat booster 합산 방식을 **카테고리 기반 + HA 필터 게이트** 구조로 전환.

### Success Criteria
- [x] HA 필터 게이트 구현 (safe mode: 2연속 HA 캔들 확인)
- [x] 카테고리 기반 신호 분류 (Trend/Momentum/Volatility)
- [x] 카테고리 게이트 구현 (Trend|Momentum ≥1 AND Volatility ≥1)
- [x] 신규 부스터 4개 구현 (hull_ma_crossover, adx_di_crossover, rsi_trend_crossover, hull_rsi_crossover)
- [x] 강화 부스터 4개 (bb_expansion, volume_spike_strong, atr_spike, outlier)
- [x] 2개 부스터 비활성화 (stochrsi_extreme, bb_middle_break)
- [x] 기존 214개 + 신규 18개 = 232개 테스트 전체 통과

---

## 🏗️ Architecture Decisions

| Decision | Rationale | Trade-offs |
|----------|-----------|------------|
| HA safe mode (2연속 캔들) | Pine Script 원본 일치, 횡보장 필터링 | 약간의 신호 지연 |
| 카테고리 게이트 (AND 조건) | 단일 카테고리 신호만으로는 신뢰도 부족 | 신호 수 대폭 감소 |
| `category_gate.enabled` config | 테스트 격리 + 향후 A/B 테스트 가능 | 설정 복잡도 증가 |
| bandwidth ratio ≥1.3 (bb_expansion) | 단순 expanding보다 정밀한 필터 | 일부 약한 확장 미감지 |
| critical_only (outlier) | half-boost 제거로 오탐 감소 | 경미한 이상치 무시 |

---

## 📦 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `config/technical.yaml` | 카테고리 태그, ha_filter, category_gate, 신규 4개 부스터, 2개 비활성화, 임계값 강화 |
| `app/analyzers/technical_analyzer.py` | HA 게이트, 카테고리 분류/게이트, Hull MA/RSI Trend/Hull RSI/ADX DI 크로스 계산, 강화 부스터 로직 |
| `tests/unit/test_technical_analyzer.py` | HA 게이트 4개, 카테고리 게이트 4개, 신규 부스터 4개, 강화 부스터 4개, 상세보고 2개 테스트 추가 |

---

## 🧪 Test Results

- **Total tests**: 232 passed (was 214, +18 new)
- **Lint**: ruff check passed
- **Type check**: mypy — no new errors (pre-existing yaml stubs warning only)

### 신규 테스트 목록
- `TestHAFilterGate` (4 tests): 횡보 차단, bullish/bearish 통과, disabled config
- `TestCategoryGate` (4 tests): momentum-only 차단, volatility-only 차단, 복합 통과, hits 리포트
- `TestNewBoosters` (4 tests): hull_ma_crossover, adx_di_crossover, rsi_trend_crossover, hull_rsi_crossover
- `TestEnhancedBoosters` (4 tests): volume threshold 강화, outlier critical_only, stochrsi/bb_middle 비활성화
- `TestSignalBoostDetails` (2 tests): ha_filter/ha_direction 필드 존재

---

## 📝 Notes

### Pine Script → 코드 매핑 완료
| Pine Script | 코드 구현 |
|---|---|
| `MHULL/SHULL` crossover | `hull_ma.hma(close, 30)` / `hma(close, 10)` 크로스 |
| `stochK × hullrsi1` | `stoch_rsi.calculate(hull_rsi_value=...)` 전달 |
| `frsi/srsi` RSI Trend Line | `hma(rsi_series, 10)` / `hma(rsi28_series, 10)` 크로스 |
| HA 필터 (safe mode) | `heikin_ashi.calculate(mode="safe")` → filter gate |
| ADX DI crossover | `adx.calculate()["di_crossover"]` 연결 |

### 검증 대기
- `python scripts/backtest_real_data.py` 실행하여 실데이터 오탐률 확인 필요
- 목표: 탐지율 ≥80%, 오탐률 <40%, 신호 수 20~30개
