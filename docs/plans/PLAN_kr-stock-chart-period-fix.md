# PLAN: KR Stock Chart Period Fix

**Seed ID:** seed_53b3b009d8e8  
**Interview ID:** interview_20260419_055438  
**작성일:** 2026-04-19

## 문제 요약

KrStockChart에서 1w/1m 탭 클릭 시 차트가 비어있거나, period를 변경해도 같은 데이터가 반환되는 버그.

### 근본 원인

| 원인 | 위치 | 증상 |
|---|---|---|
| `_PERIOD_MAP`에 `"1w"`, `"1m"` 키 누락 | `yahoo_finance.py` | US 주식에서 1w/1m 탭이 항상 3m 데이터 반환 |
| 백엔드 서버 미재시작 | 런타임 | `naver_finance.py`의 `_PERIOD_COUNT` 변경(`"1w": 10, "1m": 30`) 미반영 |

### 이번 범위 **제외** 항목

- 네이버 fchart API 데이터 신뢰성 검증
- lightweight-charts 10포인트 렌더링 보정
- altcoin_season.py 관련 변경 (별도 커밋으로 분리)

---

## Task 1: yahoo_finance.py _PERIOD_MAP 확장

**파일:** `dashboard/backend/collectors/yahoo_finance.py`

`fetch_stock_ohlcv` 함수 내 `_PERIOD_MAP`에 `"1w"`와 `"1m"` 추가.

```python
# 변경 전
_PERIOD_MAP: dict[str, str] = {
    "3m": "3mo",
    "6m": "6mo",
    "1y": "1y",
}

# 변경 후
_PERIOD_MAP: dict[str, str] = {
    "1w": "5d",
    "1m": "1mo",
    "3m": "3mo",
    "6m": "6mo",
    "1y": "1y",
}
```

**커밋:** `fix: yahoo_finance _PERIOD_MAP에 1w/1m 기간 매핑 추가`

---

## Task 2: altcoin_season.py diff 검토 및 커밋 분리

`git diff dashboard/backend/collectors/altcoin_season.py` 로 변경 내용 확인 후:

- 이번 차트 수정과 **무관**하면 → 별도 커밋으로 분리
- **관련** 있으면 → Task 1 커밋에 포함

---

## Task 3: 백엔드 서버 재시작

`naver_finance.py`의 `_PERIOD_COUNT = {"1w": 10, "1m": 30, "3m": 90, "6m": 180, "1y": 365}` 반영을 위해 백엔드 재시작.

- in-process 캐시(`_store` dict)는 재시작으로 자동 초기화 → 별도 flush 불필요

---

## 검증 시나리오 (합격 기준)

| 종목 | 탭 | 기대 배열 길이 | 확인 방법 |
|---|---|---|---|
| 삼성전자 005930.KS | 1w | ≈ 10 | 브라우저 네트워크 탭 응답 확인 |
| 삼성전자 005930.KS | 1m | ≈ 30 | 동일 |
| 삼성전자 005930.KS | 3m | 1w/1m과 다른 데이터 | 날짜 범위 비교 |
| AAPL | 1w | ≈ 5 거래일 | 동일 |
| AAPL | 1m | ≈ 20 거래일 | 동일 |

---

## Acceptance Criteria

- [ ] `yahoo_finance.py` `_PERIOD_MAP`에 `"1w": "5d"`, `"1m": "1mo"` 추가됨
- [ ] 백엔드 서버 재시작 완료
- [ ] 삼성전자 1w ≈ 10, 1m ≈ 30, 3m과 다른 데이터 확인
- [ ] AAPL 1w ≈ 5, 1m ≈ 20 확인
- [ ] altcoin_season.py 처리 방침 결정됨
