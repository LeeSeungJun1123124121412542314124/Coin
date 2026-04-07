# 크립토 인사이트 대시보드 — 기존 봇과 접목 계획

## Context

**문제**: 두 개의 프로젝트가 존재한다.
- **프로젝트 A** (`crypto-volatility-bot`): Python FastAPI 기반 변동성 분석 봇. GCP Cloud Run 배포 완료. 12+ 기술적 지표, 온체인/감성 분석, 텔레그램 알림.
- **프로젝트 B** (기획서만 존재): "크립토 인사이트 대시보드" 웹앱. 8개 탭, React+TypeScript 프론트엔드, 15+ 외부 API 연동.

**목표**: 기존 봇(A)의 분석 엔진을 활용하면서 대시보드(B)를 구현하여, 하나의 통합 시스템으로 만든다.

---

## 멀티레이어 분석 시스템 — 예측 정확도 분석

### 5개 분석 레이어 구조

전체 시스템은 **서로 다른 시간축과 성격의 데이터**를 계층적으로 결합한다. 단일 지표가 아닌 다중 레이어가 같은 방향을 가리킬 때 시그널을 발생시키는 구조.

```
[L1. 매크로 유동성 — 주~월 단위]
  TGA 잔고 변화 → 유동성 공급/흡수 방향
  M2 YoY → 글로벌 유동성 사이클 (BTC 상관계수 ~0.85, 약 10주 래그)
  국채 발행/경매 → 유동성 흡수 이벤트
  연준 SOMA 보유량 → QT/QE 방향

[L2. 시장 환경 — 일~주 단위]
  VIX / DXY / S&P500 / Gold → 리스크온/오프
  김치프리미엄 → 한국 시장 과열도
  크립토/KRX 거래량 비율 → 투기 심리 지표

[L3. 포지셔닝 — 일 단위]
  OI + FR → 포지션 흐름 분류 (SPF)
  CVD → 실제 매수/매도 체결 불균형
  CVD 11팩터 스크리너 → 알트코인 진입 타이밍

[L4. 스마트머니 — 실시간~2시간]
  HL 고래 포지션 변화 → 큰손 방향
  거래소 BTC 유입/유출 (온체인) → 매도/보유 의향

[L5. 기술적 확인 — 시간 단위]
  기존 봇 12+ 지표 → 변동성 + 방향 태깅
  RSI 다이버전스 / MACD / BB → 과열/과매도
  Fear & Greed → 군중 극단값
```

### 각 레이어의 역할

- **L1 매크로**: 큰 방향의 틀 — "지금이 유동성 확장기인가 축소기인가"
- **L2 환경**: 크로스마켓 컨텍스트 — "전통 시장이 리스크오프 모드인가"
- **L3 포지셔닝**: 시장 구조 — "누가 어디에 베팅하고 있는가"
- **L4 스마트머니**: 선행 지표 — "큰손들이 실제로 무엇을 하고 있는가"
- **L5 기술적**: 타이밍 확인 — "진입/청산의 시점이 지금인가"

### 강한 시그널 조합 예시

**하락 합의 시그널:**
```
L1 매크로:  TGA 증가 (유동성 흡수) + M2 YoY 둔화
L2 환경:   VIX 30+ + DXY 상승 + 크립토/KRX 비율 급등
L3 포지션: OI 3일 +20% 급등 + FR 과열 + CVD 하락 다이버전스
L4 스마트: HL 고래 롱 축소 + 거래소 BTC 유입 증가
L5 기술적: 봇 EMERGENCY + RSI 70+ + BB 상단 이탈
→ 5개 레이어 동시 합의 → 고신뢰 하방 시그널
```

**반등 합의 시그널:**
```
L1 매크로:  TGA 감소 (유동성 공급) + M2 YoY 반등
L2 환경:   VIX 하락 + DXY 하락 + Gold 안정
L3 포지션: OI 감소 + FR 음수 (숏 과밀집) + CVD 상승 다이버전스
L4 스마트: HL 고래 롱 증가 + 거래소 BTC 유출
L5 기술적: RSI 30 이하 + BB 하단 이탈 + 감성 극단적 공포
→ 5개 레이어 동시 합의 → 고신뢰 반등 시그널
```

### 예측 정확도 추정

