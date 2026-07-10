# 계획: SPF 2·3단계 통합 — 팩터 재가중(3단계) + 확률 보정(2단계)

작성일: 2026-07-05
관련: [SPEC_spf-composite.md](../SPEC_spf-composite.md), [SPEC_spf-upgrade-phase1.md](../SPEC_spf-upgrade-phase1.md), [project_leaderboard_feedback_next]
상태: **0단계 완료 (2026-07-11) — 3단계는 리더보드 4~6주 대기 (현재 ~4주차)**

> **0단계 완료 기록 (2026-07-11)**
> - Avast 우회 불필요해짐 — FRED·CoinMetrics·Binance 전부 로컬 Python TLS 통과 확인 (PowerShell SChannel 경로 미사용, 기존 MACRO_CA_BUNDLE 장치는 유지)
> - 산출물: `crypto-volatility-bot/scripts/composite_history.py` (수집→CSV→베이스라인, `--from-csv` 오프라인 재계산 지원) + `app/macro/backtest_baseline.py` (3단계 전후 비교·2단계 보정이 재사용할 순수 계산부) + `crypto-volatility-bot/data/composite_{sources,history}.csv`, `composite_baseline.json`
> - 동등가중 베이스라인 (2017-12~2026-07, 3,143일 / composite 유효 2,880일):
>   | H | 방향적중 | 기준상승률 | IC |
>   |---|---|---|---|
>   | 7 | 56.5% | 52.9% | 0.136 |
>   | 14 | 58.6% | 54.0% | 0.194 |
>   | 30 | 61.4% | 54.5% | 0.266 |
>   | 60 | 64.5% | 54.4% | 0.306 |
> - 정합성: IC30 0.266 ≈ 연구 문서(RESEARCH_direction-signals.md) IC30 0.272 — 파이프라인 재현 검증됨

## 왜 2·3을 묶는가 / 순서

둘 다 같은 재료(백테스트 + 리더보드 실측)를 쓰지만 **3단계를 먼저** 해야 한다:

- **3단계(재가중)**: 리더보드 실측 성적으로 복합 9팩터의 **가중치를 조정**
- **2단계(보정)**: 그 확정된 모델의 z-score를 **경험적 적중률로 매핑**
- ⚠️ **순서 고정**: 2단계를 먼저 하면 3단계에서 가중치가 바뀌며 보정 곡선이 전부 무효화됨 → **3단계로 모델 확정 → 2단계 보정**

현재 모델: 9팩터 **동등가중**(`direction_composite.compute_composite`, bullish 부호정렬 causal z의 단순 평균). 3단계는 이 "동등가중"에 팩터별 가중치를 도입하는 것.

## 선행 작업 (0단계) — 데이터 무관, 지금 가능

**8년 백테스트 파이프라인 정비**
- 기존 자산: `crypto-volatility-bot/scripts/backtest_real_data.py`, `tga_calibration.py`(오프라인 계산 선례)
- 매크로 소스(FRED 등)가 로컬 Python(httpx)에서 [[reference_avast_tls_interception]]로 막힘 → **PowerShell SChannel 수집 후 CSV 오프라인 계산** 방식(tga_calibration.py 선례) 재사용
- 산출물: 2018~2026 일봉 + 9팩터 시계열 CSV (재현 가능하게 저장)
- 이건 3단계·2단계 공통 기반이라 **데이터 대기 없이 지금 구성 가능**

## 3단계 — 팩터 재가중 (데이터 전제: 리더보드 4~6주)

### 전제
- 리더보드 실측이 4~6주 쌓여야 각 지표(팩터 대응)의 forward 수익성이 유의미 (현재 ~3주차, 2026-07 중하순 예상)
- 리더보드 지표 ↔ 복합 팩터 대응: 순유동성·달러·금리·VIX·MVRV 등이 팩터와 1:1 근접

### 작업
1. 리더보드 실측(총수익·Sharpe·승률)으로 팩터별 가중치 산출
   - 방식 후보: (a) Sharpe 비례 가중 (b) 승률 임계 이상만 채택 (c) 릿지 회귀 — **소표본 과적합 주의, 단순 방식 우선**
2. `FACTORS`를 `(name, category, sign, weight)`로 확장하거나 별도 weight dict 도입, `compute_composite`를 가중평균으로
3. **재가중 전후 백테스트 적중률 비교** — 동등가중 대비 개선 없으면 채택 안 함(가드)
4. 재가중은 실측 검증을 리셋하므로 **버전 태깅** + 전환 시점 기록

### AC
- 재가중 모델의 백테스트 7/14/30/60 적중률이 동등가중 이상
- 가중치 산출 근거(리더보드 실측 스냅샷) 문서화
- 소표본 과적합 방지 장치(최소 표본 수·정규화) 명시

## 2단계 — 확률 보정 (3단계 확정 후)

### 문제
현재 confidence·up_prob는 |z| 휴리스틱 → "신뢰도 35%"에 경험적 근거 없음

### 작업
1. **재가중 확정 모델**로 8년 백테스트 → (composite_z 구간, 실제 방향 적중) 페어 수집
2. z 구간별(또는 isotonic/logistic) **경험적 적중률 곡선** 산출 → 모듈 상수/테이블
3. `composite_prediction`의 confidence·up_prob를 이 보정 테이블로 매핑
4. 화면 "상승 X%"가 과거 통계상 실제 X% 적중 구간을 의미하게 됨

### AC
- 보정 테이블이 백테스트 데이터에서 산출됨(재현 스크립트 포함)
- 보정 후 confidence가 실제 적중률과 정합(reliability diagram 개선)
- 중립 confidence 낮음 유지(기존 버그 회귀 없음)

## 제약

- 한국어 주석 · 외과적 변경 · TDD · 새 의존성 금지(가능하면) · app.macro 재사용
- 재가중/보정은 실측 검증을 리셋 → **버전·전환시점 명시적 기록**
- 소표본 과적합 최우선 경계 (3주 소표본에 맞추지 말 것 — 4~6주 대기 이유)

## 실행 타임라인

| 시점 | 작업 |
|---|---|
| 지금 | 0단계 — 백테스트 파이프라인(Avast 우회 CSV) 구성 |
| 7월 중하순 (리더보드 4~6주) | 3단계 — 재가중 + 전후 백테스트 비교 |
| 3단계 직후 | 2단계 — 확정 모델로 보정 곡선 산출 → confidence 교체 |

## 우선순위 메모

- 임팩트: **3단계(예측력) > 2단계(신뢰도 정직성)**. 2단계는 방향을 더 맞히는 게 아니라 확률 숫자를 정직하게 만드는 것
- 전체 우선순위: APP_SECRET(보안) > 0단계(지금 가능) > 3단계(7월 중하순) > 2단계
