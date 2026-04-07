# GCP 배포 계획서

**기능명**: Google Cloud Platform 배포 및 운영 설정
**작성일**: 2026-02-17
**예상 소요 시간**: 1~2시간
**현재 상태**: gcloud SDK 설치 완료

---

**CRITICAL INSTRUCTIONS**: 각 단계 완료 후:
1. ✅ 완료된 항목 체크
2. 🧪 검증 명령어 실행
3. ⚠️ 모든 검증 항목 통과 확인
4. ➡️ 다음 단계로 진행

⛔ 검증 실패 시 다음 단계로 넘어가지 마세요

---

## Phase 1: GCP 인증 및 프로젝트 설정 (10분)

### 목표
gcloud CLI 인증 및 프로젝트 연결

### 작업

- [ ] **1.1** gcloud 인증 로그인
  ```bash
  gcloud auth login
  ```
  → 브라우저에서 Google 계정 로그인

- [ ] **1.2** GCP 프로젝트 ID 확인/선택
  ```bash
  # 기존 프로젝트 목록 확인
  gcloud projects list

  # 프로젝트 설정 (기존 프로젝트 사용 시)
  gcloud config set project YOUR_PROJECT_ID

  # 또는 새 프로젝트 생성
  gcloud projects create crypto-volatility-bot --name="Crypto Volatility Bot"
  gcloud config set project crypto-volatility-bot
  ```

- [ ] **1.3** 리전 설정 (서울)
  ```bash
  gcloud config set run/region asia-northeast3
  ```

- [ ] **1.4** 결제 계정 연결 확인
  ```bash
  gcloud billing accounts list
  gcloud billing projects describe $(gcloud config get-value project)
  ```
  > ⚠️ 결제 계정이 연결되어 있어야 Cloud Run, Scheduler 등 사용 가능

### 검증
```bash
gcloud config list
# project, region 값이 올바른지 확인
```

---

## Phase 2: 필수 API 활성화 (5분)

### 목표
Cloud Run, Cloud Build, Secret Manager, Cloud Scheduler API 활성화

### 작업

- [ ] **2.1** 필요한 API 일괄 활성화
  ```bash
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
    containerregistry.googleapis.com
  ```

### 검증
```bash
gcloud services list --enabled --filter="name:(run OR cloudbuild OR secretmanager OR cloudscheduler OR containerregistry)"
# 5개 API가 모두 ENABLED 상태인지 확인
```

---

## Phase 3: Secret Manager에 환경 변수 등록 (10분)

### 목표
Telegram Bot Token, Chat ID 등 민감 정보를 Secret Manager에 안전하게 저장

### 사전 준비
- Telegram Bot Token (@BotFather에서 발급)
- Telegram Chat ID (봇에 메시지 보낸 후 확인)

### 작업

- [ ] **3.1** Telegram Bot Token 등록
  ```bash
  echo -n "실제_봇_토큰" | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
  ```

- [ ] **3.2** Telegram Chat ID 등록
  ```bash
  echo -n "실제_채팅_ID" | gcloud secrets create TELEGRAM_CHAT_ID --data-file=-
  ```

- [ ] **3.3** (선택) Binance API Key 등록 — 공개 데이터만 사용하면 불필요
  ```bash
  echo -n "BINANCE_KEY" | gcloud secrets create BINANCE_API_KEY --data-file=-
  echo -n "BINANCE_SECRET" | gcloud secrets create BINANCE_API_SECRET --data-file=-
  ```

- [ ] **3.4** Cloud Build 서비스 계정에 Secret 접근 권한 부여
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')

  # Cloud Build 서비스 계정에 권한 부여
  gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

  gcloud secrets add-iam-policy-binding TELEGRAM_CHAT_ID \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

  # Cloud Run 서비스 계정에도 권한 부여
  gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

  gcloud secrets add-iam-policy-binding TELEGRAM_CHAT_ID \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  ```

### 검증
```bash
gcloud secrets list
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID가 표시되는지 확인

gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN
# 올바른 토큰 값이 출력되는지 확인
```

---

## Phase 4: Cloud Build로 빌드 및 배포 (15분)

### 목표
Docker 이미지 빌드 → 테스트 → Cloud Run 배포

### 작업

- [ ] **4.1** 프로젝트 디렉토리로 이동
  ```bash
  cd E:\Dev\coin\crypto-volatility-bot
  ```

- [ ] **4.2** Cloud Build 서비스 계정에 Cloud Run 배포 권한 부여
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')

  gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/run.admin"

  gcloud iam service-accounts add-iam-policy-binding \
    ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"
  ```