| 시그널 유형 | 정확도 | 발생 빈도 | 설명 |
|---|---|---|---|
| **5개 레이어 합의** | **75-85%** | 월 1-2회 | 매크로+환경+포지셔닝+스마트머니+기술적 모두 동일 방향 |
| **3개 이상 레이어 합의** | **65-72%** | 월 3-5회 | 실전 참고에 충분한 신뢰도 |
| **매크로+포지셔닝 조합** (L1+L3) | **62-68%** | 주 1-2회 | 중기 방향 판단에 유용 |
| **극단 이벤트** (OI 폭등 + CVD 역행 + 고래 청산) | **80-88%** | 분기 2-3회 | 드물지만 높은 가치 |
| **일반 구간** (뚜렷한 시그널 없음) | **52-55%** | 전체의 ~60% | "시그널 없음" 자체가 유용한 정보 |

> **핵심 원칙: "항상 맞추는 시스템"이 아니라 "확신할 때만 말하는 시스템"**
> 정확도가 높을수록 발생 빈도가 낮아지는 건 피할 수 없으나, 이것이 오히려 장점.
> 매일 방향을 맞추려는 시스템보다 "지금 조심해야 할 때"를 확실히 알려주는 시스템이 실전 가치가 높다.

### 예측 한계 (솔직한 평가)

| 한계 | 설명 |
|---|---|
| **외부 충격 예측 불가** | 규제 폭탄, 거래소 해킹, 전쟁 등 — 어떤 기술적 분석으로도 불가능 |
| **매크로 데이터 후행성** | FRED 데이터 1-2주 지연 반영. 실시간 매크로 판단에는 한계 |
| **기획서 수치 할인 필요** | "88% 하락 확률" 등은 특정 기간 백테스트 결과 → 실전에서 10-15%p 할인 |
| **패턴 매칭 과적합 위험** | 코사인 유사도 0.9+ 필터 시 매칭 샘플 5개 미만 → 통계적 의미 약함 |
| **합의 시그널 희소성** | 모든 레이어 합의 시점은 드물어, 대부분의 기간은 "판단 불가" 구간 |

### 정확도 향상 전략

1. **백테스트 선행**: 기존 봇의 BacktestEngine으로 SPF 패턴을 과거 500일 데이터에 검증 → 실제 적중률 확인 후 파라미터 튜닝
2. **적중률 투명 공개**: predictions 테이블에 예측 결과(hit/miss)를 자동 기록하여 누적 성적표 제공
3. **레이어별 가중치 학습**: 초기 균등 가중치 → 3개월 운영 데이터 축적 후 레이어별 기여도 분석 → 가중치 조정
4. **시그널 없음 활용**: 뚜렷한 합의가 없는 60% 구간에서는 "중립/관망" 표시 → 오신호 방지

---

## 텔레그램 메시지 체계 (6종)

기존 봇의 단순 4종 메시지(정기/긴급/고래/일간)를 멀티레이어 분석에 맞게 재설계.

### 발송 조건 요약

| 메시지 유형 | 발송 조건 | 빈도 |
|---|---|---|
| 멀티레이어 합의 알림 | 3개+ 레이어 동일 방향 감지 시 | 월 3-5회 |
| 극단 이벤트 경고 | OI 3일 +10% 이상 + 추가 확인 1개+ | 월 1-2회 |
| 데일리 브리핑 | 매일 09:00 KST | 매일 |
| SPF 예측 발표 | 매일 00:30 UTC | 매일 |
| 매크로 전환 알림 | TGA/M2 추세 방향 전환 감지 시 | 월 1-2회 |
| 주간 성적표 | 매주 일요일 21:00 KST | 주 1회 |

### 1. 멀티레이어 합의 알림 (3개+ 레이어 동의 시)

```
🔴 하락 합의 시그널 [4/5 레이어]
━━━━━━━━━━━━━━━━━━━━
BTC $83,420 (-2.1%)

📊 레이어 분석
  매크로   🔴 TGA +$47B (유동성 흡수) / M2 YoY 둔화
  시장환경  🔴 VIX 32.4 / DXY 105.2↑ / 리스크오프
  포지셔닝  🔴 OI 3일 +18% 급등 / FR 0.031% 과열
  스마트머니 ⚪ 고래 포지션 변화 미미
  기술적   🔴 봇 78점 HIGH / RSI 74 / BB 상단 이탈

🎯 종합 판단: 강한 하방 압력
  신뢰도: 72% | 합의 레이어: 4/5
  유사 패턴 3일 후: 평균 -4.2% (5건 중 4건 하락)

💡 DCA 계수: 0.3x (대폭 축소 권장)
```

