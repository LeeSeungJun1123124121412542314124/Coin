# 봇 알림 업그레이드 계획서
## 대시보드 데이터 통합 — 백테스트 기반 설계

**작성일**: 2026-04-08  
**기반 데이터**: BTC/USDT 1년 (2025-04-08 ~ 2026-04-08, 8,556 평가 포인트)

---

## 1. 백테스트 결과 요약

### 현재 시스템 성능

| 시그널 | 건수 | 정밀도 | 오탐률 |
|--------|------|--------|--------|
| HIGH   | 62건 | 77.4%  | 22.6%  |
| MEDIUM | 28건 | 39.3%  | **60.7%** |
| 합계   | 90건 | 65.6%  | 34.4%  |

- **Recall**: 3.9% (연간 1,532건 실제 변동 이벤트 중 59건 감지)
- **기준선**: 전체 캔들의 17.9%가 4h 내 1.5% 이상 변동

> Recall이 낮은 것은 설계 의도: 봇은 모든 변동이 아닌 **극단적 이벤트**만 알림

### 파생상품 데이터 단독 성능

| 지표 | 건수 | 정밀도 | 비고 |
|------|------|--------|------|
| OI 3일 급등(>12%) | 408건 | 25.7% | 기준선(17.9%) 대비 +7.8%p |
| FR 음수(숏쏠림) | 2,004건 | 21.3% | 기준선 대비 +3.4%p |
| FR 극단(>75%ile) | 2,136건 | 12.9% | 기준선 **하회** (노이즈) |
| OI급등 + FR극단 | 312건 | 17.9% | 기준선과 동일 |

> **결론**: 파생상품 데이터 단독으로는 알파 낮음. **기술적 분석과 조합**할 때 효과 극대화

### 기술적 + 파생상품 조합 성능

| 조합 | 건수 | 정밀도 | 현재 대비 |
|------|------|--------|-----------|
| HIGH + OI 급등 | 13건 | **92.3%** | +14.9%p |
| HIGH + FR 음수 | 21건 | **81.0%** | +3.6%p |
| HIGH + (OI급등 OR FR음수) | 28건 | **85.7%** | +8.3%p |
| HIGH 단독 (파생상품 없음) | 34건 | 70.6%  | -6.8%p |
| MEDIUM + OI 급등 | 5건 | 80.0%  | +40.7%p |

### 점수 임계값별 정밀도

| score 기준 | 건수 | 정밀도 |
|------------|------|--------|
| >= 72 (현재 HIGH) | 170건 | 45.9% |
| >= 80 | 72건 | 62.5% |
| >= 85 | 36건 | **75.0%** |
| >= 90 | 23건 | 78.3% |

> **현재 HIGH 임계값 72는 낮음** — score >= 85로 올리면 오탐 대폭 감소

---

## 2. 핵심 발견 및 문제점

### 문제 1: HIGH 임계값이 너무 낮음
- 현재: score >= 72 → 정밀도 77.4%, 170건 발동 가능
- 권고: score >= 85 → 정밀도 75%, 36건 (알림 과다 방지)
- HIGH는 진짜 긴급 상황만 발동해야 함

### 문제 2: MEDIUM 시그널이 노이즈 수준
- 현재 MEDIUM: 오탐률 60.7% (10건 중 6건이 오탐)
- 독립 알림으로 발송하기엔 신뢰도 부족
- 리포트에 포함하되 별도 알림 비권고

### 문제 3: 고래 감지가 하드코딩
- `dormant_whale_activated = False` (항상 False, 실제 미감지)
- Hyperliquid 실시간 고래 포지션 데이터 미활용

### 문제 4: 파생상품 데이터 미사용
- OI/FR이 이미 대시보드에서 수집 중이나 봇 파이프라인과 미연결
- OI 급등 + HIGH 시그널 조합이 가장 신뢰도 높은 패턴

---

## 3. 업그레이드 설계

### 3-1. 임계값 조정 (technical.yaml)

```yaml
# 현재 → 권고
signals:
  high_threshold: 72 → 85   # HIGH: 정밀도 45%→75%, 건수 감소
  medium_threshold: 58 → 65  # MEDIUM 노이즈 감소
  max_boost: 35              # 유지
```

### 3-2. 파생상품 분석기 신설 (derivatives_analyzer.py)

```python
class DerivativesAnalyzer:
    """OI + FR 기반 파생상품 위험도 분석."""
    
    def analyze(self, oi_3d_chg: float, fr: float) -> AnalysisResult:
        # OI 급등 + 기술적 HIGH = CONFIRMED HIGH
        # FR 음수 + 기술적 HIGH = SHORT_SQUEEZE_RISK
        # OI 급등 + FR 극단 = LIQUIDATION_RISK (단독)
```

**분류 규칙:**

| 조건 | 신호 | 점수 |
|------|------|------|
| OI 3일 > 15% | OI_SURGE | +20 |
| FR < 0 | SHORT_CROWDED | +15 |
| FR > 75th percentile | LONG_CROWDED | +10 |
| OI > 15% AND FR 극단 | LIQUIDATION_RISK | +30 |

### 3-3. 고래 분석기 연결 (whale_analyzer.py)

