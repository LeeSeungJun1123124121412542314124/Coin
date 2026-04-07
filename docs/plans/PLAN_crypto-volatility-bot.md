# Implementation Plan: Crypto Volatility Analysis Bot

**Status**: ✅ Complete + Deployed (GCP)
**Started**: 2026-02-16
**Last Updated**: 2026-02-18
**Completion**: 9 phases 완료 (구현 7단계 + API 마이그레이션 + GCP 배포)

---

**⚠️ CRITICAL INSTRUCTIONS**: After completing each phase:
1. ✅ Check off completed task checkboxes
2. 🧪 Run all quality gate validation commands
3. ⚠️ Verify ALL quality gate items pass
4. 📅 Update "Last Updated" date above
5. 📝 Document learnings in Notes section
6. ➡️ Only then proceed to next phase

⛔ **DO NOT skip quality gates or proceed with failing checks**

---

## Context

`e:\Dev\coin\crypto-volatility-bot-plan.md`에 정의된 암호화폐 변동성 분석 봇을 처음부터 구현합니다. 이 봇은 BTC/ETH의 온체인, 기술적 지표, 감성 분석을 종합하여 텔레그램으로 실시간 알림을 보내는 시스템입니다. 매매 실행 없이 **분석 및 시그널 제공**에 집중합니다.