- [ ] **4.3** Cloud Build 실행 (테스트 + 빌드 + 배포)
  ```bash
  gcloud builds submit --config=deploy/gcp/cloudbuild.yaml
  ```
  > 이 명령어가 실행하는 작업:
  > 1. Docker test 스테이지 빌드 → pytest 실행
  > 2. production 이미지 빌드
  > 3. Container Registry에 푸시
  > 4. Cloud Run에 배포

- [ ] **4.4** Cloud Run 서비스 URL 확인
  ```bash
  gcloud run services describe crypto-volatility-bot \
    --region=asia-northeast3 \
    --format='value(status.url)'
  ```

### 검증
```bash
# Health check 테스트
CLOUD_RUN_URL=$(gcloud run services describe crypto-volatility-bot --region=asia-northeast3 --format='value(status.url)')
curl -s "${CLOUD_RUN_URL}/health"
# {"status": "ok"} 응답 확인
```

---

## Phase 5: Cloud Scheduler 설정 (10분)

### 목표
1시간마다 자동 분석 실행 스케줄 등록

### 작업

- [ ] **5.1** Cloud Run 서비스에 인증 없이 접근 허용 (또는 서비스 계정 인증 사용)
  ```bash
  # 방법 A: 공개 접근 허용 (간단)
  gcloud run services add-iam-policy-binding crypto-volatility-bot \
    --region=asia-northeast3 \
    --member="allUsers" \
    --role="roles/run.invoker"

  # 방법 B: 서비스 계정 인증 (보안 권장)
  # → 이 경우 아래 scheduler 생성 시 --oauth-service-account-email 추가
  ```

- [ ] **5.2** 1시간마다 분석 실행 스케줄 생성
  ```bash
  CLOUD_RUN_URL=$(gcloud run services describe crypto-volatility-bot --region=asia-northeast3 --format='value(status.url)')

  gcloud scheduler jobs create http crypto-bot-hourly \
    --location=asia-northeast3 \
    --schedule="0 * * * *" \
    --uri="${CLOUD_RUN_URL}/scheduled-run" \
    --http-method=POST \
    --time-zone="Asia/Seoul"
  ```

- [ ] **5.3** 수동 트리거 테스트
  ```bash
  gcloud scheduler jobs run crypto-bot-hourly --location=asia-northeast3
  ```

### 검증
```bash
# 스케줄러 상태 확인
gcloud scheduler jobs describe crypto-bot-hourly --location=asia-northeast3

# Cloud Run 로그에서 실행 확인
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=crypto-volatility-bot" \
  --limit=10 --format="table(timestamp, textPayload)"

# Telegram 메시지 수신 확인 (봇 채팅방에서 확인)
```

---

## Phase 6: Telegram Webhook 등록 및 최종 검증 (10분)

### 목표
Telegram Webhook 연결 + 전체 시스템 동작 확인

### 작업

- [ ] **6.1** Telegram Webhook 등록
  ```bash
  CLOUD_RUN_URL=$(gcloud run services describe crypto-volatility-bot --region=asia-northeast3 --format='value(status.url)')
  BOT_TOKEN=$(gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN)

  curl "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook?url=${CLOUD_RUN_URL}/webhook"
  # {"ok":true,"result":true} 확인
  ```

- [ ] **6.2** Webhook 상태 확인
  ```bash
  curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
  ```

- [ ] **6.3** 비용 알림 설정 (선택)
  ```bash
  # GCP Console > Billing > Budgets & alerts에서 설정
  # 월 $5 상한선 알림 권장
  ```

### 최종 검증 체크리스트

- [ ] `/health` 엔드포인트 정상 응답
- [ ] `/scheduled-run` 호출 시 분석 실행 및 Telegram 메시지 수신
- [ ] Cloud Scheduler 정상 등록 (1시간마다)
- [ ] Cloud Run 로그에 에러 없음
- [ ] Secret Manager에 민감 정보 안전하게 저장됨

---

## 리스크 및 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| Cloud Build 실패 | 권한 부족 | Phase 4.2의 IAM 권한 확인 |
| Secret 접근 불가 | IAM 바인딩 누락 | Phase 3.4 재실행 |
| Scheduler 트리거 실패 | Cloud Run URL 불일치 | URL 재확인, 인증 설정 확인 |
| Telegram 메시지 미수신 | Bot Token/Chat ID 오류 | Secret Manager 값 확인 |
| 결제 오류 | 결제 계정 미연결 | GCP Console에서 결제 계정 연결 |

---

## 배포 후 운영

```yaml
모니터링:
  - GCP Console > Cloud Run > Logs 확인
  - Telegram 메시지 정상 수신 여부

비용 확인:
  - GCP Console > Billing > 예상 월 $0.32~$0.50

롤백:
  - gcloud run services update-traffic crypto-volatility-bot --to-revisions=PREVIOUS_REVISION=100 --region=asia-northeast3
```
