# Crypto Volatility Analysis Bot

BTC/ETH의 **온체인(40%) + 기술적(35%) + 감성(25%)** 분석을 종합하여 텔레그램으로 실시간 변동성 알림을 전송하는 봇입니다.

## 기능

- 📊 **3개 분석 레이어**: 온체인(거래소 유입/유출, 고래), 기술적(ATR, BB, HV 등), 감성(Fear & Greed)
- 🚨 **4종 알림**: 긴급(≥80점), 고래 감지, 정기 리포트, 일간 요약
- 📡 **Telegram 명령어**: `/analyze`, `/status`, `/set_interval`, `/help`
- 🐳 **Docker 지원** + GCP/AWS 배포 가이드

## 빠른 시작

### 1. 환경 설정

```bash
git clone <repo>
cd crypto-volatility-bot
cp .env.example .env
# .env 파일에 토큰/키 입력
```

### 2. 필수 환경 변수

```
TELEGRAM_BOT_TOKEN=   # @BotFather에서 발급
TELEGRAM_CHAT_ID=     # 봇이 메시지를 보낼 채팅 ID
BYBIT_API_KEY=        # (선택) Bybit API 키 — 공개 데이터만 사용하면 불필요
```

### 3. 로컬 실행

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt  # Windows
# 또는
.venv/bin/pip install -r requirements-dev.txt      # Linux/macOS

# 한 번 실행 (테스트용)
python -c "import asyncio; from app.pipeline import run_analysis; from app.utils.config import Config; asyncio.run(run_analysis(Config.from_env()))"

# 서버 모드 (Webhook)
python -m app.main
```

### 4. 테스트

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
ruff check app/ tests/
mypy app/ --ignore-missing-imports
```

### 5. Docker

```bash
# 테스트
docker build --target test -t crypto-bot-test .
docker run --rm crypto-bot-test

# 프로덕션
docker build --target production -t crypto-bot .
docker run --rm --env-file .env crypto-bot
```

## 점수 계산

| 레이어 | 가중치 | 소스 |
|--------|--------|------|
| 온체인 | 40% | CryptoQuant API |
| 기술적 | 35% | Binance OHLCV (ATR, BB, CVI, HV, Volume) |
| 감성 | 25% | Fear & Greed Index |

**알림 레벨**: EMERGENCY(≥80) → HIGH(≥60) → MEDIUM(≥40) → LOW(<40)

## 배포

- [GCP Cloud Run](deploy/gcp/README.md)
- [AWS Lambda](deploy/aws/README.md)

## 아키텍처

```
DataCollector → [OnchainAnalyzer, TechnicalAnalyzer, SentimentAnalyzer]
             → ScoreAggregator → AggregatedResult
             → [MessageFormatter → TelegramNotifier]
```

## Python 버전 호환성

Python **3.10–3.12** 권장 (Docker 이미지: `python:3.12-slim`).
로컬 개발 시 Python 3.14도 동작하나 pandas-ta 사용 불가 → 순수 pandas/numpy 구현 사용.
