"""SPF 유사 패턴 매칭 회귀 테스트."""

from __future__ import annotations

import pytest

from dashboard.backend.services.spf_service import find_similar_patterns


@pytest.fixture
def spf_db(tmp_path, monkeypatch):
    """임시 SQLite로 SPF DB를 격리한다."""
    from dashboard.backend.db import connection

    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "spf.db"))
    monkeypatch.setattr(connection, "_conn", None)
    conn = connection.get_connection()
    yield conn
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


def _record(
    date: str,
    *,
    oi3: float,
    oi7: float,
    oi14: float,
    fr3: float,
    fr7: float,
    fr14: float,
) -> dict:
    return {
        "date": date,
        "oi_change_3d": oi3,
        "oi_change_7d": oi7,
        "oi_change_14d": oi14,
        "cum_fr_3d": fr3,
        "cum_fr_7d": fr7,
        "cum_fr_14d": fr14,
    }


def _insert_spf(conn, row: dict, *, price: float = 100.0) -> None:
    conn.execute(
        """INSERT INTO spf_records
           (date, oi_change_3d, oi_change_7d, oi_change_14d,
            cum_fr_3d, cum_fr_7d, cum_fr_14d,
            price, price_after_3d, flow, bearish_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["date"],
            row["oi_change_3d"],
            row["oi_change_7d"],
            row["oi_change_14d"],
            row["cum_fr_3d"],
            row["cum_fr_7d"],
            row["cum_fr_14d"],
            price,
            price * 1.03,
            "neutral",
            42,
        ),
    )
    conn.commit()


def _scale_fr(row: dict, factor: float) -> dict:
    scaled = dict(row)
    for key in ("cum_fr_3d", "cum_fr_7d", "cum_fr_14d"):
        scaled[key] *= factor
    return scaled


def test_scale_invariance(spf_db):
    """FR 단위만 바뀌어도 유사 패턴 순위는 유지되어야 한다."""
    current = _record("current", oi3=10.0, oi7=10.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001)
    rows = [
        _record("2026-01-04", oi3=10.0, oi7=10.0, oi14=10.0, fr3=-0.001, fr7=-0.001, fr14=-0.001),
        _record("2026-01-03", oi3=10.0, oi7=9.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001),
        _record("2026-01-02", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=0.010, fr7=0.010, fr14=0.010),
        _record("2026-01-01", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=-0.010, fr7=-0.010, fr14=-0.010),
    ]
    for row in rows:
        _insert_spf(spf_db, row)
    normal_order = [row["date"] for row in find_similar_patterns(current, top_n=4)]

    spf_db.execute("DELETE FROM spf_records")
    for row in rows:
        _insert_spf(spf_db, _scale_fr(row, 1000))
    scaled_order = [row["date"] for row in find_similar_patterns(_scale_fr(current, 1000), top_n=4)]

    assert normal_order == scaled_order


def test_fr_dimension_contributes(spf_db):
    """OI가 같고 FR만 다르면 FR 차이가 유사도에 반영되어야 한다."""
    current = _record("current", oi3=10.0, oi7=10.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001)
    rows = [
        _record("2026-01-04", oi3=10.0, oi7=10.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001),
        _record("2026-01-03", oi3=10.0, oi7=10.0, oi14=10.0, fr3=-0.001, fr7=-0.001, fr14=-0.001),
        _record("2026-01-02", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=0.010, fr7=0.010, fr14=0.010),
        _record("2026-01-01", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=-0.010, fr7=-0.010, fr14=-0.010),
    ]
    for row in rows:
        _insert_spf(spf_db, row)

    similarities = {row["date"]: row["similarity"] for row in find_similar_patterns(current, top_n=4)}

    assert similarities["2026-01-04"] > similarities["2026-01-03"]


def test_return_shape_unchanged(spf_db):
    """프론트가 쓰는 반환 키는 그대로 유지한다."""
    current = _record("current", oi3=10.0, oi7=10.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001)
    _insert_spf(spf_db, _record("2026-01-01", oi3=10.0, oi7=10.0, oi14=10.0, fr3=0.001, fr7=0.001, fr14=0.001))
    _insert_spf(spf_db, _record("2025-12-31", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=0.010, fr7=0.010, fr14=0.010))
    _insert_spf(spf_db, _record("2025-12-30", oi3=-10.0, oi7=-10.0, oi14=-10.0, fr3=-0.010, fr7=-0.010, fr14=-0.010))

    result = find_similar_patterns(current, top_n=1)

    assert set(result[0]) == {"date", "similarity", "flow", "change_3d_pct", "bearish_score"}