```
🟢 반등 합의 시그널 [3/5 레이어]
━━━━━━━━━━━━━━━━━━━━
BTC $67,850 (-8.3% from ATH)

📊 레이어 분석
  매크로   🟢 TGA -$62B (유동성 공급) / M2 반등 시작
  시장환경  ⚪ VIX 22.1 / DXY 보합
  포지셔닝  🟢 OI 감소 + FR -0.018% (숏 과밀집)
  스마트머니 🟢 고래 3명 롱 진입 / 거래소 BTC 유출 +2,400 BTC
  기술적   ⚪ 봇 45점 MEDIUM / RSI 32

🎯 종합 판단: 반등 가능성 높음
  신뢰도: 65% | 합의 레이어: 3/5

💡 DCA 계수: 1.5x (확대 고려)
```

### 2. 극단 이벤트 경고 (OI 폭등 + 다중 확인)

```
⚠️ 극단 이벤트 경고 — OI 급등
━━━━━━━━━━━━━━━━━━━━
BTC $91,200 | OI $48.2B (+27% 3일)

🚨 위험 요인
  • OI 3일 +27% → 역사적 상위 3% 수준
  • FR 0.045% → 롱 과밀집 극단
  • CVD 하락 다이버전스 → 실제 매수세 동반 안됨
  • 고래 2명 롱 청산 시작

📈 과거 유사 패턴 (유사도 92%+)
  2025-11-14: 3일 후 -7.2%
  2025-08-03: 3일 후 -5.8%
  2025-05-21: 3일 후 -11.4%
  → 3일 내 하락 확률: 83% (6건 중 5건)

💡 신규 롱 진입 자제 / 기존 포지션 헷지 고려
```

### 3. 데일리 브리핑 (매일 09:00 KST)

```
📋 데일리 브리핑 — 2026.04.07 (월)
━━━━━━━━━━━━━━━━━━━━
BTC $84,520 (+1.2%) | 공포탐욕 34 (공포)

🌐 매크로
  TGA: $841B (주간 -$23B, 유동성 공급↑)
  M2 YoY: +3.2% (3개월 연속 상승)
  국채 경매: 내일 10Y $42B 예정

📈 시장 환경
  S&P +0.4% | NASDAQ +0.6% | VIX 19.8
  DXY 103.2 | Gold $2,340 | 10Y 4.21%
  김프: +1.8% | 크립토/KRX: 12.3%

📊 포지셔닝
  OI: $42.1B (+2.3%) | FR: 0.008% (정상)
  흐름: long_entry | CVD: 상승 추세 유지

🐋 스마트머니
  고래 TOP5: 롱 3 / 숏 1 / 중립 1
  거래소 BTC: 24h 순유출 -820 BTC

🔧 기술적 (봇)
  변동성: 52점 MEDIUM | RSI: 48 | 방향: NEUTRAL

🎯 종합: 중립~약간 긍정 (합의 2/5)
  오늘 주시: 10Y 국채 경매 결과, VIX 방향
```

### 4. SPF 예측 발표 (매일 00:30 UTC)

```
🔮 SPF 3일 예측 — 2026.04.07
━━━━━━━━━━━━━━━━━━━━
BTC $84,520

예측: 🟢 반등 예상
  신뢰도: 68% | 상승 64% / 하락 36%

근거:
  1. OI 안정화 + FR 정상 → 레버리지 해소 완료
  2. CVD 3일 연속 상승 → 실매수세 유입
  3. 공포탐욕 34 → 역발상 구간

유사 패턴 TOP 3:
  2025-12-08 (94%): +3.1% / +5.4% / +7.2%
  2025-09-15 (91%): +1.8% / +2.9% / +4.1%
  2025-06-22 (90%): -0.4% / +1.2% / +3.8%

📊 어제 예측: ✅ 적중 (예측 하락 → 실제 -2.1%)
  누적: 42전 27승 15패 (64.3%)
```

### 5. 매크로 전환 알림 (TGA/M2 추세 변화 시)

```
🏛️ 매크로 유동성 전환 감지
━━━━━━━━━━━━━━━━━━━━
TGA 추세 전환: 증가 → 감소
  현재: $841B | 7일 변화: -$23B
  해석: 유동성 공급 시작 → 위험자산에 긍정적

M2 YoY: +3.2% (3개월 연속 상승)
  BTC-M2 상관: 0.85 (10주 래그)
  시사점: 10주 후 BTC 상승 압력 예상

📅 이번 주 주요 일정
  04/08 (화) 3Y 국채 경매 $58B
  04/09 (수) FOMC 의사록 공개 ★★★
  04/11 (금) CPI 발표 ★★★
```

