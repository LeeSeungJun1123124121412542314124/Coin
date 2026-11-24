"""리서치 분석 일별 스냅샷 — 카드의 '어제 · 7일 전 대비' 표시용.

분석 결과는 요청 때마다 새로 계산되고 따로 남지 않는다. 하루 1행씩 저장해 두고
응답에 이전 저장분을 붙여, 카드가 무엇이 달라졌는지 보여줄 수 있게 한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_WEEK_DAYS = 7        # '7일 전' 비교 기준
_WEEK_MAX_DAYS = 14   # 이보다 오래된 저장분은 '7일 전' 비교에 쓰지 않는다

_NO_COMPARE = {"prev": None, "week": None}


def kst_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def save_snapshot(categories: list[dict], day: date) -> int:
    """항목별 점수·등급·제목·요약을 day 날짜 행으로 저장한다. 같은 날은 덮어써 그날의 마지막 값이 남는다."""
    from dashboard.backend.db import connection

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (day.isoformat(), c["key"], c["level"], int(c["score"]), c["title"], c["summary"], now)
        for c in categories
        # 오류·적재 중 상태는 실제 분석 결과가 아니고, 봇 관찰 카드는 점수가 없다
        if not c.get("placeholder") and not c.get("observed")
    ]
    with connection.get_db() as conn:
        conn.executemany(
            """INSERT INTO research_snapshot (date, key, level, score, title, summary, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, key) DO UPDATE SET
                   level = excluded.level,
                   score = excluded.score,
                   title = excluded.title,
                   summary = excluded.summary,
                   updated_at = excluded.updated_at""",
            rows,
        )
    return len(rows)


def _latest_rows(conn, newest: date, oldest: date | None) -> dict:
    """항목별로 [oldest, newest] 구간에서 가장 최근 저장분 1행."""
    lower = "AND date >= ?" if oldest else ""
    params = [newest.isoformat()] + ([oldest.isoformat()] if oldest else [])
    rows = conn.execute(
        f"""SELECT s.date, s.key, s.level, s.score, s.summary
            FROM research_snapshot s
            JOIN (SELECT key, MAX(date) AS latest
                  FROM research_snapshot
                  WHERE date <= ? {lower}
                  GROUP BY key) m
              ON m.key = s.key AND m.latest = s.date""",
        params,
    ).fetchall()
    return {row["key"]: row for row in rows}


def load_comparisons(day: date) -> dict[str, dict]:
    """항목 키 → {"prev": 오늘 이전 가장 최근 저장분, "week": 7일 전 이전 가장 최근(14일 이내) 저장분}."""
    from dashboard.backend.db import connection

    with connection.get_db() as conn:
        prev_rows = _latest_rows(conn, day - timedelta(days=1), None)
        week_rows = _latest_rows(conn, day - timedelta(days=_WEEK_DAYS), day - timedelta(days=_WEEK_MAX_DAYS))

    def entry(row, with_summary: bool) -> dict | None:
        if row is None:
            return None
        item = {
            "date": row["date"],
            "days_ago": (day - date.fromisoformat(row["date"])).days,
            "score": row["score"],
            "level": row["level"],
        }
        if with_summary:
            item["summary"] = row["summary"]
        return item

    return {
        key: {"prev": entry(prev_rows.get(key), True), "week": entry(week_rows.get(key), False)}
        for key in prev_rows.keys() | week_rows.keys()
    }


def attach_comparisons(result: dict, day: date) -> dict:
    """analyze_all 결과의 각 항목에 compare를 붙인 새 dict를 돌려준다(원본은 캐시된 객체일 수 있어 건드리지 않는다)."""
    comparisons = load_comparisons(day)
    categories = [
        {
            **category,
            # 오류·적재 중 카드는 점수가 0으로 채워져 있어 비교하면 오해를 준다
            "compare": _NO_COMPARE if category.get("placeholder") else comparisons.get(category["key"], _NO_COMPARE),
        }
        for category in result["categories"]
    ]
    return {**result, "categories": categories}
