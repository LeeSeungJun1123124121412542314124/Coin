# 봇 리포트 전송 안내 (그록봇용)

투자분석기는 봇이 만든 리포트를 받아 "봇 리포트" 화면에 종류별로 모아 보여 줍니다.
지금 채팅으로 보내는 내용을 **같은 시점에 한 번 더** 아래 주소로 보내면 됩니다.

## 보내는 곳

| 항목 | 값 |
|---|---|
| 주소 | `https://myl6zvvq1egnb4adcundbjbv.129.203.199.110.sslip.io/api/bot-reports` |
| 방식 | `POST`, 본문은 JSON (`Content-Type: application/json`) |
| 인증 | 헤더 `X-Bot-Key: <전달받은 키>` |

키는 이 문서에 적지 않습니다. 사용자가 따로 알려 준 값을 쓰고, 기록 파일이나 채팅에 남기지 마세요.

## 본문 형식

```json
{
  "kind": "heatmap",
  "title": "CoinGlass 청산 히트맵 · 11/22 09:17 KST",
  "body": "…마크다운 본문…",
  "reported_at": "2026-11-22T00:17:00+00:00",
  "data": { "long_pct_3d": 30, "short_pct_3d": 70 }
}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `kind` | 예 | 아래 6가지 중 하나 |
| `title` | 예 | 1~200자. 리포트 제목 한 줄 |
| `body` | 예 | 1~20,000자. 마크다운. 넘으면 나눠서 보낸다 |
| `reported_at` | 아니오 | 기준 시각(ISO 8601, 시간대 포함). 없으면 받은 시각을 쓴다 |
| `data` | 아니오 | 숫자로 나눠 둔 값(JSON 객체, 50,000자 이하). 나중에 카드로 만들 때 쓴다 |

### kind

| 값 | 화면 이름 | 보내는 리포트 |
|---|---|---|
| `daily_check` | 일봉 점검 | 매일 09:05 일봉 점검 |
| `weekly_check` | 주봉 점검 | 주봉 마감 점검 |
| `heatmap` | 청산 히트맵 | CoinGlass 청산 히트맵 |
| `whale` | 고래·온체인 | X 고래·온체인 소식, OI 점검 |
| `breakout` | 돌파 알림 | 1시간 돌파·이탈 알림 |
| `other` | 기타 | 위에 없는 것 |

### body에 쓸 수 있는 마크다운

화면은 아래 네 가지만 해석합니다. 나머지는 글자 그대로 보입니다.

- 표: `| 구분 | 11/21 | 11/22 |` 형식(둘째 줄은 `|---|---|---|`)
- 굵은 글씨: `**$57,301 · 44.1M**`
- 링크: `[CoinGlass](https://www.coinglass.com/…)` — `http`/`https` 주소만 링크가 된다
- 목록: 줄 앞에 `- `, 제목: 줄 앞에 `## `

표는 탭으로 나눈 글이 아니라 `|`로 나눈 마크다운 표로 보내야 표로 그려집니다.

## 응답

| 상태 | 뜻 | 할 일 |
|---|---|---|
| `200` `{"ok": true, "id": 12, "duplicate": false}` | 저장됨 | 없음 |
| `200` `{"ok": true, "id": 12, "duplicate": true}` | 같은 `kind`·`title`·`body`를 이미 받음 | 없음(다시 보내도 안전) |
| `401` | 키가 없거나 틀림 | 키 확인 |
| `422` | 형식 오류(없는 `kind`, 빈 값, 길이 초과, 잘못된 시각) | 본문 고쳐서 다시 |
| `429` | 1분에 30건 초과 | 1분 뒤 다시 |
| `503` | 서버에 키가 아직 등록되지 않음 | 사용자에게 알림 |

실패했을 때는 1분 뒤 한 번만 다시 시도하고, 그래도 안 되면 채팅 보고에 "투자분석기 전송 실패(상태 코드)" 한 줄을 붙입니다.

## 예시 (curl)

```bash
curl -X POST "https://myl6zvvq1egnb4adcundbjbv.129.203.199.110.sslip.io/api/bot-reports" \
  -H "Content-Type: application/json" \
  -H "X-Bot-Key: $BOT_INGEST_KEY" \
  -d '{"kind":"breakout","title":"돌파 알림 · 11-22 11:51 KST","body":"| 상태 | 조건 | 현재 | 기준 | 거리 |\n|---|---|---|---|---|\n| 🔴 이탈 | BTC $60K 하향 이탈 | $59,430 | $60,000 | −0.95% |","reported_at":"2026-11-22T02:51:00+00:00"}'
```

## 받은 쪽에서 하는 일

- 원문을 그대로 저장하고 "봇 리포트" 화면에 최신순으로 보여 준다.
- 리서치 점수 계산에는 넣지 않는다.
- 관련 코드: `dashboard/backend/api/bot_report_routes.py`, 스펙: `docs/plans/bot-reports-spec-2026-11-24.md`

## 리서치 카드에 쓰이는 숫자 값 (`data`)

보낸 리포트 중 세 가지는 리서치 화면의 "봇 관찰" 카드로도 만들어집니다.
카드는 본문이 아니라 **`data`에 넣은 값**으로 만듭니다. 본문 표는 사람이 읽는 용도로 자유롭게 써도 됩니다.

| 카드 | 리포트 종류 | `data`에 넣을 것 |
|---|---|---|
| ETF 수급 | `daily_check` | `etf` |
| 청산 히트맵 | `heatmap` | `price`, `main_long_band`, `biggest_short`, `long_pct`, `short_pct`, `liquidated_24h` |
| 고래 소식 | `whale` | `items` |

### `daily_check` — ETF 순유입

```json
{
  "etf": [
    { "date": "11/23", "btc_m": -73.7, "eth_m": 0.0, "sol_m": -1.9, "provisional": true },
    { "date": "11/20", "btc_m": -669.2, "eth_m": -97.3, "sol_m": -5.9, "provisional": false }
  ]
}
```

- 최신 날짜를 맨 앞에, 최근 3~5일치.
- 금액은 백만 달러 단위 숫자(순유출은 음수). `date`와 `btc_m`은 필수, 나머지는 없으면 빼도 됩니다.
- 일부 운용사 미집계 등 잠정치면 `provisional: true`.

### `heatmap` — 청산 히트맵

```json
{
  "price": 61150,
  "main_long_band": { "price": 57352, "amount_3d_m": 63.8, "amount_1w_m": 63.8 },
  "biggest_short": { "price": 64001, "amount_m": 62.9 },
  "long_pct": { "24h": 36, "3d": 71, "1w": 50 },
  "short_pct": { "24h": 64, "3d": 29, "1w": 50 },
  "liquidated_24h": { "total_m": 97.0, "long_m": 34.7, "short_m": 62.3 }
}
```

모두 숫자이고, 읽지 못한 값은 빼면 됩니다(있는 것만 보여 줍니다).

### `whale` — 고래·온체인 소식

```json
{
  "items": [
    { "time": "11-24 00:22", "account": "Whale Alert", "coin": "ETH", "text": "29,624 ETH($53.0M) 미확인 지갑→Coinbase Institutional 입금", "flagged": true },
    { "time": "11-24 00:57", "account": "Whale Alert", "coin": "BTC", "text": "4,362 BTC($274.2M) Coinbase Institutional→신규 미확인 지갑 이동" }
  ]
}
```

- `time`·`account`·`coin`·`text`는 필수(문자열). 알림 기준을 넘은 건은 `flagged: true`.
- `text`는 본문 표의 "내용" 칸과 같은 한 문장.

### `data`가 없을 때

`data`를 보내지 않으면 본문 표를 읽어서 카드를 만듭니다(ETF는 머리글 `날짜 | BTC | ETH | SOL | 비고`인 표, 고래는 머리글 첫 칸에 "시각"이 있는 첫 표).
이 방식은 표 모양이 바뀌면 카드가 빠지므로, `data`를 보내는 쪽을 권합니다.

카드는 종류별로 가장 최근 리포트 한 건으로 만들고, 전날 리포트와 나란히 보여 줍니다. 점수 계산에는 쓰지 않습니다.