### 6. 주간 성적표 (매주 일요일 21:00 KST)

```
📊 주간 성적표 — W14 (03.31~04.06)
━━━━━━━━━━━━━━━━━━━━
BTC: $81,200 → $84,520 (+4.1%)

🎯 예측 성과
  SPF 예측: 5전 3승 2패 (60%)
  합의 시그널: 2건 발생, 2건 적중 (100%)
  극단 경고: 0건

📊 레이어별 정확도 (누적)
  매크로:   방향 일치 71% (42주)
  포지셔닝: 방향 일치 63% (180일)
  기술적:   시그널 적중 58% (누적)
  종합 합의: 적중 74% (누적 38건)

🐋 고래 동향 (주간 요약)
  TOP10 포지션 변화: 롱 6→4 / 숏 2→4 / 중립 2→2
  주요 이동:
    [James_HL] BTC 롱 $8.2M 전량 청산 → ETH 숏 $3.1M
    [Whale_0x7a] BTC 롱 60% 축소 ($5.4M → $2.1M)
  → 큰손 롱 비중 축소 추세

💡 다음 주 주시
  • TGA 감소 추세 지속 → 유동성 환경 우호적
  • CVD 스크리너 S등급: INJ (진입 고려)
  • FOMC 의사록 + CPI 발표 예정
```

### 구현 시 수정 파일

**기존 봇 수정:**
- `app/notifiers/message_formatter.py` — 기존 4종 → 6종 메시지 템플릿으로 교체
- `app/notification_dispatcher.py` — 발송 조건 로직 재설계 (레이어 합의 판단, 스케줄 분기)
- `app/bot/webhook_server.py` — 신규 스케줄 엔드포인트 추가 (`/scheduled-daily`, `/scheduled-weekly`)

**신규:**
- `dashboard/backend/services/consensus_engine.py` — 5개 레이어 합의 판단 + 신뢰도 산출
- `dashboard/backend/services/message_builder.py` — 각 레이어 데이터를 수집하여 메시지 조립

**스케줄 추가:**
- apscheduler 내장: 데일리 브리핑 (09:00 KST), 주간 성적표 (일 21:00 KST)

---

## 핵심 아키텍처 결정

### 1. 백엔드: Python FastAPI 확장 (Node.js 대신)

기획서는 Node.js+Express를 명시했으나, **기존 봇이 Python**이므로 FastAPI를 확장한다.

**이유:**
- 봇의 분석 엔진(TechnicalAnalyzer, 12+ 지표, ScoreAggregator)을 in-process로 직접 호출 가능
- Binance/Fear&Greed 등 공통 API 호출을 하나의 프로세스에서 캐싱하여 중복 제거
- 프론트엔드 빌드 결과물도 FastAPI에서 정적 서빙 → 서비스 하나로 통합
- 프론트엔드는 JSON API만 호출하므로 백엔드 언어에 무관

### 2. 배포 구조 — Railway 단일 플랫폼 ($5/월)

```
Railway ($5/월 Hobby 플랜)
  ├── FastAPI 서비스 (백엔드 API + 프론트 정적 파일 서빙)
  │     ├── 기존 봇 파이프라인 (in-process)
  │     ├── 텔레그램 알림 (기존)
  │     ├── 스케줄러 (apscheduler, 앱 내장)
  │     └── React 빌드 결과물 서빙 (StaticFiles)
  └── SQLite (/data/crypto.db, Railway Volume 마운트로 영구 저장)
```

기존 GCP(Cloud Run, Cloud Scheduler, Secret Manager)에서 **Railway로 전면 이전**.
- git push → 자동 배포
- 환경변수는 Railway 대시보드에서 관리
- Cloud Scheduler 대신 앱 내장 apscheduler로 스케줄 작업 실행
- Vercel 불필요 — FastAPI `StaticFiles`로 프론트 직접 서빙

### 3. 봇 엔진 재활용 지점

| 대시보드 탭 | 재활용하는 봇 모듈 |
|---|---|
| 탭 1 대시보드 | `DataCollector.fetch_fear_greed()`, `indicators/rsi.py` |
| 탭 2 볼륨 트래커 | `indicators/rsi.py` (주간/일간 RSI 계산) |
| 탭 3 SPF | `analysis_history` 테이블에서 봇 점수 조회 → bearish_score 보정 |
| 탭 5 시장 분석 | `run_analysis()` 결과를 `analysis_history`에서 읽어 시계열 차트 |
| 탭 7 CVD 스크리너 | `indicators/bollinger_bands.py`, `indicators/rsi.py` |

