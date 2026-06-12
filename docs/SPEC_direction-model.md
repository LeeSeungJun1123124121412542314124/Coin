# 스펙: 변동성 정기 리포트 — 방향 모델 추가

- Seed ID: `seed_6265f88009ed`
- Interview ID: `interview_20260612_160821`
- Ambiguity: 0.107
- 작성일: 2026-06-12
- 출처: ouroboros interview → seed (수동 결정 기록 포함)

## 배경 / 문제

`crypto-volatility-bot`의 변동성 정기 리포트(`periodic_report`)는 시스템 전체가 **변동성 크기만 측정**(direction-agnostic)한다:

- 감성: `abs(50 - fg) * 0.5` — 극단 공포·탐욕이 점수를 동일하게 올림 ([sentiment_analyzer.py:22](../crypto-volatility-bot/app/analyzers/sentiment_analyzer.py))
- MVRV: 극단 고/저평가 부스트 대칭 ([onchain_analyzer.py:62](../crypto-volatility-bot/app/analyzers/onchain_analyzer.py))
- 파생: `abs(oi_chg) > 12%` — OI 급락도 OI_SURGE로 라벨 ([derivatives_analyzer.py:52](../crypto-volatility-bot/app/analyzers/derivatives_analyzer.py))
- 기술: RSI/MACD/BB/ATR — 변동성 크기만, 방향(HA)은 부스터 게이트로만 쓰고 버림

그런데 리포트 라벨은 방향성 단어("매도압력/매집/공포/탐욕/OI급등")를 써서 트레이더가 매수·매도 신호로 오해. 추천 문구는 `alert_level`(기술 변동성 점수)만으로 결정되어 방향 정보가 0 → **"신호·추천이 반대/무의미"**.

## 목표 (GOAL)

`periodic_report`에 **계층 게이트 기반 롱/숏/중립 방향 bias + 0~100 신뢰도**를 산출·표기하는 방향 모델을 추가한다. 기존 변동성 크기 측정과 **분리된 독립 '방향' 섹션**과 **alert_level×방향 9칸 추천 매트릭스**를 제공한다.

## 결합 방식: 계층 게이트 + 보조

### 1차 방향 (기술 게이트)
- HA 방향이 1차 방향 결정: `ha_close > ha_open` → bullish(롱), `<` → bearish(숏) ([heikin_ashi.py:43](../crypto-volatility-bot/app/analyzers/indicators/heikin_ashi.py))
- HMA 크로스 · MACD 크로스는 **별개 확인 시그널**. 둘 다 HA와 반대 방향이면 **중립 강등**.
- HA가 neutral(doji, 사실상 미발생)이면 1차 방향 중립.
- **주의(구현)**: 방향용 HA는 부스터 게이트(`ha_filter.enabled`)와 **무관하게 항상 계산**해야 함. mode(simple/strong/safe)는 `config/technical.yaml`의 `ha_filter` 재사용.
- 타임프레임: pipeline `ohlcv_df` 기본 주기 1개 재사용 (주기별 분리 금지, 4h는 선택적 확인용).

### 신뢰도 (보조 신호 가감) — 상수 모듈로 분리(수동 튜닝 가능)
| 항목 | 값 |
|---|---|
| base | 50 |
| 파생 카테고리 confirm / divergence | +15 / −15 |
| 온체인 flow_ratio confirm / divergence | +15 / −15 |
| MVRV 극단(>3.5 또는 <0.8) 컨트레리언 nudge | ±10 |
| F&G 극단(<25 또는 >75) 컨트레리언 nudge | ±10 |
| clamp | 0 ~ 100 |

**방향(컨트레리언) 매핑**
- 파생: FR < 0 (숏 쏠림) → **롱 레인**, FR > 0 (롱 쏠림) → **숏 레인**.
- 온체인: flow_ratio < 1 (outflow > inflow, 매집) → **롱 레인**, > 1 (유입 우위) → **숏 레인**.
- MVRV 극단: >3.5(과열) → 숏 nudge, <0.8(저평가) → 롱 nudge.
- F&G 극단: <25(극단 공포) → 롱 nudge(약), >75(극단 탐욕) → 숏 nudge(약).
- 보조가 1차 방향과 같은 레인이면 confirm(+), 반대면 divergence(−).
- **OI 증감은 방향 카운팅 제외** (변동성 점수에만 사용, 방향 아님).

**deadband 상수 (무가산 0)** — 별도 상수로 분리, 튜닝 가능
- FR: `|FR| < 0.00005` → 0 가산
- flow_ratio: `0.95 ~ 1.05` → 0 가산
- 데이터 결측(None) → 해당 보조 0 가산으로 통일

### 컷오프
- 신뢰도 < 30 → 1차 방향과 무관하게 **최종 방향 '중립'**으로 강등 표기 + 폴백 문구.

