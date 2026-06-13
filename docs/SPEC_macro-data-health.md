# 스펙: 매크로 데이터 헬스 모니터

작성일: 2026-06-14
상태: 구현
배경: 복합 방향 모델(SPF·봇 리포트·리더보드 복합방향이 의존)은 9팩터 매크로/온체인 수집에 의존. 수집이 조용히 실패하면 **전부 neutral로 죽는데 아무도 모른다**(Avast TLS·API 장애 등). 이를 감지하는 헬스 패널.

## 보는 것
- **캐시 신선도**: `macro_cache.csv`(get_sources) 파일 mtime → 마지막 수집 후 경과 시간
- **소스별 최신성**: 9개 소스(close/eth/sol/net_liquidity/dxy/ust10y/vix/mvrv/active_addr) 각 마지막 데이터 날짜 + 며칠 지났나 (투명성용, 상태 판정엔 미사용 — FRED 주간 시리즈는 자연 지연)
- **복합 산출 가능 여부**: `latest_tilt(build_factors(...))`로 n_factors·z 확인 → 복합이 실제로 나오나

## 상태 판정 (단순)
- `no_data`: 캐시 파일 없음
- `stale`: 캐시 age > 48h **또는** 복합 산출 불가(n_factors < 6 / NaN)
- `warn`: 캐시 age > 30h
- `ok`: 그 외
(소스별 staleness는 표시만, 상태 게이팅엔 안 씀 — 오탐 방지)

## 구성
| 파일 | 작업 |
|---|---|
| `dashboard/backend/services/macro_health.py` | 신규 — `macro_health(cache_path, today)` 순수 함수(캐시 읽기 + 복합 점검) |
| `dashboard/backend/api/health_routes.py` | 신규 — `GET /api/macro-health` (경량, 무거운 의존 없음) |
| `dashboard/backend/main.py` | health_router 등록(인증) |
| `dashboard/frontend/src/components/shared/MacroHealthCard.tsx` | 신규 — 상태 배지 + 소스별 최신성 + 복합 상태 |
| `dashboard/frontend/src/components/screens/Dashboard.tsx` | 카드 배치 |

## 검증 (AC)
1. 캐시 없으면 `no_data`
2. 정상 캐시(400일·9소스)면 `ok` + composite.ok=true + series 9개
3. 짧은 캐시(워밍업 미달)면 composite.ok=false → `stale`
4. mtime 오래되면(>48h) `stale`
5. 경량 라우트라 로컬 임포트·테스트 가능
6. 대시보드 회귀 무파손 + 신규 단위테스트