---

## 프로젝트 구조

```
e:/Dev/coin/
├── crypto-volatility-bot/          # 기존 봇 (수정 최소화)
│   ├── app/                        # 분석 엔진 → 대시보드에서 import
│   ├── config/
│   └── ...
│
├── dashboard/                      # 신규
│   ├── backend/
│   │   ├── api/                    # FastAPI 라우터 (탭별)
│   │   │   ├── dashboard_routes.py    # GET /api/dashboard
│   │   │   ├── volume_routes.py       # GET /api/data, /weekly-all 등
│   │   │   ├── spf_routes.py          # GET /api/spf-data
│   │   │   ├── research_routes.py     # GET /api/research
│   │   │   ├── market_routes.py       # GET /api/insights
│   │   │   ├── liquidity_routes.py    # GET /api/tga-*, /m2-yoy 등
│   │   │   ├── cvd_routes.py          # GET /api/cvd
│   │   │   ├── whale_routes.py        # GET /api/hyperliquid-whales
│   │   │   └── visitor_routes.py      # GET /api/visitor-count
│   │   ├── collectors/             # 대시보드 전용 데이터 수집기
│   │   │   ├── coingecko.py           # 코인 가격 6종
│   │   │   ├── yahoo_finance.py       # 미국 시장 지표
│   │   │   ├── binance_derivatives.py # OI/FR/롱숏 비율
│   │   │   ├── upbit.py               # 업비트 거래량
│   │   │   ├── bithumb.py             # 빗썸 거래량
│   │   │   ├── fred.py                # TGA/M2/SOMA
│   │   │   ├── treasury.py            # 국채 경매 일정
│   │   │   ├── hyperliquid.py         # HL 고래 리더보드
│   │   │   └── exchange_rate.py       # USD/KRW 환율
│   │   ├── services/               # 비즈니스 로직
│   │   │   ├── spf_service.py         # 포지션 흐름 분류 + 예측
│   │   │   ├── cvd_service.py         # CVD 계산 + 멀티팩터 스크리너
│   │   │   ├── market_insight.py      # AI 인사이트 생성
│   │   │   └── kimchi_premium.py      # 김치 프리미엄 계산
│   │   ├── jobs/                   # 스케줄 작업
│   │   │   ├── collect_spf.py         # 매일 00:10
│   │   │   ├── collect_volume.py      # 매일 09:10 (KRX 마감 후)
│   │   │   ├── update_predictions.py  # 매일 00:30
│   │   │   └── collect_whales.py      # 2시간마다
│   │   ├── db/
│   │   │   ├── connection.py          # sqlite3 커넥션 관리
│   │   │   └── schema.sql             # 전체 테이블 정의
│   │   ├── cache.py                # TTL 기반 인메모리 캐시
│   │   └── main.py                 # 봇 앱 + 대시보드 라우터 통합
│   │
│   └── frontend/                   # React 19 + TypeScript + Vite + Tailwind
│       ├── src/
│       │   ├── components/screens/    # Dashboard, Volume, SPF 등 8개 탭
│       │   ├── components/shared/     # Card, StatCard, GaugeChart, PinScreen 등
│       │   ├── components/charts/     # SparklineChart, RSIChart 등
│       │   ├── hooks/useApi.ts
│       │   ├── lib/api.ts
│       │   └── App.tsx
│       ├── vite.config.ts
│       └── package.json
│
└── docs/                           # 기존 문서
```

---

## DB — SQLite + Railway Volume

**파일 위치**: `/data/crypto.db` (Railway Volume 마운트)
**별도 DB 서비스 불필요** → Railway 비용 절감, 백업은 파일 복사로 끝

Railway Volume 설정:
```
Railway 대시보드 → 서비스 → Settings → Volumes
  Mount Path: /data
```

### 스키마

