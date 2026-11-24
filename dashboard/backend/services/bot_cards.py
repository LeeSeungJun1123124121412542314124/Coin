"""봇 리포트로 만드는 리서치 '봇 관찰' 카드 — ETF 수급, 청산 히트맵, 고래 소식.

봇이 보고 적은 값이라 점수를 매기지 않는다(observed). 리서치 점수·스냅샷과 섞지 않고,
응답을 만드는 라우트에서 기존 카드 뒤에 덧붙인다.
스펙: docs/plans/bot-reports-spec-2026-11-24.md 7절
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")
_MAX_AGE_DAYS = 7      # 가장 최근 리포트가 이보다 오래되면 카드를 만들지 않는다
_LOOKBACK_ROWS = 40    # 종류별로 살펴볼 최근 리포트 수 (어제 리포트를 찾기에 충분)
_NO_COMPARE = {"prev": None, "week": None}


# ── 공통 ────────────────────────────────────────────────────────

def _kst(iso: str) -> datetime:
    parsed = datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_KST)


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _data(report) -> dict:
    return _dict(json.loads(report["data_json"])) if report["data_json"] else {}


_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _plain(cell: str) -> str:
    """표 칸에서 굵은 글씨 표시와 링크 주소를 걷어낸 글자."""
    return _LINK.sub(r"\1", cell).replace("**", "").strip()


def _tables(body: str) -> list[list[list[str]]]:
    """본문의 마크다운 표들을 [머리글 행, 데이터 행, …] 목록으로. 구분선 줄은 뺀다."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in body.replace("\r\n", "\n").split("\n") + [""]:
        line = line.strip()
        if line.startswith("|"):
            if not (_SEPARATOR.match(line) and "-" in line):
                current.append([_plain(cell) for cell in line.strip("|").split("|")])
        elif current:
            tables.append(current)
            current = []
    return tables


# ── 청산 히트맵 ─────────────────────────────────────────────────

def _heatmap_levels(report) -> dict[str, float]:
    """홈의 청산 구간 막대용 숫자: 현재가, 아래 롱 구간, 위 숏 구간. 숫자가 아닌 값은 뺀다."""
    data = _data(report)
    values = {
        "price": _num(data.get("price")),
        "long_price": _num(_dict(data.get("main_long_band")).get("price")),
        "short_price": _num(_dict(data.get("biggest_short")).get("price")),
    }
    return {key: value for key, value in values.items() if value is not None}


def _usd(value: float) -> str:
    return f"${value:,.0f}"


def _distance(target: float, price: float | None) -> str:
    if not price:
        return ""
    return f" ({(target - price) / price * 100:+.1f}%)"


def _build_heatmap(report) -> tuple[str, str | None, list[list[str]]]:
    data = _data(report)
    price = _num(data.get("price"))
    long_band, short_band = _dict(data.get("main_long_band")), _dict(data.get("biggest_short"))
    long_price, short_price = _num(long_band.get("price")), _num(short_band.get("price"))
    long_3d, long_1w = _num(long_band.get("amount_3d_m")), _num(long_band.get("amount_1w_m"))
    short_amount = _num(short_band.get("amount_m"))
    long_pct, short_pct = _dict(data.get("long_pct")), _dict(data.get("short_pct"))
    liquidated = _dict(data.get("liquidated_24h"))
    liq_total, liq_long, liq_short = (_num(liquidated.get(k)) for k in ("total_m", "long_m", "short_m"))

    parts: list[str] = []
    rows: list[list[str]] = []
    title_parts: list[str] = []
    if price is not None:
        parts.append(f"현재가 {_usd(price)}")
        rows.append(["현재가", _usd(price)])
    if long_price is not None:
        head = f"{_usd(long_price)}{_distance(long_price, price)}"
        amount = long_3d if long_3d is not None else long_1w
        parts.append(f"아래 롱 {head}" + (f" {amount:.1f}M" if amount is not None else ""))
        sizes = [f"{label} {v:.1f}M" for label, v in (("3일", long_3d), ("1주", long_1w)) if v is not None]
        rows.append(["아래 롱 구간", " · ".join([head, *sizes])])
        title_parts.append(f"아래 롱 {_usd(long_price)}")
    if short_price is not None:
        head = f"{_usd(short_price)}{_distance(short_price, price)}"
        parts.append(f"위 숏 {head}" + (f" {short_amount:.1f}M" if short_amount is not None else ""))
        rows.append(["위 숏 구간", " · ".join([head] + ([f"{short_amount:.1f}M"] if short_amount is not None else []))])
        title_parts.append(f"위 숏 {_usd(short_price)}")

    ratios = [
        f"{label} {long_v:.0f}/{short_v:.0f}"
        for key, label in (("24h", "24시간"), ("3d", "3일"), ("1w", "1주"))
        if (long_v := _num(long_pct.get(key))) is not None and (short_v := _num(short_pct.get(key))) is not None
    ]
    three_day = next((r for r in ratios if r.startswith("3일 ")), None)
    if three_day:
        parts.append(three_day.replace("3일 ", "3일 롱/숏 "))
    if ratios:
        rows.append(["롱/숏 비중", " · ".join(ratios)])
    if liq_total is not None:
        parts.append(f"24시간 청산 ${liq_total:.1f}M")
        split = [f"{label} ${v:.1f}M" for label, v in (("롱", liq_long), ("숏", liq_short)) if v is not None]
        rows.append(["24시간 청산", f"${liq_total:.1f}M" + (f" ({' · '.join(split)})" if split else "")])

    title = " · ".join(title_parts) or "청산 히트맵"
    stamp = _kst(report["reported_at"]).strftime("%m-%d %H:%M")
    summary = f"{stamp} 기준 · {' | '.join(parts)}" if parts else None
    return title, summary, rows


