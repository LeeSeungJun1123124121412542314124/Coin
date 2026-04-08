# 코드 리뷰 메모

작성일: 2026-04-08

## 요약

현재 코드에서 가장 위험한 문제는 다음 네 가지입니다.

1. `research_analyzer`에서 `calc_bullish_score()`를 잘못된 인자 순서로 호출해 파생상품 리서치 점수가 왜곡됨
2. CVD 스크리너가 모든 심볼에 BTC 기준 OI 변화율을 재사용해 심볼별 점수가 오염됨
3. 스케줄러에 존재하지 않는 `NotificationDispatcher` 메서드를 등록해 런타임 예외 가능성이 있음
4. 리서치 레이어가 분석 결과의 `details` 키를 잘못 읽어 화면/요약 값이 비거나 0으로 보일 가능성이 있음

## 상세 Findings

### 1. 파생상품 리서치의 bullish score 계산이 틀림

- 심각도: 높음
- 파일:
  - `dashboard/backend/services/research_analyzer.py`
  - `dashboard/backend/services/spf_service.py`

#### 근거

- `calc_bullish_score()` 시그니처는 아래와 같습니다.
  - `(oi_change_3d, cum_fr_3d, cum_fr_7d, flow, bot_alert_level=None)`
- 그런데 `research_analyzer.py`에서는 아래처럼 잘못 호출합니다.
  - `calc_bullish_score(oi_change_3d, oi_change_7d, cum_fr_3d, cum_fr_7d, flow)`

#### 영향

- `oi_change_7d`가 `cum_fr_3d` 자리에 들어가고, 이후 인자도 모두 한 칸씩 밀립니다.
- 결과적으로 파생상품 리서치 카드의 반등 점수는 실제 SPF 계산 로직과 다르게 나옵니다.

#### 관련 위치

- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:103`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:104`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:118`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:119`
- `d:\Dev\Coin\dashboard\backend\services\spf_service.py:116`

### 2. CVD 스크리너가 BTC OI를 모든 심볼에 공통 적용함

- 심각도: 높음
- 파일:
  - `dashboard/backend/services/cvd_service.py`

#### 근거

- `_get_oi_change_from_db(symbol)`는 `symbol` 인자를 받지만 실제 쿼리는 심볼 조건 없이 최신 `spf_records` 1건만 조회합니다.
- `spf_records`는 BTC 기반 SPF 데이터 저장소라서, ETH/SOL/JUP 등 개별 심볼용 OI가 아닙니다.

#### 영향

- CVD 스코어링의 `oi_change` 팩터가 모든 종목에 동일한 BTC 값으로 들어갑니다.
- 스크리너 순위와 점수가 심볼 고유 데이터가 아니라 BTC 파생 흐름에 끌려 왜곡됩니다.

#### 관련 위치

- `d:\Dev\Coin\dashboard\backend\services\cvd_service.py:314`
- `d:\Dev\Coin\dashboard\backend\services\cvd_service.py:316`
- `d:\Dev\Coin\dashboard\backend\services\cvd_service.py:352`
- `d:\Dev\Coin\dashboard\backend\services\cvd_service.py:358`

### 3. 스케줄러가 존재하지 않는 메서드를 호출함

- 심각도: 높음
- 파일:
  - `dashboard/backend/main.py`
  - `crypto-volatility-bot/app/notification_dispatcher.py`

#### 근거

- 스케줄러는 아래 메서드를 예약합니다.
  - `dispatcher.send_daily_briefing()`
  - `dispatcher.send_weekly_report()`
- 하지만 `NotificationDispatcher`에는 해당 메서드가 정의되어 있지 않습니다.

#### 영향

- 해당 잡이 실행되는 시점에 `AttributeError`가 발생할 가능성이 큽니다.
- 배포 후 특정 시각에만 터지는 유형이라 초기에 놓치기 쉽습니다.

#### 관련 위치

- `d:\Dev\Coin\dashboard\backend\main.py:167`
- `d:\Dev\Coin\dashboard\backend\main.py:168`
- `d:\Dev\Coin\dashboard\backend\main.py:173`
- `d:\Dev\Coin\dashboard\backend\main.py:174`
- `d:\Dev\Coin\crypto-volatility-bot\app\notification_dispatcher.py:44`

### 4. 온체인 리서치 요약이 잘못된 키를 읽음

- 심각도: 중간
- 파일:
  - `dashboard/backend/services/research_analyzer.py`
  - `crypto-volatility-bot/app/analyzers/onchain_analyzer.py`

#### 근거

- `OnchainAnalyzer`는 `details`에 `inflow`, `outflow`, `flow_ratio`를 넣습니다.
- 그런데 `research_analyzer`는 `exchange_inflow`, `exchange_outflow`를 읽고 있습니다.