```sql
-- SPF 레코드 (탭 3)
CREATE TABLE spf_records (
  date            TEXT PRIMARY KEY,
  oi              REAL,
  fr              REAL,
  price           REAL,
  oi_change_3d    REAL,
  oi_change_7d    REAL,
  oi_change_14d   REAL,
  price_change_3d REAL,
  cum_fr_3d       REAL,
  cum_fr_7d       REAL,
  cum_fr_14d      REAL,
  flow            TEXT,
  bearish_score   INTEGER,
  bullish_score   INTEGER,
  oi_consecutive_up INTEGER,
  oi_surge_alert  TEXT,
  price_after_3d  REAL,
  price_after_7d  REAL,
  price_after_14d REAL
);

-- 예측 기록 (탭 3)
CREATE TABLE predictions (
  date          TEXT PRIMARY KEY,
  direction     TEXT,
  direction_raw TEXT,
  confidence    INTEGER,
  bullish_score INTEGER,
  bearish_score INTEGER,
  up_prob       INTEGER,
  down_prob     INTEGER,
  top_patterns  TEXT,  -- JSON 문자열
  reasons       TEXT,  -- JSON 문자열
  actual_price_3d REAL,
  result        TEXT
);

-- 리서치 글 (탭 4)
CREATE TABLE research_posts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  badge         TEXT,
  title         TEXT,
  subtitle      TEXT,
  category      TEXT,
  content       TEXT,
  views         INTEGER DEFAULT 0,
  read_time     INTEGER,
  published_at  TEXT DEFAULT (datetime('now'))
);

-- 방문자 (카운터)
CREATE TABLE visitors (
  date        TEXT PRIMARY KEY,
  today_count INTEGER DEFAULT 0,
  total_count INTEGER DEFAULT 0
);

-- 거래량 히스토리 (탭 2)
CREATE TABLE volume_daily (
  date         TEXT PRIMARY KEY,
  upbit_krw    REAL,
  bithumb_krw  REAL,
  krx_krw      REAL,
  crypto_ratio REAL
);

-- 고래 스냅샷 (탭 8)
CREATE TABLE whale_snapshots (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  captured_at   TEXT DEFAULT (datetime('now')),
  address       TEXT,
  nickname      TEXT,
  account_value REAL,
  pnl           REAL,
  roi           REAL,
  positions     TEXT  -- JSON 문자열
);

-- 봇 분석 히스토리 (탭 5 + SPF 보정용 — 핵심 브릿지 테이블)
CREATE TABLE analysis_history (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol       TEXT,
  timestamp    TEXT DEFAULT (datetime('now')),
  final_score  REAL,
  alert_score  REAL,
  alert_level  TEXT,
  details      TEXT  -- JSON 문자열
);
```

`analysis_history`가 **봇과 대시보드를 연결하는 핵심 브릿지** — 봇이 매시간 분석 결과를 저장하고, 대시보드가 이를 읽어 시장 분석 차트와 SPF 보정에 사용.

---

## 구현 Phase

### Phase 0: 기반 구축 (Day 1-3)

**목표**: 모노레포 구조, DB, 통합 FastAPI 진입점 설정

**수정 파일:**
- `crypto-volatility-bot/requirements.txt` — httpx, cachetools, apscheduler 추가
- `crypto-volatility-bot/Dockerfile` — dashboard 디렉토리 포함, 진입점 변경

**신규 파일:**
- `dashboard/backend/main.py` — 봇의 `create_app()` 가져와서 대시보드 라우터 마운트
- `dashboard/backend/db/connection.py` — sqlite3 커넥션 관리 (WAL 모드)
- `dashboard/backend/db/schema.sql` — 전체 테이블 DDL (SQLite 문법)
- `dashboard/backend/cache.py` — TTL 기반 캐시 데코레이터
- `dashboard/frontend/` — Vite + React + Tailwind 스캐폴드

**핵심 작업:**
1. `dashboard/backend/main.py`에서 기존 봇의 `webhook_server.create_app()`을 import하고 대시보드 라우터 추가
2. `pipeline.py`의 `run_analysis()` 결과를 `analysis_history` 테이블에 저장하는 후크 추가
3. Railway Volume 마운트 설정 (`/data`), SQLite DB 초기화 (`/data/crypto.db`)
4. 프론트엔드 프로젝트 초기화 (`npm create vite@latest . -- --template react-ts`)

---

### Phase 1: 대시보드 탭 (Tab 1) — 메인 화면 (Day 4-8)

**목표**: BTC 가격, 공포탐욕 게이지, 미국 시장, 온체인 지표

**백엔드:**
- `collectors/coingecko.py` — 6개 코인 가격 (60초 캐시)
- `collectors/yahoo_finance.py` — 10개 미국 시장 티커 (300초 캐시)
- `collectors/binance_derivatives.py` — OI, FR, 롱/숏 비율
- `services/kimchi_premium.py` — 업비트 가격 + 환율 → 김프 계산
- `api/dashboard_routes.py` — `GET /api/dashboard` (봇의 `fetch_fear_greed()` 재활용)

