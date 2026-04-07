# 외부 API 가이드 — 크립토 인사이트 대시보드 (신규만)

> 기존 봇(`crypto-volatility-bot`)에서 이미 사용 중인 API는 제외.
> 봇 기존 API: Binance 현물(ccxt), Alternative.me, CoinMetrics, Telegram

## 요약

| # | API | 용도 | 인증 | 비용 | 키 발급 |
|---|---|---|---|---|---|
| 1 | CoinGecko | 코인 가격 6종 | **Demo API 키** | 무료 | 회원가입 발급 |
| 2 | Yahoo Finance | 미국 시장 지표 10종 | 불필요 | 무료 (비공식) | - |
| 3 | Binance 선물 | OI, FR, 롱숏 비율 | 불필요 | 무료 | - |
| 4 | 업비트 | 거래량, BTC 원화가 | 불필요 | 무료 | - |
| 5 | 빗썸 | 거래량 | 불필요 | 무료 | - |
| 6 | Coinbase | BTC 현물가 (프리미엄 계산) | 불필요 | 무료 | - |
| 7 | ExchangeRate API | USD/KRW 환율 | 불필요 | 무료 | - |
| 8 | **FRED** | TGA, M2, 연준 보유량 | **API 키 필요** | 무료 | 이메일 발급 |
| 9 | US Treasury | 국채 경매 일정 | 불필요 | 무료 | - |
| 10 | Hyperliquid | 고래 리더보드/포지션 | 불필요 | 무료 | - |

> **API 키가 필요한 건 CoinGecko(Demo)와 FRED, 총 2개.** 나머지는 전부 키 없이 사용 가능.

---

## 1. CoinGecko — 코인 가격

**용도**: 탭 1 대시보드 — BTC, ETH, SOL, HYPE, INJ, ONDO 가격 + 24h 변동률 + 시총

**인증**: Demo API 키 필요 (무료, 헤더에 포함)
**제한**: 월 10,000콜 → **60초 캐시 필수**

### 요청

```
GET https://api.coingecko.com/api/v3/simple/price
  ?ids=bitcoin,ethereum,solana,hyperliquid,injective-protocol,ondo-finance
  &vs_currencies=usd
  &include_24hr_change=true
  &include_market_cap=true
  &x_cg_demo_api_key={COINGECKO_API_KEY}
```

### 응답

```json
{
  "bitcoin": {
    "usd": 84520,
    "usd_24h_change": -2.1,
    "usd_market_cap": 1670000000000
  },
  "ethereum": { ... },
  "solana": { ... }
}
```

### CoinGecko ID 매핑

| 코인 | CoinGecko ID |
|---|---|
| BTC | `bitcoin` |
| ETH | `ethereum` |
| SOL | `solana` |
| HYPE | `hyperliquid` |
| INJ | `injective-protocol` |
| ONDO | `ondo-finance` |

### 추가 엔드포인트 (글로벌 데이터)

```
GET https://api.coingecko.com/api/v3/global
  ?x_cg_demo_api_key={COINGECKO_API_KEY}
→ 응답에서 추출:
  data.total_market_cap.usd       → 전체 크립토 시총
  data.market_cap_percentage.btc  → BTC 도미넌스
  data.total_market_cap.usd 중 스테이블코인 시총은 별도 계산 필요
```

---

## 2. Yahoo Finance — 미국 시장 지표

**용도**: 탭 1 대시보드 — S&P500, NASDAQ, VIX, DXY, 금, 은 등 10개 지표

**인증**: 불필요
**주의**: 비공식 API. 가끔 차단됨 → `yfinance` Python 패키지를 폴백으로 사용

### 요청

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}
  ?interval=1d
  &range=5d
```

### 티커 목록

| 지표 | 티커 |
|---|---|
| S&P 500 | `^GSPC` |
| NASDAQ | `^IXIC` |
| Russell 2000 | `^RUT` |
| VIX | `^VIX` |
| MOVE | `^MOVE` |
| DXY | `DX-Y.NYB` |
| US 10Y 국채 | `^TNX` |
| 금 (XAU) | `GC=F` |
| 은 (XAG) | `SI=F` |
| KOSPI | `^KS11` (탭 2 KRX 거래량용) |

### 응답에서 추출

```python
data = response["chart"]["result"][0]
closes = data["indicators"]["quote"][0]["close"]  # 최근 5일 종가 배열
current = closes[-1]
sparkline = closes  # 스파크라인 차트용
```

### 폴백: yfinance 패키지

```python
import yfinance as yf
ticker = yf.Ticker("^GSPC")
hist = ticker.history(period="5d")
close = hist["Close"].iloc[-1]
```

---

## 3. Binance 선물 API — OI, FR, 롱숏 비율

**용도**: 탭 1 온체인 지표, 탭 3 SPF 핵심 데이터, 탭 7 선물 CVD

**인증**: 불필요

### 3-1. 미결제약정 (OI) 현재값

```
GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT
→ { "openInterest": "87895.197", "symbol": "BTCUSDT" }
```

### 3-2. OI 히스토리 (탭 3 SPF용, 최대 500일)

```
GET https://fapi.binance.com/futures/data/openInterestHist
  ?symbol=BTCUSDT
  &period=1d
  &limit=500