**프로젝트 디렉토리**: `e:\Dev\coin\crypto-volatility-bot\`
**참조 문서**: `e:\Dev\coin\crypto-volatility-bot-plan.md`
**GCP 배포 계획서**: `e:\Dev\coin\crypto-volatility-bot\docs\plans\PLAN_gcp-deployment.md`

---

## 📋 Overview

### Success Criteria
- [x] 로컬에서 `python -m app.main` 실행 시 BTC/ETH 변동성 분석 후 텔레그램 메시지 전송
- [x] 3개 분석 레이어(온체인 40%, 기술적 35%, 감성 25%) 가중 종합 점수 산출
- [x] 긴급 알림(점수 ≥ 80), 고래 알림, 정기 리포트, 일간 요약 4종 알림
- [x] Docker 컨테이너화 완료, GCP 배포 완료
- [x] 전체 테스트 커버리지 ≥ 80% (88% 달성)
- [x] GCP Cloud Run 프로덕션 배포 + Cloud Scheduler 자동 실행

---

## 🏗️ Architecture Decisions

| 결정 | 이유 | 트레이드오프 |
|------|------|-------------|
| **순수 pandas/numpy** (pandas-ta 대신) | Python 3.14 호환, C 컴파일 불필요 | 직접 구현 필요하지만 의존성 감소 |
| **Coin Metrics Community API** (CryptoQuant 대신) | API 키 불필요, 무료, 안정적 | **1일 단위 데이터만 지원** (시간별 불가) |
| **Webhook + Cloud Run 서비스** | Telegram 명령 수신 + 스케줄러 트리거 모두 지원 | 상시 실행 필요 (Cloud Run min-instances=0으로 비용 절감) |
| **FastAPI 경량 서버** | Webhook 엔드포인트 + 스케줄러 엔드포인트 제공, async 지원 | 의존성 추가 |
| **dataclass 기반 모델** | 타입 안전, 불변성, 네이티브 Python 3.10+ | 직렬화 내장 없음 (`asdict` 활용) |
| **ABC 기반 Analyzer** | 일관된 인터페이스, 테스트 시 mock 용이 | 약간의 간접 참조 오버헤드 |
| **클라우드 불가지론 main.py** | 로컬/Docker/Lambda/Cloud Run 동일 진입점 | 클라우드별 얇은 어댑터 필요 |
| **Binance API 키 선택적 지원** | 키 없이도 동작, 있으면 rate limit 여유 확보 | 설정 항목 증가 |
| **GCP Cloud Run** (AWS Lambda 대신) | 무료 티어 관대, 컨테이너 직접 지원, 설정 간단, 한국 리전 | AWS 대비 약간 높은 cold start |

---

## 📦 Dependencies

### External (사전 준비)
- [x] Python 3.10-3.12 설치
- [x] Telegram Bot Token (@BotFather) + Chat ID
- [x] GCP 프로젝트 (`crypto-volatility-bot`) + 결제 계정
- [ ] Binance API Key/Secret — **선택** (없어도 공개 데이터 접근 가능)

### Python Packages (실제 사용)
```
ccxt>=4.2.0              # 거래소 API (Binance OHLCV)
pandas>=2.0.0            # 데이터프레임
numpy>=2.0.0             # 수치 계산
python-telegram-bot>=20.0 # 텔레그램 봇
python-dotenv>=1.0.0     # 환경 변수
python-json-logger>=2.0.0 # 구조화 로깅
requests>=2.31.0         # REST API (Coin Metrics, Fear & Greed)
pyyaml>=6.0              # YAML 설정 파일 파싱
fastapi>=0.110.0         # Webhook 서버
uvicorn>=0.29.0          # ASGI 서버
```

### Dev Dependencies
```
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.23.0
ruff>=0.4.0
mypy>=1.10.0
pip-audit>=2.7.0
```

### 외부 API

| API | 용도 | 인증 | 주기 제한 |
|-----|------|------|----------|
| **Coin Metrics Community** | 온체인 (FlowInExNtv, FlowOutExNtv, AdrActCnt) | 키 불필요 | **1일 단위만** |
| **Binance (CCXT)** | OHLCV 캔들 데이터 | 선택적 | 1시간 단위 가능 |
| **Alternative.me** | Fear & Greed Index | 키 불필요 | 1일 단위 |
| **Telegram Bot API** | 알림 발송 | Bot Token | 무제한 |

---

## 🧪 Test Strategy

**TDD 원칙**: 테스트를 먼저 작성하고, 구현으로 통과시킨 후, 리팩토링

| 테스트 유형 | 커버리지 목표 | 결과 |
|-------------|--------------|------|
| **Unit Tests** | ≥85% | ✅ 105개 테스트, 88% 커버리지 |
| **Integration Tests** | Critical paths | ✅ 구현 완료 |
| **E2E Tests** | 1 full pipeline | ✅ 전체 파이프라인 검증 통과 |

### Validation Commands
```bash
pytest tests/ -v --tb=short
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/ --ignore-missing-imports
pip-audit
```

---

## 🚀 Implementation Phases

---

### Phase 1: 프로젝트 스켈레톤 및 설정 ✅
**Status**: ✅ Complete
- [x] Config 환경 변수 로딩 + 유효성 검사
- [x] JSON 구조화 로거
- [x] 프로젝트 디렉토리 구조 + pyproject.toml
- [x] Git tag: `phase-1-complete`

---

### Phase 2: 기술적 분석 엔진 ✅
**Status**: ✅ Complete
- [x] 5개 기술적 지표 (ATR, Bollinger Width, CVI, Historical Volatility, Volume Spike)
- [x] 순수 pandas/numpy로 직접 구현 (pandas-ta 미사용)
- [x] YAML 기반 동적 지표 설정 (`config/technical.yaml`)
- [x] 지표 레지스트리 플러그인 패턴
- [x] Git tag: `phase-2-complete`

---

### Phase 3: 온체인 + 감성 분석기 ✅
**Status**: ✅ Complete
- [x] 온체인: 거래소 유입/유출 비율 + 고래 부스트
- [x] 감성: Fear & Greed Index 변동성 부스트
- [x] OnchainDataUnavailableError 예외 처리
- [x] Git tag: `phase-3-complete`

---

### Phase 4: 데이터 수집 레이어 + 점수 집계기 ✅
**Status**: ✅ Complete
- [x] DataCollector: CCXT (Binance), Coin Metrics, Fear & Greed API
- [x] ScoreAggregator: 가중 집계 (온체인 40% + 기술적 35% + 감성 25%)
- [x] 4단계 Alert Level (EMERGENCY ≥80, HIGH ≥60, MEDIUM ≥40, LOW <40)
- [x] 3회 재시도 + exponential backoff
- [x] Git tag: `phase-4-complete`

---

### Phase 5: 텔레그램 봇 + Webhook 서버 ✅
**Status**: ✅ Complete
- [x] 4종 메시지 포맷 (정기 리포트, 긴급, 고래, 일간 요약)
- [x] TelegramNotifier: async 전송 + 재시도
- [x] FastAPI Webhook 서버 (/health, /webhook, /scheduled-run)
- [x] Git tag: `phase-5-complete`

---

### Phase 6: 파이프라인 통합 + E2E 테스트 ✅
**Status**: ✅ Complete
- [x] `app/pipeline.py` — 전체 분석 파이프라인
- [x] `app/main.py` — FastAPI + Uvicorn 서버 진입점
- [x] E2E 테스트 (모든 API mocked)
- [x] Git tag: `phase-6-complete`

---

### Phase 7: 컨테이너화 + 배포 설정 ✅
**Status**: ✅ Complete
- [x] Dockerfile (multi-stage: test + production)
- [x] docker-compose.yml
- [x] GCP 배포 가이드 (`deploy/gcp/`)
- [x] AWS 배포 가이드 (`deploy/aws/`)
- [x] README.md
- [x] Git tag: `phase-7-complete`

---

### Phase 8: CryptoQuant → Coin Metrics 마이그레이션 ✅
**Status**: ✅ Complete
**Goal**: CryptoQuant API를 Coin Metrics Community API로 교체
- [x] `data_collector.py` — Coin Metrics Community API (`community-api.coinmetrics.io/v4`) 연동
- [x] 메트릭: `FlowInExNtv` (거래소 유입), `FlowOutExNtv` (거래소 유출), `AdrActCnt` (활성 주소)
- [x] API 키 불필요 (무료)
- [x] Config에서 `CRYPTOQUANT_API_KEY` 필수 요구 제거
- [x] 고래 대리지표: `(inflow + outflow) / 1000` (총 유동량 기반 추정)
- [x] `dormant_whale_activated`: 현재 항상 `False` (실제 휴면 고래 감지 미구현)

**한계점**:
- Coin Metrics 무료 API는 **1일(`1d`) 주기만 지원** — 시간별 데이터 불가
- 봇이 1시간마다 실행되지만 온체인 데이터는 하루 1번만 갱신됨
- 시간별 온체인 데이터 필요 시: CryptoQuant (유료) 또는 Glassnode (유료) 고려

---

### Phase 9: GCP 프로덕션 배포 ✅
**Status**: ✅ Complete (2026-02-17)
**Goal**: GCP Cloud Run에 프로덕션 배포 + Cloud Scheduler 자동 실행

- [x] GCP 프로젝트 생성: `crypto-volatility-bot` (ID: 834326073484)
- [x] 계정 인증: `bluezero02@gmail.com`
- [x] 결제 계정 연결: `01FF45-267DE4-F9D403`
- [x] 필수 API 활성화 (Cloud Run, Cloud Build, Secret Manager, Cloud Scheduler, Container Registry)
- [x] Secret Manager 등록: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [x] IAM 권한 설정 (Cloud Build SA → Cloud Run Admin, Secret Accessor)
- [x] Cloud Build 실행 (테스트 통과 → 빌드 → 배포)
- [x] Cloud Run 배포 성공
- [x] Cloud Scheduler 설정 (매시간 정각, KST)
- [x] Telegram Webhook 등록
- [x] Health check 정상: `{"status": "ok"}`
- [x] Scheduled run 정상: `{"ok": true, "count": 2}`
- [x] Telegram 메시지 수신 확인

**배포 정보**:
- **Service URL**: `https://crypto-volatility-bot-834326073484.asia-northeast3.run.app`
- **리전**: `asia-northeast3` (서울)
- **스케줄**: `0 * * * *` (매시간 정각, KST)
- **예상 월 비용**: ~$0.32~$0.50

