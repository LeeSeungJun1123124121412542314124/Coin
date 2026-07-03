# 반도체 정점 시그널 카드 확장 (삼성 + SK하이닉스) 구현 계획

**작성일:** 2026-07-04
**Seed:** seed_c8c084fc16f3 (interview_20260703_162623, ambiguity 0.065)
**기능:** 삼성 전용 "반도체 정점" 카드를 삼성+하이닉스 9시그널 3섹션으로 확장 + 수동 데이터 stale 알림

---

## 1. 배경 / 문제

- 사용자는 반도체 사이클 고점 신호를 보고 삼성전자·SK하이닉스를 매도하려는 개인 투자자.
- 현재 카드는 `research_analyzer.py`의 하드코딩 상수 `SAMSUNG_SIGNALS`(6개, 2026-04 시점)를 표시. API 연동 없이 수동 편집으로만 갱신.
- **치명적 문제**: 4월 데이터로 멈춤 → 실제 고점 신호(외국인 6월 -36.5조 순매도)가 켜졌는데 카드는 "정상" 표시. 게다가 `updated_at`을 매 요청마다 현재 시각으로 찍어 신선한 척함.

## 2. 확정 요구사항

### 데이터 모델 — 단일 카드 "반도체 정점", 9시그널 3섹션
| 섹션 | 시그널 |
|------|--------|
| 업황 공통 | DRAM 고정거래가 모멘텀 둔화 / LTA 가격 하한선 무력화 / DRAM 재고 증가 |
| 삼성 005930 | 외국인 4주 누적 순매도 / EPS 컨센서스 상향 정체·하향 / 메모리 capex 폭발 |
| 하이닉스 000660 | 외국인 4주 누적 순매도 / EPS 컨센서스 상향 정체·하향 / 메모리 capex 폭발 |

각 시그널: `status`(green/yellow/red) · `label` · `note`.

### 초기값 (2026-07 리서치)
- 업황: 가격 🟡(둔화, Q1 +95%→Q2 +48~63%→Q3 +40~50%) / LTA 🟢(공급사 계약단축·가격결정권 회복) / 재고 🟢(역대최저 2~3주, 완판)
- 삼성: 수급 🔴(6월 -20.6조 순매도, 인버스 매수) / EPS 🟢(2Q 컨센 폭증) / capex 🟡(730억달러, P5 60조)
- 하이닉스: 수급 🔴(6월 -15.9조) / EPS 🟢(2Q 컨센 폭증) / capex 🟡(170억달러+, M15X 20조)
- → red 2, yellow 3, green 4 → **level "critical", 정점 임박 5/9**

### 집계 규칙 (기존 로직 유지)
- `peak_count = yellow + red`, 카드 상단 "정점 임박 N/9"
- level: `red>=1 → critical` / `elif yellow>=3 → warning` / `elif yellow>=1 → neutral` / `else bullish`
- `score = (yellow*50 + red*100)//total`, 0~100 클램프

### 갱신 시점 추적
- 모듈 상수 `SEMICONDUCTOR_SIGNALS_AS_OF = "2026-07-04"` (단일 date 문자열, 사람이 마지막 검토한 날)
- `days_since = (datetime.now(timezone.utc).date() - as_of).days`
- 카드에 "최종 확인: N일 전" 표시. `updated_at`(현재시각) 동작은 유지, `as_of`는 별도.

### Stale 알림 (자동 크롤링 아님 — 리마인더)
- `days_since > 21` → `alert_history`에 INSERT: `symbol="반도체"`, `alert_level="STALE_SIGNAL"`, `details` JSON
- + 텔레그램 발송 (`dispatcher._notifier.send_message`)
- 중복 방지: `bot_state` 키 `semiconductor_peak_stale_alerted` 전이 패턴 (direction_watch 미러링). stale→ok 복귀 시 리셋 → 다음 stale 때 재알림.
- 스케줄: 기존 `direction_health_watch`(매일 UTC 00:20)에 `check_semiconductor_stale()` 호출 추가. **별도 크론 미추가.**
- `details` JSON: `{as_of, days_since, threshold_days, peak_count, total, level}`
- 텔레그램 템플릿(고정):
  ```
  🔺 반도체 정점 카드 갱신 필요
  마지막 확인: {as_of} ({days_since}일 전 · 기준 {threshold_days}일 초과)
  현재 정점 임박 {peak_count}/{total} (level: {level})
  Claude에게 '반도체 시그널 갱신'을 요청하세요.
  ```

### 네이밍 리네이밍 (참조 2파일 한정)
- `SAMSUNG_SIGNALS` → `SEMICONDUCTOR_SIGNALS`
- API key `samsung_signals` → `semiconductor_signals`, 캐시 `key_prefix` `research_samsung` → `research_semiconductor`
- `names`/`keys` 배열, Research.tsx `key === ` 검사, interface명 동반 수정. 카테고리 name "반도체 정점" 유지.

### 프론트엔드
- `Research.tsx`: samsung_signals 렌더 → 3섹션 그룹 레이아웃 + "최종 확인: N일 전". `CATEGORIES` 필터/`CATEGORY_COLORS`에 "반도체 정점" 추가 (기존 갭 수정).
- `Alerts.tsx`: `LEVEL_LABEL`/`LEVEL_COLOR`에 `STALE_SIGNAL="갱신 필요"` 추가. **심볼 필터 셀렉트는 미수정** (스코프 제외).

## 3. 실제 파일 경로 (검증됨)
| 파일 | 경로 | 역할 |
|------|------|------|
| research_analyzer.py | `dashboard/backend/services/` | 상수·분석 로직·stale 판정 함수 |
| macro_health.py | `dashboard/backend/services/` | stale 판정 패턴 참고 |
| direction_watch.py | `dashboard/backend/jobs/` | bot_state 전이·중복방지 참고 + 훅 추가 |
| main.py (스케줄러) | `dashboard/backend/` | direction_health_watch 크론 |
| schema.sql | `dashboard/backend/db/` | alert_history·bot_state |
| notification_dispatcher.py | `crypto-volatility-bot/app/` | _save_alert_history INSERT 템플릿 |
| telegram_notifier.py | `crypto-volatility-bot/app/notifiers/` | send_message |
| Research.tsx | `dashboard/frontend/src/components/screens/` | 카드 렌더 |
| Alerts.tsx | `dashboard/frontend/src/components/screens/` | 알림 라벨 |

## 4. 검증 기준
1. **백엔드**: as_of를 22일 전으로 세팅 → stale 함수 실행 시 `alert_history` STALE_SIGNAL 1건 INSERT + 텔레그램 호출. 재실행 시 중복 없음. as_of 최근 복구 → bot_state 리셋 → 다음 stale 재알림. (3케이스 테스트)
2. **API**: `GET /api/research-analysis`의 semiconductor_signals에 3섹션 9시그널 + as_of + peak_count(5) + level("critical").
3. **프론트**: 카드 3섹션 렌더 + "최종 확인" 표시 + "반도체 정점" 탭. 알림 화면 "갱신 필요" 라벨.
4. **리네이밍**: `grep samsung_signals` 잔여 0건.
