# AWS 배포 가이드

## 아키텍처
- **Lambda**: 봇 실행 (60초 타임아웃)
- **EventBridge**: 1시간 주기 트리거
- **API Gateway**: Telegram webhook 수신
- **Secrets Manager**: 환경 변수 관리
- **SAM**: 배포 템플릿

## 사전 준비

```bash
pip install aws-sam-cli
aws configure  # AWS 자격증명 설정
```

## Secrets 등록

```bash
aws secretsmanager create-secret \
  --name crypto-bot/telegram \
  --secret-string '{"bot_token":"YOUR_TOKEN","chat_id":"YOUR_CHAT_ID"}'

aws secretsmanager create-secret \
  --name crypto-bot/cryptoquant \
  --secret-string '{"api_key":"YOUR_API_KEY"}'
```

## 배포

```bash
sam build
sam deploy --guided
```

## Lambda Handler 추가

Lambda를 위해 `app/lambda_handler.py` 생성:

```python
import asyncio
from app.pipeline import run_analysis
from app.utils.config import Config

def handler(event, context):
    config = Config.from_env()
    asyncio.run(run_analysis(config))
    return {"statusCode": 200}
```

## Telegram Webhook 등록

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_API_GATEWAY_URL/webhook"
```
