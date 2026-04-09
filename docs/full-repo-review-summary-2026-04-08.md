# 전체 코드베이스 전수 점검 요약

작성일: 2026-04-08  
대상 범위: `d:\Dev\Coin` 전체 (실행 경로 중심 전수 스캔)

## 점검 범위

- 백엔드: `dashboard/backend`
- 봇 앱: `crypto-volatility-bot/app`
- 프론트엔드: `dashboard/frontend/src`
- 테스트/문서/설정: `tests`, `docs`, `deploy`, `*.env.example`, `pyproject.toml`

## 전체 결론

- 현재 구조는 기능적으로 잘 구성되어 있으며, 핵심 흐름(수집 → 분석 → 집계 → API/알림)은 일관적이다.
- 주요 리스크는 신규 기능 부족보다 **계약 불일치(코드-문서-테스트)**, **운영 시점 동시성/블로킹**, **관측성 부족**에 집중된다.

## 아키텍처 요약

- 통합 엔트리: `dashboard/backend/main.py`
  - FastAPI 라우터 등록
  - APScheduler 잡 등록
  - 봇 파이프라인 연계
- 분석 파이프라인: `crypto-volatility-bot/app/pipeline.py`
  - `DataCollector` 수집
  - `Onchain/Technical/Sentiment/DerivativesAnalyzer` 분석
  - `ScoreAggregator` 집계
- 알림: `crypto-volatility-bot/app/notification_dispatcher.py`
  - 이벤트 알림(`CONFIRMED_HIGH/HIGH/LIQUIDATION_RISK/WHALE`)
  - 정기 리포트(12시간)
- 프론트: `dashboard/frontend/src/components/screens/*`
  - 각 탭이 `/api/*`를 주기 폴링
  - `useApi` 훅으로 공통 fetch 처리

## 우선순위 이슈

### P0 (즉시 대응)

- 거래량 수집 잡의 타입 충돌 가능성
  - `dashboard/backend/jobs/collect_volume.py`
  - `dashboard/backend/collectors/upbit.py`
  - `fetch_krw_volume()` 반환형(dict)과 잡 내부 계산(숫자 가정) 사이 불일치 가능성.

### P1 (높은 우선순위)

- 심볼 단위 실패 격리 부족
  - `crypto-volatility-bot/app/pipeline.py`
  - 일부 심볼 예외가 전체 분석 루프에 전파될 위험.

- async 경로 내 동기 I/O 사용
  - `crypto-volatility-bot/app/data/data_collector.py`
  - `crypto-volatility-bot/app/bot/webhook_server.py`
  - `requests`/`time.sleep` 기반 경로로 이벤트루프 블로킹 가능.

- SQLite 단일 커넥션 공유 및 동시 잡 충돌 가능성
  - `dashboard/backend/db/connection.py`
  - `dashboard/backend/main.py`
  - 동시 write 상황에서 lock/경합 가능.

- 환경변수/거래소 키 명칭 혼재
  - 코드: `BYBIT_*` (`crypto-volatility-bot/app/utils/config.py`)
  - 문서/샘플: `BINANCE_*`, `CRYPTOQUANT_*` 혼재 (`README`, `.env.example`, `deploy/*`)

### P2 (중간 우선순위)

- 프론트 에러 표시 일관성 부족
  - `dashboard/frontend/src/components/screens/*`
  - 일부 화면은 API 실패를 로딩/빈 상태처럼 보이게 처리.

- SPF 화면의 파싱 안정성
  - `dashboard/frontend/src/components/screens/SPF.tsx`
  - JSON 파싱 예외가 렌더 실패로 이어질 수 있는 경로.

- 문서 API 경로 최신성 문제
  - `docs/*` 일부가 구 API 경로를 설명.

## 문서/테스트 관점 요약

- 테스트는 `crypto-volatility-bot/tests`에 집중되어 있으며, `dashboard` 측 테스트 공백이 크다.
- 문서와 실제 코드 간 불일치 포인트가 운영 설정(환경변수, 배포 핸들러, 엔드포인트)에서 다수 관찰된다.

## 권장 조치 순서

1. P0 타입 충돌 경로 수정 및 재발 방지 테스트 추가
2. 파이프라인 심볼 단위 예외 격리
3. 동기 I/O 경로 비동기화 또는 실행 분리
4. 설정 키/문서/예제 파일 표준화(BYBIT 기준 단일화 등)
5. 프론트 공통 에러 UI/재시도 UX 정리

## 비고

- 본 문서는 실행 경로 중심 전수 스캔 결과 요약이며, 라인 단위 코드 감사(audit) 문서는 아니다.
- 세부 수정안은 별도 핫픽스 문서로 분리하는 것을 권장한다.