→ [{ "symbol": "BTCUSDT", "sumOpenInterest": "87895", "timestamp": 1234567890000 }]
```

### 3-3. 펀딩레이트 (FR) 최근 3건

```
GET https://fapi.binance.com/fapi/v1/fundingRate
  ?symbol=BTCUSDT
  &limit=3
→ [{ "fundingRate": "-0.00021", "fundingTime": 1234567890000 }]
```

**일별 평균 계산**: 하루 3건 (8시간마다) → 3개 평균값 사용

### 3-4. FR 히스토리 (탭 3 SPF용)

```
GET https://fapi.binance.com/fapi/v1/fundingRate
  ?symbol=BTCUSDT
  &limit=1500
→ 1500건 = 약 500일치 (하루 3건)
```

### 3-5. 글로벌 롱/숏 비율

```
GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio
  ?symbol=BTCUSDT
  &period=1h
  &limit=1
→ [{ "longShortRatio": "1.8249", "longAccount": "0.6460", "shortAccount": "0.3540" }]
```

### 3-6. 선물 캔들 (CVD 계산용)

```
GET https://fapi.binance.com/fapi/v1/klines
  ?symbol=BTCUSDT&interval=4h&limit=200
```

**CVD 계산**:
```python
taker_buy = float(kline[9])     # 시장가 매수
total_vol = float(kline[5])     # 총 거래량
taker_sell = total_vol - taker_buy
delta = taker_buy - taker_sell
cvd += delta  # 누적
```

---

## 4. 업비트 — 거래량, BTC 원화가

**용도**: 탭 1 김치프리미엄, 탭 2 거래량 트래커

**인증**: 불필요
**주의**: 한 번에 요청 가능한 마켓 수 제한 있음 → 청크 분할 필요

### 4-1. KRW 마켓 목록 조회

```
GET https://api.upbit.com/v1/market/all?isDetails=false
→ [{ "market": "KRW-BTC" }, { "market": "KRW-ETH" }, ...]
→ "KRW-" 로 시작하는 것만 필터링
```

### 4-2. 전체 티커 조회 (거래량)

```
GET https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH,KRW-XRP,...
→ [{ "market": "KRW-BTC", "trade_price": 92000000, "acc_trade_price_24h": 1234567890000 }]
```

**거래대금 합산**: 모든 KRW 마켓의 `acc_trade_price_24h` 합계
**조 단위 변환**: `sum / 1_000_000_000_000`

### 4-3. BTC 원화가 (김치프리미엄 계산용)

```
GET https://api.upbit.com/v1/ticker?markets=KRW-BTC
→ [{ "trade_price": 92000000 }]
```

---

## 5. 빗썸 — 거래량

**용도**: 탭 2 거래량 트래커

**인증**: 불필요

### 전체 코인 조회

```
GET https://api.bithumb.com/public/ticker/ALL_KRW
→ {
    "status": "0000",
    "data": {
      "BTC": { "closing_price": "92000000", "units_traded_24H": "123.45" },
      "ETH": { "closing_price": "4500000", "units_traded_24H": "456.78" },
      "date": "1234567890000"
    }
  }
```

**거래대금 합산**: 각 코인 `units_traded_24H × closing_price` (단, `"date"` 키는 건너뜀)

---

## 6. Coinbase — BTC 현물가 (프리미엄 계산)

**용도**: 탭 1 코인베이스 프리미엄 계산

**인증**: 불필요

### 요청

```
GET https://api.coinbase.com/v2/prices/BTC-USD/spot
→ { "data": { "base": "BTC", "currency": "USD", "amount": "84500.00" } }
```

### 코인베이스 프리미엄 계산

```python
coinbase_price = float(coinbase_response["data"]["amount"])
binance_price = float(binance_response["price"])  # Binance 현물 API (봇 기존)
premium = (coinbase_price - binance_price) / binance_price * 100
# 양수 = 코인베이스가 더 비쌈 (미국 매수세), 음수 = 바이낸스가 더 비쌈
```

---

## 7. ExchangeRate API — USD/KRW 환율

**용도**: 탭 1 김치프리미엄 계산

**인증**: 불필요

### 요청

```
GET https://api.exchangerate-api.com/v4/latest/USD
→ { "rates": { "KRW": 1380.5, "EUR": 0.92, ... } }
```

### 김치프리미엄 계산

```python
upbit_btc_krw = 92000000              # 업비트 BTC 원화가
usd_krw = rates["KRW"]                # 환율
binance_btc_usd = 84520               # 바이낸스 BTC 달러가 (봇 기존)
kimchi = (upbit_btc_krw / usd_krw / binance_btc_usd - 1) * 100
# 양수 = 한국이 더 비쌈 (국내 과열)
```

---

## 8. FRED — TGA, M2, 연준 보유량 ⚠️ API 키 필요

**용도**: 탭 6 유동성 분석 (매크로 레이어 L1)

**인증**: API 키 필요 (무료)

### 키 발급 방법

1. https://fred.stlouisfed.org/docs/api/api_key.html 접속
2. "Request API Key" 클릭
3. 이메일 입력 → 계정 생성
4. 발급된 키를 환경변수에 저장: `FRED_API_KEY=your_key_here`

### 8-1. TGA 잔고 (일별)

```
GET https://api.stlouisfed.org/fred/series/observations
  ?series_id=WTREGEN
  &api_key={FRED_API_KEY}
  &file_type=json
  &limit=365
  &sort_order=desc