# ── ETF 수급 ────────────────────────────────────────────────────

def _money(cell: str) -> float | None:
    text = cell.replace("−", "-").replace("–", "-")
    cleaned = re.sub(r"[$,M+\s]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _signed_money(value: float) -> str:
    sign = "-" if value < 0 else "+" if value > 0 else ""
    return f"{sign}${abs(value):,.1f}M"


def _etf_days_from_data(data: dict) -> list[dict]:
    """봇이 data.etf로 보낸 숫자 값 — [{date, btc_m, eth_m, sol_m, provisional}], 최신 날짜가 먼저."""
    days = []
    for item in data.get("etf") if isinstance(data.get("etf"), list) else []:
        item = _dict(item)
        btc = _num(item.get("btc_m"))
        if not isinstance(item.get("date"), str) or btc is None:
            continue
        values = {"BTC": btc, "ETH": _num(item.get("eth_m")), "SOL": _num(item.get("sol_m"))}
        days.append({"date": item["date"], "provisional": item.get("provisional") is True, "values": values})
    return days


def _etf_days_from_table(body: str) -> list[dict]:
    """data가 없을 때 — 본문의 ETF 표(머리글 날짜·BTC·ETH·SOL·비고)를 읽는다."""
    table = next(
        (t for t in _tables(body)
         if "날짜" in t[0][0] and all(coin in t[0] for coin in ("BTC", "ETH", "SOL"))),
        None,
    )
    if table is None:
        return []
    header = table[0]
    col = {name: header.index(name) for name in ("BTC", "ETH", "SOL")}
    note_col = header.index("비고") if "비고" in header else None

    days = []
    for cells in table[1:]:
        values = {name: _money(cells[i]) if i < len(cells) else None for name, i in col.items()}
        if values["BTC"] is None:
            continue
        note = cells[note_col] if note_col is not None and note_col < len(cells) else ""
        # "어제 잠정에서 … 반영된 확정치"처럼 확정된 날의 비고에도 '잠정'이 나온다 — '확정'이 있으면 잠정이 아니다
        days.append({"date": cells[0], "provisional": "잠정" in note and "확정" not in note, "values": values})
    return days


def _build_etf(report) -> tuple[str, str | None, list[list[str]]] | None:
    # 봇이 보낸 숫자 값이 있으면 그것을 쓴다 — 본문 표는 모양이 바뀌면 못 읽는다
    days = _etf_days_from_data(_data(report)) or _etf_days_from_table(report["body"])
    if not days:
        return None

    def flows(day: dict) -> list[str]:
        return [f"{name} {_signed_money(v)}" for name, v in day["values"].items() if v is not None]

    latest = days[0]
    tag = " 잠정" if latest["provisional"] else ""
    title = f"BTC 현물 ETF {_signed_money(latest['values']['BTC'])} ({latest['date']}{tag})"
    summary = f"{latest['date']}{tag} · {' | '.join(flows(latest))}"
    rows = [
        [f"{d['date']} (잠정)" if d["provisional"] else d["date"], " · ".join(flows(d))]
        for d in days[:5]
    ]
    return title, summary, rows


# ── 고래 소식 ───────────────────────────────────────────────────

def _whale_items_from_data(data: dict) -> list[dict]:
    """봇이 data.items로 보낸 소식 — [{time, account, coin, text, flagged}]."""
    items = []
    for item in data.get("items") if isinstance(data.get("items"), list) else []:
        item = _dict(item)
        fields = [item.get(k) for k in ("time", "account", "coin", "text")]
        if not all(isinstance(v, str) and v for v in fields):
            continue
        items.append({"time": fields[0], "account": fields[1], "coin": fields[2], "text": fields[3],
                      "flagged": item.get("flagged") is True})
    return items


def _whale_items_from_table(body: str) -> list[dict]:
    """data가 없을 때 — 본문의 첫 표(시각·계정·코인·내용)를 읽는다. 🔴는 시각 칸에 붙어 온다."""
    table = next((t for t in _tables(body) if "시각" in t[0][0] and len(t[0]) >= 4), None)
    if table is None:
        return []
    return [
        {"time": cells[0].replace("🔴", "").strip(), "account": cells[1], "coin": cells[2], "text": cells[3],
         "flagged": "🔴" in cells[0]}
        for cells in table[1:]
        if len(cells) >= 4 and cells[3]
    ]


def _build_whale(report) -> tuple[str, str | None, list[list[str]]] | None:
    items = _whale_items_from_data(_data(report)) or _whale_items_from_table(report["body"])
    if not items:
        return None

    coins: dict[str, int] = {}
    for item in items:
        coins[item["coin"]] = coins.get(item["coin"], 0) + 1
    by_coin = " · ".join(f"{coin} {n}건" for coin, n in sorted(coins.items(), key=lambda kv: -kv[1]))
    flagged = sum(1 for item in items if item["flagged"])

    stamp = _kst(report["reported_at"]).strftime("%m-%d %H:%M")
    summary = f"{stamp} 기준 · 소식 {len(items)}건 | {by_coin}" + (f" | 🔴 {flagged}건" if flagged else "")
    rows = [
        [("🔴 " if item["flagged"] else "") + " · ".join((item["time"], item["account"], item["coin"])), item["text"]]
        for item in items
    ]
    return f"고래·온체인 소식 {len(items)}건", summary, rows


# ── 카드 조립 ───────────────────────────────────────────────────

# (카드 키, 카드 이름, 리포트 종류, 만드는 함수) — 화면에 나오는 순서
_CARDS = (
    ("bot_etf", "ETF 수급", "daily_check", _build_etf),
    ("bot_heatmap", "청산 히트맵", "heatmap", _build_heatmap),
    ("bot_whale", "고래 소식", "whale", _build_whale),
)


def build_bot_cards(today: date) -> list[dict]:
    """종류별 가장 최근 리포트로 봇 관찰 카드를 만든다. 리포트가 없거나 7일보다 오래되면 그 카드는 뺀다."""
    from dashboard.backend.db import connection

    cards: list[dict] = []
    with connection.get_db() as conn:
        for key, name, kind, build in _CARDS:
            reports = conn.execute(
                """SELECT id, title, body, data_json, reported_at FROM bot_reports
                   WHERE kind = ? ORDER BY reported_at DESC, id DESC LIMIT ?""",
                (kind, _LOOKBACK_ROWS),
            ).fetchall()
            if not reports:
                continue
            latest = reports[0]
            latest_day = _kst(latest["reported_at"]).date()
            if (today - latest_day).days > _MAX_AGE_DAYS:
                continue
            built = build(latest)
            if built is None:
                continue
            title, summary, rows = built
            stamp = _kst(latest["reported_at"]).strftime("%m-%d %H:%M")

            # 어제 대비 — 같은 날 먼저 온 리포트가 아니라 그 전 날짜의 가장 최근 리포트와 견준다
            compare = _NO_COMPARE
            previous = next((r for r in reports[1:] if _kst(r["reported_at"]).date() < latest_day), None)
            if previous is not None:
                prev_built = build(previous)
                prev_day = _kst(previous["reported_at"]).date()
                compare = {
                    "prev": {
                        "date": prev_day.isoformat(),
                        "days_ago": (today - prev_day).days,
                        "summary": (prev_built[1] if prev_built else None) or previous["title"],
                    },
                    "week": None,
                }

            cards.append({
                "key": key,
                "name": name,
                "level": "neutral",
                "score": 0,
                "observed": True,  # 점수 없음 — 스냅샷·점수 비교에서 제외
                "title": title,
                "summary": summary or f"{stamp} 기준 · {latest['title']}",
                "details": {
                    "rows": rows, "report_id": latest["id"], "reported_at": latest["reported_at"],
                    **({"levels": _heatmap_levels(latest)} if key == "bot_heatmap" else {}),
                },
                "updated_at": latest["reported_at"],
                "compare": compare,
            })
    return cards
