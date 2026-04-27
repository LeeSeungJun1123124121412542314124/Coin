# PLAN: 시뮬레이터 v2 — 매크로 + TA 신호 기반 가상 트레이딩

**작성일:** 2026-04-19

---

## 목표

현재 지표들(OI, FR, TGA YoY, M2 YoY + 13개 TA 지표)을 배경으로 깔고,
직접 가상 포지션을 잡아 **내일/1주/1달/3달 수익 예측 및 실제 승률 트래킹**을 한다.
승률 60% 미만 시 어떤 지표를 수정해야 하는지 피드백을 받는다.

---

## 핵심 사용 흐름

```
[매크로 패널] OI · FR · TGA YoY · M2 YoY 한눈에 보기
       ↓
[신호 패널] 13개 TA 지표 → 종합 방향 스코어 (롱 bias / 숏 bias / 중립)
       ↓
[포지션 입력] 심볼 · 롱/숏 · 진입가 · 레버리지 · 사이즈
       ↓
[수익 예측] 1일 / 1주 / 1달 / 3달 예상 수익 범위 표시
       ↓
[청산 or 만기] 실제 결과 기록 → 승률 / 지표별 정확도 업데이트
       ↓
[튜닝 피드백] 승률 60% 미만 지표 → 파라미터 조정 안내
```

---

## 기존 코드와의 관계

| 기존 | 처리 |
|---|---|
| 현재 시뮬레이터 탭 (예측 등록/정산) | 유지 — 별도 탭으로 분리 |
| 자동 백테스트 (AutoBacktest.tsx) | 참고 데이터로만 활용 (숨기거나 접기) |
| ta_indicators.py / auto_backtest.py | 신호 엔진으로 재활용 |
| bybit_derivatives.py (OI, FR) | 매크로 패널에 직접 사용 |
| fred.py (TGA, M2) | 매크로 패널에 직접 사용 |
| coin_ohlcv_1h 테이블 | 신호 계산 + 변동성 추정 데이터 소스 |

---

## UI 레이아웃

```
┌─── 시뮬레이터 v2 ──────────────────────────────────────────────┐
│  [코인] [한국주식] [미국주식]                                    │
│                                                                │
│ ┌── 매크로 배경 ────────────────────────────────────────────┐  │
│ │  OI        FR         TGA YoY     M2 YoY                  │  │
│ │  $28.4B   -0.01%     -12.3%      +3.8%                    │  │
│ │  ↑+2.1%  (매수우세)  (긴축)      (완화)                    │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│ ┌── 신호 분석 ──────────────────────────────────────────────┐  │
│ │  심볼: [BTCUSDT ▼]                                         │  │
│ │                                                            │  │
│ │  RSI ████░░  숏    MACD ████░░ 롱   BB  ██░░░  중립        │  │
│ │  MA  ██████  롱    EMA  █████░ 롱   ADX ████░  숏          │  │
│ │  (나머지 7개 지표...)                                       │  │
│ │                                                            │  │
│ │  종합 스코어: ████████░░ +64  →  [롱 우세]                 │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│ ┌── 포지션 입력 ─────────────────────────────────────────────┐ │
│ │  방향: [롱 ●] [숏 ○]   진입가: $75,600   레버리지: [5x ▼]  │ │
│ │  사이즈: [100 USDT]    청산가: $60,480   [포지션 열기]      │ │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│ ┌── 수익 예측 ───────────────────────────────────────────────┐ │
│ │  기간    예상 방향    예상 수익범위    신뢰도               │ │
│ │  내일    ↑ 롱 우세   +0.8% ~ +3.2%   ★★★☆☆              │ │
│ │  1주     ↑ 롱 우세   +2.1% ~ +8.4%   ★★★☆☆              │ │
│ │  1달     → 중립      -5.0% ~ +9.0%   ★★☆☆☆              │ │
│ │  3달     ↑ 롱 우세   +8.0% ~ +25%    ★★☆☆☆              │ │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│ ┌── 활성 포지션 ─────────────────────────────────────────────┐ │
│ │  BTC 롱 5x  진입 $75,600  현재 $76,200  +3.15%  [청산]     │ │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│ ┌── 승률 & 지표 튜닝 ────────────────────────────────────────┐ │
│ │  전체 승률: 58% ⚠️ (목표: 60%)                              │ │
│ │                                                            │ │
│ │  지표별 기여도:                                             │ │
│ │  RSI    72% ✅   MACD   65% ✅   BB    48% ❌ → 조정 필요  │ │
│ │  MA     61% ✅   ADX    55% ⚠️   ATR   45% ❌ → 조정 필요  │ │
│ │                                                            │ │
│ │  💡 BB (볼린저밴드) σ 2.0 → 2.5 로 조정 권장              │ │
│ └───────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 상세 설계

### 1. 매크로 패널

| 지표 | 데이터 소스 | 갱신 주기 | 표시 |
|---|---|---|---|
| OI (미결제약정) | Bybit `/v5/market/open-interest` | 5분 (캐시) | 현재값 + 24h 변화% |
| FR (펀딩비) | Bybit `/v5/market/funding/history` | 1시간 | 현재 FR + 방향(매수우세/매도우세) |
| TGA YoY | FRED `WTREGEN` (이미 수집 중) | 일간 | 전년대비 증감% + 방향(긴축/완화) |
| M2 YoY | FRED `M2SL` (이미 수집 중) | 월간 | 전년대비 증감% + 방향 |

**매크로 종합 방향 해석:**
- OI 상승 + FR 양수 → 레버리지 롱 과열 → 숏 우세 신호
- TGA 감소(긴축 완화) + M2 증가 → 유동성 확대 → 롱 우세 신호

---

### 2. 신호 분석 엔진

**기존 ta_indicators.py 활용** — 실시간 신호로 변환

```python
# 새 함수: 현재 신호 계산 (최근 200봉 기준)
async def get_current_signals(symbol: str) -> SignalSummary:
    """
    각 지표의 현재 신호 상태를 반환.
    returns: {
      "indicators": [{"name": "RSI", "signal": "long|short|neutral", "value": 28.5, "desc": "과매도"}],
      "score": 64,          # -100(all short) ~ +100(all long)
      "bias": "long",       # long|short|neutral
      "confidence": 0.72    # 0~1
    }
    """