**배포 중 수정사항**:
- `Dockerfile`: test 스테이지에 `requirements.txt` 복사 누락 수정
- `deploy/gcp/cloudbuild.yaml`: `$COMMIT_SHA` → `_TAG` 대체변수 (수동 빌드 호환)
- Cloud Run `--allow-unauthenticated` 플래그 추가

---

## 최종 디렉토리 구조

```
crypto-volatility-bot/
  app/
    __init__.py
    main.py                          # FastAPI 서버 진입점 (Uvicorn, port 8080)
    pipeline.py                      # 분석 파이프라인 핵심 로직
    bot/
      __init__.py
      webhook_server.py              # FastAPI Webhook 라우트
      scheduler_state.py             # 스케줄 간격 상태 관리
    analyzers/
      __init__.py
      base.py                        # BaseAnalyzer ABC + AnalysisResult
      technical_analyzer.py          # YAML 설정 기반 동적 지표 실행
      indicators/                    # 지표 플러그인 디렉토리 (순수 pandas/numpy)
        __init__.py                  # 지표 레지스트리
        atr.py                       # ATR 계산
        bollinger_width.py           # 볼린저밴드 폭
        cvi.py                       # Chaikin Volatility Index
        historical_volatility.py     # 수익률 표준편차
        volume_spike.py              # 거래량 스파이크
      onchain_analyzer.py            # 거래소 유출입 + 고래 감지
      sentiment_analyzer.py          # Fear & Greed + 변동성 부스트
      score_aggregator.py            # 가중 최종 점수 + Alert level
    data/
      __init__.py
      data_collector.py              # CCXT, Coin Metrics, Fear & Greed API
    notifiers/
      __init__.py
      message_formatter.py           # 4종 메시지 템플릿
      telegram_notifier.py           # 텔레그램 전송 + 재시도
    utils/
      __init__.py
      config.py                      # 환경 변수 설정
      logger.py                      # JSON 구조화 로깅
  tests/
    conftest.py                      # OHLCV fixture 생성기
    unit/ (12+ test files)
    integration/
    e2e/ (test_main_entrypoint.py)
  deploy/
    gcp/ (cloudbuild.yaml + README.md)
    aws/ (README.md)
  config/
    technical.yaml                   # 기술적 지표 설정 (가중치, 범위, 임계값)
  docs/
    plans/
      PLAN_crypto-volatility-bot.md  # 이 파일
      PLAN_gcp-deployment.md         # GCP 배포 계획서
  Dockerfile                         # Multi-stage (test + production)
  docker-compose.yml
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  .env.example
  .gitignore
  README.md
```