## 리포트 출력 스펙

### 라벨 리라이팅 (오해 유발 → 사실 기반)
- "OI급등" → "OI 3일 +12%"
- "매도압력" → "유입/유출 1.7"
- "매집" → "유입/유출 0.6"
- 방향 해석은 신설 '방향' 섹션이 전담.

### 신설 '방향' 섹션
```
방향: 롱 (신뢰도 65/100)
근거: 파생 confirm · 온체인 divergence
```

### 추천 매트릭스 (alert_level × 방향) — 9칸

| level \ 방향 | 롱 | 숏 | 중립 |
|---|---|---|---|
| **LOW** | 변동성 낮음, 롱 우위(약) | 변동성 낮음, 숏 우위(약) | 변동성 낮음, 관망 |
| **MID** | 변동성 보통, 롱 우위 | 변동성 보통, 숏 우위 | 변동성 보통, 방향 불명확 |
| **HIGH** | 단기 롱 우위, 변동성 확대 주의 | 단기 숏 우위, 변동성 확대 주의 | 변동성 확대 경보, 방향 불명확 — 포지션 축소 권고 |

- 신뢰도 < 30 폴백(방향 무관): LOW="변동성 낮음", MID="변동성 보통", HIGH="변동성 확대 경보".
- MVRV 중간 과열(2.5~3.5) 진입 시 문구 끝에 ` · MVRV 과열 위험` 1줄 부기.

## 검증 (ACCEPTANCE)

1. **백테스트 방향 적중률 ≥ 55%** — 기존 [app/backtest/engine.py](../crypto-volatility-bot/app/backtest/engine.py)의 `correct_direction`/`hit_rate` 인프라 재사용·확장, BTC/USDT 가용 히스토리, 24h(또는 엔진 호라이즌) 방향 부합 비율.
2. **단위테스트 14건** (라인 커버리지 ≥ 90% — 신규 방향 모듈 + message_formatter 방향 섹션):
   - 1차 방향 게이트 4건: HA bullish + 크로스 둘 다 golden→롱 / HA bullish + 둘 다 dead→중립강등 / HA bearish + 혼합→숏 유지 / HA bullish + 한쪽만 dead→롱 유지
   - 신뢰도 가감 4건: 모두 confirm(상한 근처) / 모두 divergence(하한 근처) / MVRV 극단 nudge 단독 / F&G 극단 nudge 단독
   - Deadband 3건: FR |x|<0.00005→0 / flow_ratio 0.95~1.05→0 / 결측(None)→0
   - 컷오프 1건: 신뢰도 28 → 방향 "중립" + 폴백 문구
   - 포매터 2건: 방향 섹션 출력 / 매트릭스 HIGH+숏, LOW+중립 문자열 매칭
3. **샘플 리포트 1~2건 육안 검수**: '방향' 섹션 + 9칸 매트릭스 정상 출력.

## 제약 (CONSTRAINTS)

- Python + pandas + YAML(config/technical.yaml) 스택 유지.
- 수정 범위: `app/analyzers/{derivatives,onchain,sentiment,technical,score_aggregator}.py`, `app/notifiers/message_formatter.py`, `app/notification_dispatcher.py`, `app/backtest/engine.py`, 신규 상수 모듈.
- 가중치·임계값 상수는 별도 상수 모듈로 분리.
- 외과적 변경: 기존 변동성 점수 로직·부스터 게이트에 영향 없이 추가.
- 데이터 결측 시 해당 보조 0 가산으로 통일.

## 영향 받는 파일

| 파일 | 역할 |
|---|---|
| `app/analyzers/technical_analyzer.py` | HA 방향·HMA/MACD 크로스 산출(항상 계산하도록) |
| `app/analyzers/derivatives_analyzer.py` | FR 부호, OI 증감(abs 부호 소실 검토) |
| `app/analyzers/onchain_analyzer.py` | flow_ratio |
| `app/analyzers/sentiment_analyzer.py` | F&G 극단 nudge |
| `app/analyzers/score_aggregator.py` | 방향 bias 결합 로직 추가 |
| `app/notifiers/message_formatter.py` | '방향' 섹션 신설, 라벨 리라이팅, 매트릭스 |
| `app/notification_dispatcher.py` | 추천 문구 결합 |
| `config/technical.yaml` | ha_filter 모드 참조 |
| `app/backtest/engine.py` | 방향 적중률 측정 재사용·확장 |
| (신규) 상수 모듈 | 가중치·deadband·임계값 |

## 평가 원칙 (가중치)

- 방향적중률 0.30 · 해석가능성 0.20 · 라벨중립성 0.15 · 튜닝가능성 0.15 · 외과적변경 0.10 · 결측견고성 0.10