```

**스코어 계산:**
- 각 지표 신호: Long=+1, Neutral=0, Short=-1
- 가중 합계 / 총 지표 수 × 100
- |score| < 20 → neutral, 20~60 → weak, 60~80 → strong, 80+ → very strong

---

### 3. 수익 예측 모델

**방법론: 신호 스코어 × 변동성 × 시간 배수**

```
ATR_pct = ATR(14) / current_price × 100  # 가격 대비 변동성 %

time_multiplier:
  1일  → 1.0×
  1주  → 2.5×
  1달  → 5.0×
  3달  → 10.0×

expected_move_pct = signal_score/100 × ATR_pct × time_multiplier

range_pct:
  best  = expected_move_pct × 1.5
  base  = expected_move_pct × 1.0
  worst = expected_move_pct × -0.5  (반대 방향 tail risk)
```

**신뢰도 = |score| / 100 × 0.8 + (matching_macro_signals / 4) × 0.2**

---

### 4. 포지션 기록 스키마

```sql
-- 기존 sim_positions 확장 (컬럼 추가)
ALTER TABLE sim_positions ADD COLUMN signal_score INTEGER;   -- 진입 시 신호 스코어
ALTER TABLE sim_positions ADD COLUMN signal_snapshot TEXT;  -- JSON: 지표별 신호
ALTER TABLE sim_positions ADD COLUMN macro_snapshot TEXT;   -- JSON: OI,FR,TGA,M2
ALTER TABLE sim_positions ADD COLUMN predicted_1d REAL;     -- 예측 수익률
ALTER TABLE sim_positions ADD COLUMN predicted_1w REAL;
ALTER TABLE sim_positions ADD COLUMN predicted_1m REAL;
ALTER TABLE sim_positions ADD COLUMN predicted_3m REAL;
ALTER TABLE sim_positions ADD COLUMN actual_result REAL;    -- 실제 수익률 (청산 시)
```

---

### 5. 지표 튜닝 피드백

**승률 계산:**
- 포지션 방향 vs 실제 가격 방향이 일치 → win
- 각 지표별: 해당 지표 신호와 결과 방향 일치율

**파라미터 조정 제안 규칙:**

| 지표 | 승률 < 50% 시 제안 |
|---|---|
| RSI | 기간 14 → 21 (장기화) 또는 임계값 30/70 → 25/75 |
| MACD | fast 12 → 8 (민감도 ↑) 또는 slow 26 → 34 (노이즈 ↓) |
| 볼린저밴드 | σ 2.0 → 2.5 (신호 필터 강화) |
| 스토캐스틱 | 임계값 20/80 → 15/85 |
| ADX | 강도 기준 25 → 30 (더 강한 추세만 신호) |

---

## 구현 Task 목록

### Task 1: 매크로 패널 API
**파일:** `dashboard/backend/api/sim_routes.py`

```
GET /api/sim/macro-context
Response: {
  "oi": {"value": 28.4e9, "change_24h_pct": 2.1, "signal": "caution"},
  "fr": {"value": -0.0001, "annualized_pct": -0.87, "signal": "short_bias"},
  "tga_yoy": {"pct": -12.3, "signal": "easing"},
  "m2_yoy": {"pct": 3.8, "signal": "expanding"}
}
```

### Task 2: 실시간 신호 분석 API
**파일:** `dashboard/backend/services/signal_analyzer.py` (신규)

```
GET /api/sim/signals?symbol=BTCUSDT
Response: SignalSummary (위 설계 참조)
```

### Task 3: 수익 예측 API
**파일:** `dashboard/backend/services/return_projector.py` (신규)

```
GET /api/sim/projection?symbol=BTCUSDT&direction=long&leverage=5
Response: {
  "horizons": [
    {"period": "1d", "base_pct": 1.2, "best_pct": 3.8, "worst_pct": -0.9, "confidence": 0.68},
    {"period": "1w", ...},
    {"period": "1m", ...},
    {"period": "3m", ...}
  ]
}
```

### Task 4: 포지션 스키마 확장
**파일:** `dashboard/backend/db/schema.sql`

`sim_positions` 테이블에 신호 스냅샷 컬럼 추가 (DB 마이그레이션)

### Task 5: 포지션 진입 API 확장
**파일:** `dashboard/backend/api/sim_routes.py`

기존 포지션 오픈 API에 signal_score, signal_snapshot, macro_snapshot 저장 추가

### Task 6: 승률 & 지표 튜닝 API
**파일:** `dashboard/backend/api/sim_routes.py`

```
GET /api/sim/win-rate-analysis?symbol=BTCUSDT
Response: {
  "overall_win_rate": 0.58,
  "total_trades": 25,
  "indicators": [
    {"name": "RSI", "win_rate": 0.72, "status": "good"},
    {"name": "BB",  "win_rate": 0.48, "status": "poor", "suggestion": "σ 2.0→2.5"},
    ...
  ]
}
```

### Task 7: 프론트엔드 v2 UI
**파일:** `dashboard/frontend/src/components/screens/Simulator.tsx` 개편

- 매크로 패널 (4개 미니 카드)
- 신호 분석 패널 (지표별 롱/숏/중립 + 스코어 게이지)
- 포지션 입력 폼 (기존 + 수익 예측 미리보기)
- 수익 예측 테이블 (1d/1w/1m/3m)
- 활성 포지션 (기존 유지)
- 승률 & 튜닝 피드백 (새 섹션)

---

## 구현 순서

1. Task 1: 매크로 컨텍스트 API (기존 collector 재활용)
2. Task 2: 신호 분석 서비스 (ta_indicators 재활용)
3. Task 3: 수익 예측 서비스
4. Task 4+5: DB 확장 + 포지션 API 업데이트
5. Task 6: 승률 분석 API
6. Task 7: 프론트엔드 전면 개편

---

## Acceptance Criteria

- [ ] OI, FR, TGA YoY, M2 YoY 4개 매크로 지표 실시간 표시
- [ ] 13개 TA 지표 현재 신호 + 종합 스코어 표시
- [ ] 포지션 진입 시 1d/1w/1m/3m 수익 예측 범위 표시
- [ ] 가상 포지션 진입/청산 + 실제 결과 기록
- [ ] 전체 승률 + 지표별 승률 표시
- [ ] 승률 60% 미만 지표에 파라미터 조정 제안
- [ ] 기존 시뮬레이터(예측/정산) 기능 회귀 없음

---

## 제약 / 주의사항

- OI는 Railway에서 Bybit API 접근 차단 이슈 있음 (bybit_derivatives.py 주석 참조) → 캐시 TTL 조정 또는 프록시 필요
- FRED API Key 환경변수 필요 (TGA, M2) — Railway에 이미 설정 여부 확인 필요
- 수익 예측은 **통계적 범위**이며 실제 수익 보장 아님 — UI에 명확히 표시
- 지표 파라미터 조정 제안은 제안일 뿐 자동 적용 안 함 (사용자가 직접 백테스트로 검증)
- 기존 `sim_positions`에 컬럼 추가 시 Railway DB 마이그레이션 필요 (ALTER TABLE)
