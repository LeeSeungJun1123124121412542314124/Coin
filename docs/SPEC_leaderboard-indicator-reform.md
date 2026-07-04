# 스펙: 리더보드 지표 개편 — 결합 지표 3종 + 표시 슬림화

작성일: 2026-07-04
상태: 구현 확정 (ouroboros seed_26afad3107f9, ambiguity 0.1)
관련: [SPEC_paper-trading-leaderboard.md](SPEC_paper-trading-leaderboard.md)

## 배경

리더보드 12개 지표가 화면에 너무 많고, 기술적 분석이 개별 지표로 흩어져 있어 한눈에 판단하기 어렵다는 사용자 피드백. 측정(포트폴리오)과 열람(표시)을 분리하고, 같은 질문에 답하는 지표끼리 결합 지표로 묶는다.

## 확정 요구사항

### 1. 리더보드 표시에서 제거 (6개)

| 지표 | 처리 |
|---|---|
| 매수보유 | **레지스트리 유지, 계속 매매**(벤치마크). leaderboard() 응답 행에서만 제외하되 vs_buyhold_pct 계산에는 계속 사용 |
| 달러·금리·TGA·모멘텀30d·RSI | INDICATORS 레지스트리에서 제거(매매 중단). DB 데이터(paper_portfolios/equity/positions 약 3주치)는 **보존**, leaderboard()가 현재 레지스트리 지표만 반환하도록 필터 |

### 2. 신규 결합 지표 3개 추가

| 지표 | 구성 | 근거 |
|---|---|---|
| 유동성 | 순유동성 + TGA | TGA는 순유동성 구성요소. 둘 다 "돈이 풀리나 잠기나" |
| 긴축환경 | 달러 + 금리 | 둘 다 리스크자산 역풍, 같은 국면 동행 |
| 과열회귀 | RSI + 볼린저밴드 | 둘 다 평균회귀 계열, 같은 장세에서 같은 말 |

- 결합 방식: **멤버 신호 스칼라 균등 산술평균** (추가 z 재정규화·롤링 창 없음, 복합방향 기존 패턴)
- NaN 정책: 유효 멤버만 부분평균, 전 멤버 NaN이면 신호 NaN
- 제거되는 지표의 신호 함수(`_tga_sig`, `_macro("dxy_13w")` 등)는 결합 재료로 필요하므로 **함수 삭제 금지**, 레지스트리 등록만 해제
- TGA는 부호 −1이 신호에 이미 반영됨 — 결합 시 이중 부호 반전 금지

### 3. 최종 리더보드 표시 (9개)

복합방향 · 순유동성 · VIX · MVRV · 볼린저밴드 · 도미넌스 · 유동성 · 긴축환경 · 과열회귀

(레지스트리는 매수보유 포함 10개)

### 4. 신규 포트폴리오

ensure_portfolios 기존 로직으로 $10,000 시드 콜드 스타트 (백필 시뮬레이션 없음)

## 변경 파일

| 파일 | 작업 |
|---|---|
| `crypto-volatility-bot/app/macro/signals.py` | 결합 신호 함수 3개 추가, INDICATORS에서 5개 해제·3개 등록 |
| `dashboard/backend/services/paper_engine.py` | leaderboard() 표시 필터 (레지스트리 지표만 + BENCHMARK 행 제외, vs_buyhold 계산 유지) |
| `crypto-volatility-bot/tests/unit/test_signals.py` | 레지스트리 구성·결합 수치·NaN 정책 테스트 갱신 |
| `dashboard/tests/test_paper_engine.py` | leaderboard() 필터·콜드 스타트 테스트 갱신 |
| `dashboard/frontend/src/components/screens/Leaderboard.tsx` | 원칙적 무변경 (백엔드에서 행 필터링, vs매수보유 컬럼 유지) |

## 검증 기준 (AC)

1. INDICATORS 레지스트리 = 정확히 10개: 복합방향·순유동성·VIX·MVRV·볼린저밴드·도미넌스·유동성·긴축환경·과열회귀·매수보유(BENCHMARK)
2. latest_signals()가 신규 3개는 자산별 신호 산출, 제거 5개는 미산출
3. 결합 수치 단위테스트: 유동성 = (순유동성z + TGAz)/2, 긴축환경 = (달러z + 금리z)/2, 과열회귀 = (RSIz + 볼밴z)/2. 멤버 일부 NaN → 부분평균, 전부 NaN → NaN
4. leaderboard() 응답에 매수보유·달러·금리·TGA·모멘텀30d·RSI 행 없음, vs_buyhold_pct는 여전히 매수보유 성적 기준 계산
5. DB 기존 행 보존 — 삭제/백필 SQL 없음
6. 봇 + 대시보드 테스트 스위트 전체 통과

## 제약

한국어 주석 · 외과적 변경 · TDD · DB 삭제 마이그레이션 금지 · 기존 스키마 필드만 사용 · app.macro sys.path 임포트 구조 재사용
