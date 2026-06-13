# 스펙: 지표 리더보드 — 포워드 모의투자 엔진

작성일: 2026-06-13
상태: **구현 완료** (Phase 1~5, feature/paper-leaderboard). 빌드 중 확정한 2가지 변경은 아래 "구현 변경점" 참조.
관련: 기존 수동예측 시뮬레이터 대체. [RESEARCH_direction-signals.md](RESEARCH_direction-signals.md)의 9팩터·생존 신호 재사용.

## 구현 변경점 (스펙 대비)

1. **도미넌스 데이터**: CoinGecko `/global`(현재값만, 과거 시계열 무료 불가) 대신 **BTC vs 알트(ETH/SOL) 30일 상대강도 프록시**로 자급 — 이미 수집하는 OHLCV만 사용, 추가 수집원 0. BTC 우위→BTC 롱·알트 숏 로테이션으로 의미 동일.
2. **수동예측 제거 → 비활성 보존**: 회사 Railway 배포 기능 삭제 리스크를 피해 프론트 `SHOW_MANUAL_PREDICTION=false` 플래그로 **UI만 숨김**. 백엔드 엔드포인트·테이블·정산잡·프론트 코드는 전부 보존(플래그 true로 재활성).
3. 구현 위치: 지표 레지스트리/수집 확장은 `crypto-volatility-bot/app/macro/`(signals.py·collectors.py), 엔진/집계/잡/API는 dashboard. (스펙의 `indicator_registry.py`는 `app/macro/signals.py`로 구현)

## 목표 (GOAL)

가상 시드를 넣고, **우리가 가진 각 지표가 자기 신호대로 실시간 자동 매매**하게 해서, **수익률 리더보드**로 "어느 지표가 실제로 돈이 되나"를 **전진(forward, OOS)** 검증한다. 과거 백테스트(과최적화 위험)와 달리, 미래 미관측 데이터로 지표의 실전 쓸모를 증명한다.

## 핵심 개념

- **지표 = 전략**: 각 지표가 동일 시드($10,000 기본)로 독립 가상 포트폴리오를 운용.
- **리더보드**: 지표별 총수익·승률·MDD·Sharpe·vs 매수보유(buy&hold) 비교.
- **포워드**: 매일 1회 신호 재평가 + 실시간 시세 마크투마켓. (과거 재생 아님)
- **확장형 지표 레지스트리**: 지표 추가 = 신호 함수 1개 + 등록 1줄.

## 삭제 범위 (기존 수동예측 시뮬레이터)

- 프론트: `Simulator.tsx`의 수동 예측 폼(direction/target_price/portfolio 입력 모드) 제거 → 리더보드 화면으로 교체
- 백엔드: `POST/GET/DELETE /sim/predictions`, `GET /sim/scorecard*`, `GET /sim/positions/{id}`, `GET /sim/projection` 등 수동예측 전용 엔드포인트
- 잡: `jobs/settle_predictions.py` (수동 예측 정산)
- 테이블: `sim_predictions`, `sim_settlements` (수동분) — 기존 데이터 폐기
- ⚠️ 회사 배포(Railway) 기능 제거 — 삭제 직전 정확한 목록 재확인 후 진행

## 재사용 (삭제 안 함)