→ { "observations": [{ "date": "2026-04-03", "value": "882.82" }] }
```

**단위**: $10억 (billion)
**해석**: 감소 = 유동성 공급 (호재) / 증가 = 유동성 흡수 (악재)

### 8-2. M2 통화량 (월별)

```
GET https://api.stlouisfed.org/fred/series/observations
  ?series_id=M2SL
  &api_key={FRED_API_KEY}
  &file_type=json
  &limit=60
  &sort_order=desc
```

**YoY 계산**: `(현재 - 12개월 전) / 12개월 전 × 100`

### 8-3. 연준 국채 보유량 (주별)

| 시리즈 ID | 내용 |
|---|---|
| `WSHODLL` | 연준 총 국채 보유 |
| `WSHOMBCB` | T-bill 보유 |
| `WSHOMSB` | Notes+Bonds 보유 |

```
GET https://api.stlouisfed.org/fred/series/observations
  ?series_id=WSHODLL
  &api_key={FRED_API_KEY}
  &file_type=json
  &limit=52
  &sort_order=desc
```

---

## 9. US Treasury Fiscal Data — 국채 경매 일정

**용도**: 탭 6 예정 국채 경매 테이블

**인증**: 불필요

### 국채 경매 일정

```
GET https://api.fiscaldata.treasury.gov/services/api/v1/debt/upcoming_auctions
  ?fields=auction_date,issue_date,security_type,security_term,offering_amount
  &sort=auction_date
```

### 평균 금리

```
GET https://api.fiscaldata.treasury.gov/services/api/v1/accounting/od/avg_interest_rates
  ?fields=record_date,security_type,avg_interest_rate_amt
  &filter=record_date:gte:2024-01-01
  &sort=-record_date
  &limit=100
```

---

## 10. Hyperliquid — 고래 리더보드

**용도**: 탭 8 HL 고래 추적, 주간 성적표 고래 동향

**인증**: 불필요
**방식**: REST가 아닌 **POST + JSON body**

### 리더보드 조회

```python
import httpx

response = httpx.post(
    "https://api.hyperliquid.xyz/info",
    json={"type": "leaderboard"}
)
data = response.json()
# → [{ "user": "0x...", "accountValue": "1234567", "pnl": "45678", "roi": "0.37" }]
```

### 특정 주소 포지션 조회

```python
response = httpx.post(
    "https://api.hyperliquid.xyz/info",
    json={"type": "clearinghouseState", "user": "0xABC123..."}
)
data = response.json()
# → { "assetPositions": [{ "position": { "coin": "BTC", "szi": "12.5", "unrealizedPnl": "1234" } }] }
```

---

## 환경변수 정리 (신규만)

```bash
# 신규 필수 (키 발급 필요)
COINGECKO_API_KEY=CG-xxxxxxxxxxxx        # coingecko.com 회원가입 후 Demo 키 발급
FRED_API_KEY=abcdef123456                # fred.stlouisfed.org에서 발급

# 앱 설정
DATABASE_PATH=/data/crypto.db            # SQLite 파일 경로 (Railway Volume)
PIN_CODE=0000                            # 대시보드 PIN (변경 권장)
```

> 기존 봇 환경변수(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BINANCE_API_KEY` 등)는 그대로 유지.

---

## API 호출 빈도 & 캐시 전략

| API | 호출 빈도 | 캐시 TTL | 사유 |
|---|---|---|---|
| CoinGecko | 탭 1 로드 시 | 60초 | 무료 50콜/분 제한 |
| Yahoo Finance | 탭 1 로드 시 | 300초 | 비공식, 차단 방지 |
| Binance 선물 (OI/FR) | 탭 1, 3 로드 시 | 60초 | |
| Binance OI/FR 히스토리 | 탭 3 로드 시 | 3600초 | 일별 데이터, 자주 안 변함 |
| Binance 선물 캔들 (CVD) | 탭 7 로드 시 | 300초 | |
| 업비트 | 탭 1, 2 로드 시 | 300초 | |
| 빗썸 | 탭 2 로드 시 | 300초 | |
| Coinbase | 탭 1 로드 시 | 60초 | |
| ExchangeRate | 탭 1 로드 시 | 3600초 | 환율 자주 안 변함 |
| FRED | 스케줄 (1일 1회) | 86400초 | 일/주/월 데이터 |
| US Treasury | 탭 6 로드 시 | 86400초 | |
| Hyperliquid | 스케줄 (2시간) | 7200초 | |