**프론트엔드:**
- `App.tsx` — PIN 인증 + 8탭 내비게이션 + 다크 테마
- `PinScreen.tsx` — 4자리 PIN, shake 애니메이션
- `Dashboard.tsx` — Hero(BTC+공포탐욕), 코인 카드 6개, 미국 시장 10개, 온체인 8개, 캘린더
- 공용 컴포넌트: Card, StatCard, Badge, GaugeChart, SparklineChart

---

### Phase 2: SPF 탭 (Tab 3) — 핵심 차별화 기능 (Day 9-14)

**목표**: OI/FR 기반 포지션 흐름 분류, 3일 예측, 유사 패턴 매칭

**백엔드:**
- `collectors/binance_derivatives.py` 확장 — OI 500일 히스토리, FR 1500건 히스토리
- `services/spf_service.py`:
  - `classify_flow()` — 5종 분류 (long_entry/short_entry/long_exit/short_exit/neutral)
  - `calc_bearish_score()` / `calc_bullish_score()`
  - `find_similar_patterns()` — 코사인 유사도 패턴 매칭
  - `generate_prediction()` — 방향 + 신뢰도 + 근거
  - **봇 연동**: `analysis_history`에서 최신 `alert_level` 조회 → bearish_score에 +5~15 보정
- `jobs/collect_spf.py` — 매일 00:10 UTC, OI/FR/BTC 수집 → DB 저장
- `jobs/update_predictions.py` — 매일 00:30, 3일 전 예측 결과 판정
- `api/spf_routes.py` — `GET /api/spf-data`, `/prediction-history`, `/spf-refresh`

**프론트엔드:**
- `SPF.tsx` — 하락위험/반등 점수 카드, OI 경고 배너, 3일 예측, 성적표, 유사 패턴 TOP5, 지표 패널 9개, 복합 차트, 일별 해석 피드

---

### Phase 3: 볼륨 트래커 (Tab 2) + 시장 분석 (Tab 5) (Day 15-19)

**백엔드:**
- `collectors/upbit.py` — KRW 전체 마켓 거래대금 합산
- `collectors/bithumb.py` — 빗썸 전체 거래대금
- `jobs/collect_volume.py` — 매일 09:10 KST
- `api/volume_routes.py` — /api/data, /weekly-all, /btc-weekly-rsi, /btc-daily-rsi, /fear-greed
  - RSI 계산에 **봇의 `indicators/rsi.py` 재활용** (주간/일간 캔들 입력만 변경)
- `services/market_insight.py` — 규칙 기반 인사이트 생성 (봇의 AggregatedResult 활용)
- `api/market_routes.py` — /api/insights, /market-analysis

**프론트엔드:**
- `Volume.tsx` — 요약 카드 4개, 거래량 막대차트 60일, RSI 차트, 공포탐욕 추이
- `Market.tsx` — AI 인사이트, 핵심 지표, VIX vs BTC 변동성 차트

---

### Phase 4: 유동성 (Tab 6) + CVD (Tab 7) + 고래 (Tab 8) (Day 20-26)

**백엔드:**
- `collectors/fred.py` — TGA(WTREGEN), M2(M2SL), SOMA(WSHODLL 등) — FRED API 키 필요
- `collectors/treasury.py` — 국채 경매 일정, 발행량
- `api/liquidity_routes.py` — /api/tga-btc, /tga-yoy, /m2-yoy, /fed-purchases, /treasury-auctions
- `services/cvd_service.py` — CVD 계산 + 11팩터 스크리너 (**BB/RSI는 봇 지표 재활용**)
- `api/cvd_routes.py` — /api/cvd?symbol=INJ&interval=4h, /cvd-screener
- `collectors/hyperliquid.py` — 리더보드 + 포지션 조회
- `jobs/collect_whales.py` — 2시간마다
- `api/whale_routes.py` — /api/hyperliquid-whales

**프론트엔드:**
- `Liquidity.tsx` — TGA 카드, TGA YoY vs BTC 차트 (타임래그 슬라이더), M2 차트, 국채 경매 테이블
- `Alt.tsx` — 종목 탭, 주기 선택, CVD 차트, 멀티팩터 스코어 카드
- `Whale.tsx` — 고래 리더보드 테이블

---

### Phase 5: 리서치 (Tab 4) + 마무리 + 배포 (Day 27-32)

