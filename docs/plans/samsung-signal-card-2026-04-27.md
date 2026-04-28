# 반도체 정점 시그널 카드 구현 계획

**작성일:** 2026-04-27  
**기능:** 리서치 화면에 삼성전자 정점 시그널 카드 추가

---

## 1. 요구사항 요약

- 리서치 화면 기존 카드 그리드에 **"반도체 정점 시그널"** 카드 1개 추가
- 카드 내부에 6개 시그널 리스트 (각각 🟢/🟡/🔴 상태 표시)
- 데이터는 백엔드 API (`/api/research-analysis`) 에서 새 카테고리로 반환
- 상태는 자동 분석 로직으로 판정 (초기: 구조화된 정적값, 향후 자동화 확장)

### 시그널 목록 (초기값)

| # | 시그널 | 현재 상태 |
|---|--------|-----------|
| 1 | DRAM 고정거래가 모멘텀 둔화 | 🟢 아직 아님 |
| 2 | 메모리 capex 폭발적 증가 | 🟡 진행 중 |
| 3 | LTA(장기계약) 가격 하한선 무력화 | 🟢 아직 아님 |
| 4 | 외국인 4주 누적 매도 가속 | 🟡 모니터링 |
| 5 | 컨센서스 EPS 상향 정체/하향 | 🟢 아직 아님 |
| 6 | DRAM 재고 증가 | 🟢 아직 아님 |

---

## 2. 아키텍처

```
research_analyzer.py
└── analyze_all()
    ├── _analyze_macro()
    ├── _analyze_onchain()
    ├── ...
    └── _analyze_samsung_signals()  ← 신규 추가

Research.tsx
└── _renderDetails()
    ├── key === 'derivatives' → ...
    ├── ...
    └── key === 'samsung_signals' → 시그널 리스트 렌더링  ← 신규 추가
```

---

## 3. 데이터 모델

### CategoryAnalysis (기존 스키마 그대로)

```python
{
    "key": "samsung_signals",
    "name": "반도체 정점",
    "level": "bullish",        # 대부분 🟢일 때 bullish
    "score": 33,               # 🟡/🔴 개수 × (100/6), 정점 임박 점수
    "title": "정점 임박 시그널 2/6 감지",
    "summary": "capex 증가·외국인 매도 모니터링 중. 나머지 4개 지표 정상.",
    "updated_at": "2026-04-27T...",
    "details": {
        "signals": [
            {
                "id": "dram_price_momentum",
                "name": "DRAM 고정거래가 모멘텀 둔화",
                "status": "green",          # green | yellow | red
                "label": "아직 아님",
                "note": "1Q26 +65% QoQ, 2026 +148% 전망 지속"
            },
            {
                "id": "memory_capex",
                "name": "메모리 capex 폭발적 증가",
                "status": "yellow",
                "label": "진행 중",
                "note": "삼성 P4 라인 발주, 본격화 시작"
            },
            {
                "id": "lta_price_floor",
                "name": "LTA 가격 하한선 무력화",
                "status": "green",
                "label": "아직 아님",
                "note": "골드만삭스: 이번엔 강력 구속력, 정점 신호 아님"
            },
            {
                "id": "foreign_selling",
                "name": "외국인 4주 누적 매도 가속",
                "status": "yellow",
                "label": "모니터링",
                "note": "4월 누적 +2.53조 매수, 직전 2일 -4조 매도 전환"
            },
            {
                "id": "eps_consensus",
                "name": "컨센서스 EPS 상향 정체/하향",
                "status": "green",
                "label": "아직 아님",
                "note": "1Q26 +49% 서프, 컨센 상향 진행 중"
            },
            {
                "id": "dram_inventory",
                "name": "DRAM 재고 증가",
                "status": "green",
                "label": "아직 아님",
                "note": "1~2주 (역대 최저)"
            }
        ],
        "peak_count": 2,    # yellow + red 개수
        "total": 6
    }
}
```

### level 판정 로직

| 조건 | level |
|------|-------|
| 🔴 1개 이상 | critical |
| 🟡 3개 이상 | warning |
| 🟡 1~2개 | neutral |
| 🟡/🔴 0개 | bullish |

### score 계산

```python
score = (yellow × 50 + red × 100) // total  # 0~100, 정점 임박 지수
```

---

## 4. 구현 태스크

### 4-1. 백엔드: `research_analyzer.py` 수정

1. `SAMSUNG_SIGNALS` 상수 정의 (6개 시그널 초기값 dict 리스트)
2. `_analyze_samsung_signals()` async 함수 추가
   - 시그널 상태를 기반으로 score/level/title/summary 계산
   - 향후 자동화 훅 주석으로 표시 (외국인 순매수는 Yahoo Finance 연동 가능)
3. `analyze_all()` 병렬 실행 목록에 추가 (`asyncio.gather`)
4. `names`/`keys` 배열에 "반도체 정점" / "samsung_signals" 추가

### 4-2. 프론트엔드: `Research.tsx` 수정

1. `_renderDetails()` 함수에 `key === 'samsung_signals'` 케이스 추가
2. `details.signals` 배열을 리스트로 렌더링
   - `status === 'green'` → 🟢 (#22c55e)
   - `status === 'yellow'` → 🟡 (#f59e0b)
   - `status === 'red'` → 🔴 (#ef4444)
3. 각 항목: 시그널명 + 상태 라벨 + 노트 표시
4. 상단에 요약 배지 표시 (예: "⚠️ 2/6 모니터링")

---

## 5. 향후 자동화 계획 (선택)

| 시그널 | 자동화 가능 여부 | 방법 |
|--------|----------------|------|
| 외국인 순매수 | ✅ 가능 | Yahoo Finance 005930.KS 또는 KRX API |
| EPS 컨센서스 | △ 부분 가능 | 재무 데이터 API |
| DRAM 재고/가격 | ❌ 어려움 | 업계 전문 데이터 (TrendForce 등) |
| capex/LTA | ❌ 어려움 | 뉴스 파싱 또는 수동 |

초기엔 코드 내 `SAMSUNG_SIGNALS` 상수를 수동 수정하여 업데이트.

---

## 6. 파일 변경 목록

| 파일 | 변경 유형 |
|------|-----------|
| `dashboard/backend/services/research_analyzer.py` | 수정 (함수/상수 추가) |
| `dashboard/frontend/src/components/screens/Research.tsx` | 수정 (`_renderDetails` 케이스 추가) |