---

## ⚠️ Risk Assessment

| 리스크 | 확률 | 영향 | 상태 | 완화 전략 |
|--------|------|------|------|----------|
| ~~pandas-ta Python 3.14 미지원~~ | - | - | ✅ 해결 | 순수 pandas/numpy로 직접 구현 |
| ~~CryptoQuant API 의존~~ | - | - | ✅ 해결 | Coin Metrics Community API로 마이그레이션 |
| **온체인 데이터 1일 단위 제한** | 높음 | 중간 | ⚠️ 알려진 한계 | 시간별 필요 시 CryptoQuant/Glassnode 유료 API 고려 |
| **고래 감지 정확도 낮음** | 높음 | 중간 | ⚠️ 알려진 한계 | 총 유동량 기반 추정 → 전용 고래 추적 API 필요 |
| Fear & Greed API 다운 | 낮음 | 낮음 | ✅ 대응됨 | None → neutral 폴백 |
| 텔레그램 Rate Limiting | 중간 | 낮음 | ✅ 대응됨 | 심볼당 1시간 1메시지 제한 |
| 변동성 점수 캘리브레이션 부정확 | 중간 | 중간 | 📊 모니터링 중 | 1주 운영 후 정규화 범위 조정 |
| GCP 비용 초과 | 낮음 | 낮음 | ✅ 대응됨 | 예상 월 ~$0.50, Budget Alert 설정 권장 |

---

## 🔄 Rollback Strategy

각 Phase 완료 시 git tag 생성: `phase-1-complete` ~ `phase-7-complete`

**GCP 배포 롤백**:
```bash
# 이전 리비전으로 트래픽 전환
gcloud run services update-traffic crypto-volatility-bot \
  --to-revisions=PREVIOUS_REVISION=100 --region=asia-northeast3
```

---

## 📊 Progress Tracking

| Phase | 예상 시간 | 상태 |
|-------|----------|------|
| Phase 1: 스켈레톤 + 설정 | 2-3시간 | ✅ |
| Phase 2: 기술적 분석 | 3-4시간 | ✅ |
| Phase 3: 온체인 + 감성 | 3-4시간 | ✅ |
| Phase 4: 데이터 수집 + 집계 | 3-4시간 | ✅ |
| Phase 5: 텔레그램 알림 | 3-4시간 | ✅ |
| Phase 6: 파이프라인 통합 | 3-4시간 | ✅ |
| Phase 7: Docker + 배포 설정 | 3-4시간 | ✅ |
| Phase 8: Coin Metrics 마이그레이션 | 1-2시간 | ✅ |
| Phase 9: GCP 프로덕션 배포 | 1-2시간 | ✅ |