#### 영향

- 리서치 요약에서 유입/유출 값이 0 또는 기본값처럼 보일 수 있습니다.
- 계산은 되었는데 표시가 틀려서 사용자가 온체인 상태를 오해하게 됩니다.

#### 관련 위치

- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:299`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:300`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:314`
- `d:\Dev\Coin\crypto-volatility-bot\app\analyzers\onchain_analyzer.py:51`
- `d:\Dev\Coin\crypto-volatility-bot\app\analyzers\onchain_analyzer.py:52`

### 5. 기술분석 리서치 요약이 실제 details 구조와 맞지 않음

- 심각도: 중간
- 파일:
  - `dashboard/backend/services/research_analyzer.py`
  - `crypto-volatility-bot/app/analyzers/technical_analyzer.py`

#### 근거

- 리서치 쪽은 다음 키를 기대합니다.
  - `rsi_value`
  - `bb_position`
  - `active_boosters`
- 실제 `TechnicalAnalyzer` 결과는 아래 구조입니다.
  - `details["rsi"]`
  - `details["bb"]`
  - `details["signal_boost"]["active_boosters"]`

#### 영향

- RSI, BB 위치, 활성 부스터가 화면/요약에 비어 보입니다.
- 사용자가 기술분석 결과를 신뢰하기 어렵게 됩니다.

#### 관련 위치

- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:185`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:186`
- `d:\Dev\Coin\dashboard\backend\services\research_analyzer.py:187`
- `d:\Dev\Coin\crypto-volatility-bot\app\analyzers\technical_analyzer.py:65`
- `d:\Dev\Coin\crypto-volatility-bot\app\analyzers\technical_analyzer.py:72`
- `d:\Dev\Coin\crypto-volatility-bot\app\analyzers\technical_analyzer.py:213`

### 6. 거래소 설정명과 실제 구현이 어긋남

- 심각도: 중간
- 파일:
  - `crypto-volatility-bot/app/utils/config.py`
  - `crypto-volatility-bot/app/data/data_collector.py`
  - `crypto-volatility-bot/tests/unit/test_data_collector.py`

#### 근거

- 환경변수/설정 이름은 `BINANCE_API_KEY`, `BINANCE_API_SECRET`입니다.
- 하지만 실제 OHLCV 수집은 `ccxt.bybit()`를 사용합니다.
- 단위 테스트는 `ccxt.binance`를 패치하고 있어 현재 코드와 기대가 어긋납니다.

#### 영향

- 운영자는 Binance 키를 넣고도 실제로는 Bybit를 호출하게 됩니다.
- 테스트도 이 불일치 때문에 실패합니다.

#### 관련 위치

- `d:\Dev\Coin\crypto-volatility-bot\app\utils\config.py:19`
- `d:\Dev\Coin\crypto-volatility-bot\app\utils\config.py:47`
- `d:\Dev\Coin\crypto-volatility-bot\app\data\data_collector.py:46`
- `d:\Dev\Coin\crypto-volatility-bot\app\data\data_collector.py:57`
- `d:\Dev\Coin\crypto-volatility-bot\tests\unit\test_data_collector.py:33`

## 테스트 메모

- `crypto-volatility-bot` 단위 테스트 실행 결과:
  - `269 passed, 1 failed`
- 실패 테스트:
  - `tests/unit/test_data_collector.py::TestFetchOhlcv::test_api_error_returns_none`

### 실패 원인 해석

- 테스트는 `ccxt.binance`를 패치하지만 실제 구현은 `ccxt.bybit()`를 사용합니다.
- 따라서 패치가 적용되지 않아 mock 예외가 발생하지 않고 실제 데이터가 반환됩니다.

## 권장 수정 순서

1. `research_analyzer.py`의 `calc_bullish_score()` 호출 인자 순서 수정
2. `cvd_service.py`에서 BTC SPF OI를 타 심볼에 재사용하는 구조 제거 또는 명시적으로 BTC 전용 팩터로 분리
3. `main.py`의 잘못된 스케줄러 메서드 등록 수정
4. `research_analyzer.py`의 `details` 키 참조를 실제 analyzer 출력 구조에 맞게 수정
5. 거래소 설정명을 `bybit` 기준으로 통일하거나 실제 구현을 Binance로 변경

## 비고

- 터미널에서 한글이 일부 깨져 보였지만, 핵심 Python 모듈들은 import 기준으로는 로드 가능했습니다.
- 즉, 이번 메모의 핵심 이슈는 문법 에러보다 계산/호출/매핑 불일치 쪽입니다.