- `sim_engine.py` — 청산가·SL/TP·청산 판정 (숏·레버리지에 필요, 그대로 재사용)
- `composite_backtest.py` — **수수료·펀딩 상수만 차용** (PnL 계산은 paper_engine 자체 구현 — §구현 디테일 #5)
- `sim_accounts` 테이블 — 지표별 포트폴리오 자본 관리로 변형
- 과거 백테스트 탭(composite/auto/tuning) — 보조 도구로 유지

## 확장형 지표 레지스트리

`direction_composite.FACTORS` 패턴 확장. 각 지표 = 일봉 정렬 데이터 → 자산별 방향 신호(z-score 또는 -1~+1).

```python
# dashboard/backend/services/indicator_registry.py (신규)
INDICATORS: dict[str, IndicatorFn] = {
    "복합방향":   composite_signal,    # 9팩터
    "순유동성":   netliq_signal,
    "달러":       dxy_signal,
    "금리":       ust10y_signal,
    "VIX":        vix_signal,
    "MVRV":       mvrv_signal,
    "RSI":        rsi_signal,          # 자산별
    "모멘텀30d":  momentum_signal,     # 자산별
    "도미넌스":   dominance_signal,    # BTC.D 로테이션 (별도 지표)
    "매수보유":   buyhold_signal,      # 벤치마크 (항상 롱)
    # 새 지표 추가 = 함수 1개 작성 + 여기 1줄 등록
}
```
`asset`를 쓰는지 여부로 매크로(공통)/기술(자산별)이 자연 구분됨:
```python
def netliq_signal(asset, date):  return _market_zscore("net_liquidity_13w", date)  # asset 무시
def rsi_signal(asset, date):     return _asset_rsi_z(asset, date)                   # asset별
```
`IndicatorFn(asset, asof_date) -> float`: 해당 시점 신호값(부호=방향, 크기=신뢰도). 데이터 소스는 기존 `app/macro` 수집기 + OHLCV 재사용.

## 신호의 자산별 적용 (확정 — 옵션 A)

`IndicatorFn(asset, asof_date) -> float` 하나로 통일. 자산별 처리는 함수가 결정:
- **매크로/온체인 지표** (순유동성·달러·금리·VIX·MVRV): `asset` 무시, **시장 방향 하나를 BTC/ETH/SOL 공통 적용** (크립토 상관 0.8+).
- **기술 지표** (RSI·모멘텀·SMA): `asset`별로 그 코인 OHLCV로 계산.
- **BTC 도미넌스(BTC.D)**: **별도 지표**로 추가 — 도미넌스 추세 기반 BTC↔알트 로테이션 전략(도미넌스↑ → BTC 비중↑/알트↓, ↓ → 알트↑). 데이터: CoinGecko 등 1개 수집기 추가.

이유: 각 지표 순수성 유지 → 리더보드 귀속 명확("매크로가 쓸모있나" vs "도미넌스가 쓸모있나" 분리 측정). 도미넌스 로테이션을 무시한 "매크로 공통 적용"이 알트 구간에 손해 보는지도 리더보드로 드러남. (필요시 후속 단계에서 도미넌스 오버레이 도입 판단)

## 전략 규칙 (신호 → 포지션)

- 신호 z-score → **부호로 롱/숏**, **|z|로 사이즈·레버리지**(캡 3배 기본).
  - 예: z>+0.5 강한 롱(레버리지↑), 0~+0.5 약한 롱, ~0 현금, 음수 숏.
- 자산 BTC/ETH/SOL **균등 분산** (지표가 3코인 각각에 신호 적용).
- **매일 리밸런스**: 신호 재평가 → 목표 포지션과 차이만 조정. 신호 flip 시 청산·반대 진입.
- SL/TP·강제청산: `sim_engine` 규칙 적용.
- 수수료·펀딩: `composite_backtest` 로직 재사용.

## 구현 디테일 확정 (#1~6 — 빌드 시 추가 결정 불필요)

### 신호 표준화 (z-score) — #2
모든 신호 = **causal 확장창 z-score** (`min_periods=250`, 미래정보 배제 — 포워드 검증 필수).
- 매크로: 팩터값의 z (research와 동일 방식) · 기술: 자산별 지표값(RSI 등)의 z
- 부호=방향, 크기=강도

### 사이징·레버리지 공식 (자산별) — #1
상수: `DEADBAND_Z=0.2`, `Z_FULL=1.0`, `LEV_CAP=3.0`, `N_ASSETS=3` (전부 config)
- `|z| < 0.2` → **현금**(포지션 0)
- 그 외 → `lev = min(|z| / Z_FULL, 1.0) × LEV_CAP` (z=0.5 → 1.5배, z≥1.0 → 3배)
- `목표명목 = sign(z) × lev × (capital / N_ASSETS)`
- **매수보유**: 예외 — 항상 +1배 롱(deadband·레버리지 무시), 벤치마크
- **도미넌스**: `d_z = z(BTC.D 13주변화)` → BTC는 `+d_z`, ETH/SOL은 `−d_z` (도미넌스↑ → BTC 롱·알트 숏)

### 리밸런스 (일 1회, UTC 00:05) — #3
자산별로 목표명목 계산 후 현재 포지션과 비교:
- 방향 flip 또는 목표=현금 → 현재 청산(PnL 실현 + 수수료), 새 포지션 진입
- 동일 방향 크기변동 → **델타만 매매** (수수료 `FEE × |Δ명목|`)
- 펀딩 `FUNDING × |보유명목|` 매일 차감(futures)
- 청산/SL/TP: 일봉 고저가가 청산가 돌파 시 `sim_engine` 규칙으로 청산

### PnL·청산 (재사용 정정) — #5
- **청산가·SL/TP·청산 판정** → `sim_engine` 재사용 (깨끗한 서비스라 그대로)
- **PnL·수수료·펀딩 계산** → `paper_engine`이 직접 구현 (단순 수식, `settle_predictions._calc_pnl` 패턴 차용). 수수료/펀딩 상수만 `composite_backtest` 값 사용
- (1375줄 composite_backtest 내부 추출 대신 sim_engine + 자체 PnL이 결합도 낮고 깔끔)
- 상수: `FEE_RATE=0.0005`(0.05% taker), `FUNDING_RATE=0.0001/일` (config, composite_backtest와 정합)

### 승률 정의 — #4
**실현 거래 기준**: 청산된 포지션(flip·flat·청산·SL/TP) 중 `PnL>0` 비율. (일별 아님)
MDD·Sharpe는 일별 에쿼티 곡선에서 산출.

### 데이터 수집 확장 (`app/macro/collectors`) — #6
- **ETH/SOL 일봉** 추가 (Binance klines, BTC와 동일 방식)
- **BTC.D 도미넌스**: CoinGecko `/global` → `data.market_cap_percentage.btc` (일 1회)
- 기존 소스 캐시에 병합 (`fetch_sources` 확장)

## 데이터 모델 (신규 테이블)

```sql
-- 지표별 포트폴리오 (시드·현재 자본)
paper_portfolios(id, indicator, seed, capital, leverage_cap, created_at, updated_at)
-- 현재/과거 포지션
paper_positions(id, portfolio_id, asset, direction, qty, entry_price, leverage,
                liq_price, opened_at, closed_at, exit_price, pnl, status)
-- 일별 에쿼티 스냅샷 (리더보드·곡선용)
paper_equity(portfolio_id, date, equity, return_pct)
```

## 설정 (config — 조정 가능)

- 시드: $10,000 / 포트폴리오
- 레버리지 캡: 3배
- 자산: BTC, ETH, SOL (균등)
- 리밸런스: 일 1회 (UTC 00:00 등)
- 수수료/펀딩: composite_backtest 기본값

## API (신규)

| 엔드포인트 | 용도 |
|---|---|
| `GET /sim/leaderboard` | 지표별 수익률·승률·MDD·Sharpe·vs매수보유 순위 |
| `GET /sim/leaderboard/{indicator}` | 특정 지표 에쿼티 곡선·포지션 이력 |
| `POST /sim/leaderboard/reset` | 시드 리셋(전체/지표별) |

## 산출 (리더보드 지표)

지표별: 총수익률, 승률(청산 포지션 중 +PnL 비율), 최대낙폭(MDD), Sharpe, vs 매수보유 초과수익, 현재 포지션. 에쿼티 곡선 차트.

## 실행 (스케줄)

- 일일 리밸런스 잡: 각 지표 신호 재평가 → 포지션 조정 → 에쿼티 스냅샷 저장. (기존 APScheduler에 등록, 봇 파이프라인과 동일 패턴)
- 실시간 마크투마켓: 리더보드 조회 시 현재가로 미실현 PnL 계산.

## 검증 (ACCEPTANCE)

- 단위테스트: 신호→포지션 매핑, PnL·청산 계산(sim_engine 재사용분), 리더보드 집계
- 통합: 시드 → 1일 리밸런스 → 에쿼티 갱신 시나리오
- 매수보유 벤치마크가 리더보드에 항상 포함 (기준선)
- 신규 지표 1개 추가가 함수+등록 1줄로 동작 (확장성 검증)

## 구현 단계 (완료)

1. ✅ **데이터 확장 + 지표 레지스트리** (collectors ETH/SOL·signals.py 10지표) + 테스트 7
2. ✅ **포트폴리오 엔진**: 신호→포지션·PnL·VWAP정산·청산, paper_* 테이블, 리밸런스 잡(UTC 00:05) + 테스트 11
3. ✅ **리더보드 API** + 집계(총수익·승률·MDD·Sharpe·vs매수보유) + 테스트 4
4. ✅ **프론트 리더보드 UI** (Leaderboard.tsx + Simulator 뷰 토글)
5. ✅ **수동예측 비활성 보존** (삭제 대신 플래그 숨김)

## 영향 파일

| 파일 | 작업 |
|---|---|
| `dashboard/frontend/src/components/screens/Simulator.tsx` | 수동폼 제거 → 리더보드 UI |
| `dashboard/backend/api/sim_routes.py` | 수동예측 엔드포인트 제거 + 리더보드 추가 |
| `dashboard/backend/services/indicator_registry.py` | 신규 (확장형 지표) |
| `dashboard/backend/services/paper_engine.py` | 신규 (포트폴리오·리밸런스) |
| `dashboard/backend/jobs/settle_predictions.py` | 삭제 또는 리밸런스 잡으로 대체 |
| `dashboard/backend/services/{sim_engine,composite_backtest}.py` | 재사용(수정 최소) |
| `dashboard/backend/db/connection.py` | paper_* 테이블 추가, sim_predictions 제거 |