---

## 📝 Notes & Learnings

### 구현 관련
- **Python 3.14 이슈**: pandas-ta가 Python 3.14 미지원 → 순수 pandas/numpy로 5개 지표 직접 구현
- **numpy 2.x**: Python 3.14에서 numpy 2.4.2 (cp314 wheel) 사용 가능
- **구현 완료**: 105개 테스트, 88% 커버리지, ruff+mypy 통과
- **git tags**: phase-1-complete ~ phase-7-complete

### API 마이그레이션
- **CryptoQuant → Coin Metrics**: API 키 불필요, 무료, 안정적
- **Coin Metrics 온체인 메트릭**: `FlowInExNtv`, `FlowOutExNtv`, `AdrActCnt`
- **한계**: Coin Metrics Community API는 `1d` (일간) 주기만 지원 — `1h` 시간별 불가
- 시간별 온체인 데이터 대안: CryptoQuant (유료), Glassnode (유료), Coin Metrics Pro (유료)

### GCP 배포
- **Dockerfile 수정**: test 스테이지에서 `requirements.txt`도 함께 COPY 필요 (requirements-dev.txt가 `-r requirements.txt` 참조)
- **cloudbuild.yaml**: `$COMMIT_SHA`는 수동 빌드 시 비어있음 → `_TAG` 대체변수 사용
- **gcloud CLI (Windows)**: 경로에 공백 포함 → Python subprocess로 우회 실행
- **IAM 권한**: Cloud Build SA에 `roles/run.admin` + `roles/iam.serviceAccountUser` 필요
- **Secret Manager**: 6개까지 무료, Cloud Run 서비스에 `--set-secrets`로 주입

### 서비스 정보
| 항목 | 값 |
|------|-----|
| GCP 프로젝트 ID | `crypto-volatility-bot` |
| 프로젝트 번호 | `834326073484` |
| Cloud Run URL | `https://crypto-volatility-bot-834326073484.asia-northeast3.run.app` |
| 리전 | `asia-northeast3` (서울) |
| Scheduler | `crypto-bot-hourly` (매시간 정각, KST) |
| 계정 | `bluezero02@gmail.com` |

---

## 📚 References

- [기획서](../../crypto-volatility-bot-plan.md)
- [CCXT Documentation](https://docs.ccxt.com/)
- [Coin Metrics Community API](https://community-api.coinmetrics.io/v4)
- [python-telegram-bot Docs](https://docs.python-telegram-bot.org/)
- [Fear & Greed Index API](https://alternative.me/crypto/fear-and-greed-index/)
- [GCP Cloud Run Docs](https://cloud.google.com/run/docs)
- [GCP Cloud Scheduler Docs](https://cloud.google.com/scheduler/docs)

---

## ✅ Final Checklist

- [x] 7개 구현 Phase 모두 완료 + Quality Gate 통과
- [x] Coin Metrics API 마이그레이션 완료
- [x] 전체 통합 테스트 수행
- [x] 전체 커버리지 ≥ 80% (88% 달성)
- [x] Docker 이미지 빌드 + 실행 성공
- [x] GCP Cloud Run 프로덕션 배포 완료
- [x] Cloud Scheduler 자동 실행 확인 (매시간 정각)
- [x] Telegram Webhook 등록 + 메시지 수신 확인
- [x] README.md 완성
- [ ] 1주간 실전 모니터링 후 캘리브레이션
- [ ] Budget Alert 설정 (월 $5 상한선 권장)

---

**Plan Status**: ✅ 구현 + 배포 완료
**Next Action**: 1주간 모니터링 → 변동성 점수 캘리브레이션 → 온체인 데이터 시간별 업그레이드 검토
**Blocked By**: None

---

## 🔮 향후 개선 사항 (우선순위)

1. **온체인 데이터 시간별 업그레이드** — CryptoQuant/Glassnode 유료 API로 1h 주기 데이터
2. **실제 고래 감지** — 대형 거래 추적 API 연동 (현재는 유동량 기반 추정)
3. **알트코인 추가** — SOL, ADA, BNB 등
4. **웹 대시보드** — Next.js 기반 시각화
5. **백테스팅 시스템** — 변동성 점수 정확도 검증
6. **추가 알림 채널** — Discord, Slack
