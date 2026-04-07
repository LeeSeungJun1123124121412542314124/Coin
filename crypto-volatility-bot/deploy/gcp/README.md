# GCP 배포 가이드

## 아키텍처
- **Cloud Run**: 봇 서버 (min-instances=0, 비용 절감)
- **Cloud Scheduler**: 주기적 분석 트리거 (`POST /scheduled-run`, `POST /scheduled-report`)
- **Secret Manager**: 환경 변수 관리
- **Cloud Build**: CI/CD 파이프라인

## 사전 준비

```bash
# GCP 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID

# 필요 API 활성화
gcloud services enable run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com
```

## Secrets 등록

```bash
echo -n "YOUR_TELEGRAM_BOT_TOKEN" | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
echo -n "YOUR_TELEGRAM_CHAT_ID" | gcloud secrets create TELEGRAM_CHAT_ID --data-file=-
echo -n "YOUR_CRYPTOQUANT_API_KEY" | gcloud secrets create CRYPTOQUANT_API_KEY --data-file=-
```

## 배포

```bash
gcloud builds submit --config=deploy/gcp/cloudbuild.yaml
```

## Cloud Scheduler 설정

```bash
# 1시간마다 분석 실행 (이벤트 알림만 발송)
gcloud scheduler jobs create http crypto-bot-hourly \
  --schedule="0 * * * *" \
  --uri="https://YOUR_CLOUD_RUN_URL/scheduled-run" \
  --http-method=POST \
  --location=asia-northeast3

# 12시간마다 정기 리포트 발송
gcloud scheduler jobs create http crypto-bot-report \
  --schedule="0 */12 * * *" \
  --uri="https://YOUR_CLOUD_RUN_URL/scheduled-report" \
  --http-method=POST \
  --location=asia-northeast3
```

## Telegram Webhook 등록

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://YOUR_CLOUD_RUN_URL/webhook"
```