**백엔드:**
- `api/research_routes.py` — CRUD (조회수 증가, 관리자 글쓰기)
- `api/visitor_routes.py` — 방문자 카운터 upsert
- 전체 캐시 데코레이터 적용, 커넥션 풀 최적화, CORS 화이트리스트

**프론트엔드:**
- `Research.tsx` — 카드 그리드 + 모달 상세보기 + 우클릭/복사 방지
- 모바일 반응형, 로딩 스켈레톤, 에러 바운더리

**배포:**
- Railway 서비스 하나: FastAPI(백엔드 API + 프론트 정적 서빙) + SQLite(Volume)
- git push → 자동 빌드/배포 (프론트 빌드 → FastAPI StaticFiles 서빙)
- 스케줄 작업: apscheduler 앱 내장 (SPF 00:10, 볼륨 09:10 KST, 고래 2시간, 예측 00:30)
- 비용: Railway $5/월 Hobby 플랜 내 전부 포함

---

## 스케줄 작업 정리 (apscheduler 앱 내장)

Cloud Scheduler 대신 FastAPI 앱 안에서 `apscheduler`로 직접 실행. Railway 서비스 하나에서 전부 처리.

| 작업 | 스케줄 | 함수 |
|---|---|---|
| 봇 분석 | 매시간 정각 | `pipeline.run_analysis()` |
| 데일리 브리핑 | 매일 09:00 KST | `message_builder.daily_briefing()` |
| SPF 데이터 수집 | 매일 00:10 UTC | `jobs.collect_spf()` |
| SPF 예측 발표 | 매일 00:30 UTC | `jobs.publish_prediction()` |
| 거래량 수집 | 매일 09:10 KST (평일) | `jobs.collect_volume()` |
| 예측 결과 업데이트 | 매일 00:30 UTC | `jobs.update_predictions()` |
| 고래 스냅샷 | 2시간마다 | `jobs.collect_whales()` |
| 주간 성적표 | 매주 일요일 21:00 KST | `message_builder.weekly_report()` |

---

## 데이터 캐시 전략 (중복 호출 방지)

| 데이터 | TTL | 봇과 공유 여부 |
|---|---|---|
| 코인 가격 (CoinGecko) | 60초 | 대시보드 전용 |
| 미국 시장 (Yahoo) | 300초 | 대시보드 전용 |
| 공포탐욕 (Alternative.me) | 300초 | **공유** — 봇의 fetch_fear_greed() 재활용 |
| OI/FR 현재 (Binance) | 60초 | 대시보드 전용 |
| OI/FR 히스토리 | 3600초 | 대시보드 전용 |
| FRED 데이터 | 86400초 (1일) | 대시보드 전용 |
| 거래소 거래량 | 300초 | 대시보드 전용 |

---

## 추가 의존성

**Python (requirements.txt에 추가):**
```
httpx>=0.27.0         # async HTTP 클라이언트
cachetools>=5.3.0     # TTL 캐시
apscheduler>=3.10.0   # 앱 내장 스케줄러 (Cloud Scheduler 대체)
aiosqlite>=0.20.0     # SQLite async 래퍼 (선택, 동기 sqlite3도 가능)
```

**Frontend (package.json):**
```
react@19, react-dom@19, recharts@2, react-router-dom@7
typescript@5, vite@6, tailwindcss@4, @tailwindcss/vite@4
```

---

## 리스크

| 리스크 | 대응 |
|---|---|
| Yahoo Finance API 차단 | `yfinance` 패키지 폴백 또는 마지막 캐시값 표시 |
| CoinGecko 50콜/분 제한 | 60초 캐시 + 배치 요청 |
| Railway 슬립 후 첫 응답 느림 | 스케줄 작업이 주기적으로 깨우므로 실질적 영향 미미 |
| SPF 예측 정확도 초기 낮음 | "beta" 표시 + 적중률 투명 공개 |
| Railway $5 플랜 리소스 한계 | 512MB RAM, 월 500시간 — 스케줄 작업 주기적 실행으로 충분 |

---

## 검증 방법

1. **백엔드 단위**: 각 collector/service에 pytest 작성
2. **API 통합**: 각 엔드포인트 응답 구조 검증
3. **프론트엔드**: 브라우저에서 각 탭 데이터 로드 확인
4. **E2E**: 전체 파이프라인 — apscheduler → 수집 → DB 저장 → API → 프론트 표시
5. **봇 연동**: analysis_history 테이블에 봇 결과 저장 확인 → SPF/Market 탭에서 조회 확인