Hyperliquid 포지션 컨센서스 활용:
- 롱 비율 변화 >= 20%p → `WHALE_FLIP_BEARISH`
- 숏 비율 변화 >= 20%p → `WHALE_FLIP_BULLISH`  
- 이미 `dashboard/backend/collectors/hyperliquid.py`에 수집 로직 존재

### 3-4. 알림 분류 체계 (4단계)

```
CONFIRMED_HIGH  = 기술적 score >= 85 + OI 급등 OR FR 음수
                  → 즉시 알림 (가장 강력, 92.3% 정밀도)

HIGH_ALERT      = 기술적 score >= 85 단독
                  → 알림 (75% 정밀도)

MEDIUM_WATCH    = 기술적 score 65-85 + OI/FR 확인
                  → 12h 리포트에 포함 (알림 X)

LIQUIDATION_RISK = 기술적 LOW + OI 급등 + FR 극단 동시
                   → 별도 경보 유형으로 신설 (현재 미감지 이벤트)
```

### 3-5. 메시지 포맷 업그레이드

**긴급 확인 알림 (CONFIRMED_HIGH):**
```
🚨 HIGH 변동성 확인
BTC/USDT | 점수: 89.2 | 2026-04-08 14:00 UTC

[기술적] score=89.2 | RSI극단 + BB확장 + MTF확인
[파생상품] OI 3일 +18.4% | FR -0.012% (숏쏠림)
[고래] 롱→숏 전환 감지 (James Wynn)

정밀도 92% 이상 확인 신호. 포지션 점검 권고.
```

**정기 리포트 (12시간):**
```
📊 BTC/USDT 변동성 리포트 | 2026-04-08 12:05 UTC

종합: 42.3 (LOW)

[기술적] 38.5 (LOW) — RSI 52 | BB%B 0.45
[파생상품] OI 3일 +3.2% | FR 0.000038
[고래] 롱 60% / 숏 30%
[감성] FGI 22 (EXTREME_FEAR) | VIX 28.5

💡 시장 안정. 주요 지표 이상 없음.
```

---

## 4. 구현 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `crypto-volatility-bot/config/technical.yaml` | HIGH 임계값 72→85, MEDIUM 58→65 |
| `crypto-volatility-bot/app/analyzers/derivatives_analyzer.py` | 신규: OI/FR 분석기 |
| `crypto-volatility-bot/app/analyzers/whale_analyzer.py` | 신규: 고래 컨센서스 분석기 |
| `crypto-volatility-bot/app/analyzers/score_aggregator.py` | 파생상품/고래 점수 통합 |
| `crypto-volatility-bot/app/pipeline.py` | OI/FR/고래 데이터 수집 추가 |
| `crypto-volatility-bot/app/data/data_collector.py` | OI/FR 수집 메서드 추가 |
| `crypto-volatility-bot/app/notifiers/message_formatter.py` | 새 메시지 포맷 4종 |
| `crypto-volatility-bot/app/notification_dispatcher.py` | CONFIRMED_HIGH, LIQUIDATION_RISK 분기 |
| `dashboard/backend/main.py` | 고래 컨센서스 데이터 봇에 전달 |

---

## 5. 예상 개선 효과

| 지표 | 현재 | 업그레이드 후 | 개선 |
|------|------|--------------|------|
| HIGH 정밀도 | 77.4% | **92.3%** | +14.9%p |
| HIGH 오탐률 | 22.6% | **7.7%** | -14.9%p |
| MEDIUM 오탐률 | 60.7% | 알림 폐지 | 노이즈 제거 |
| 신규 시그널 | 0종 | **4종** | 추가 |
| 고래 감지 | 더미 | **실데이터** | 대체 |

---

## 6. 구현 우선순위

**Phase 1 (즉시 효과, 코드 변경 최소):**
1. `technical.yaml` HIGH 임계값 72 → 85 (1줄 수정)
2. `technical.yaml` MEDIUM 임계값 58 → 65
3. MEDIUM 단독 알림 비활성화

**Phase 2 (파생상품 통합):**
4. `data_collector.py` OI/FR 수집 메서드
5. `derivatives_analyzer.py` 신규 작성
6. `pipeline.py` 파생상품 분석 연결
7. `notification_dispatcher.py` CONFIRMED_HIGH 분기

**Phase 3 (고래 통합):**
8. `whale_analyzer.py` Hyperliquid 컨센서스 분석
9. 메시지 포맷 업그레이드

---

## 7. 백테스트 데이터 위치

```
backtest/
  data/
    btc_1h.csv         — 1h OHLCV 8,760건 (2025-04-08 ~ 2026-04-08)
    btc_4h.csv         — 4h OHLCV 2,190건
    btc_oi_daily.csv   — OI 일별 365건
    btc_fr_8h.csv      — FR 8시간 1,095건
  results/
    backtest_raw.csv   — 8,556 포인트 전체 시그널 + 결과
    metrics.csv        — 시스템별 성능 지표
    monthly_breakdown.csv — 월별 시그널 현황
  fetch_data.py        — 데이터 수집 스크립트
  run_backtest.py      — 백테스트 실행 스크립트
```
