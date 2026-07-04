"""목업 셸에 원래 대시보드 자료를 연결하는 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")


def test_mock_shell_removes_account_and_top_ticker_data():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "mock-top-ticker" in source
    assert "mock-ticker-strip" not in source
    assert "TICKERS" not in source
    assert "기본 계정" not in source
    assert "mock-top-actions" not in source


def test_sidebar_uses_requested_dashboard_labels():
    source = APP_TSX.read_text(encoding="utf-8")

    for label in [
        "대시보드",
        "시장 분석",
        "SPF",
        "뉴스",
        "코인 가격",
        "한국 주식",
        "알트코인 시즌",
        "시장 지표",
    ]:
        assert label in source


def test_dashboard_uses_original_data_sections_in_mock_shell():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "useApi<DashboardData>('/api/dashboard'" in source
    assert "useApi<StockIndexItem[]>('/api/stock-indices'" in source
    assert "useApi<StockItem[]>('/api/stock-prices/kr'" in source
    assert "GlobalMarketCard" in source
    assert "StockIndexCard" in source
    assert "EconomicNewsSection" in source
    assert "AltcoinSeasonCard" in source
    assert "MacroHealthCard" in source


def test_dashboard_order_matches_requested_sections():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    ordered = [
        "mock-market-overview",
        "mock-news-section",
        "mock-coin-price-section",
        "mock-kr-stock-section",
        "mock-altcoin-season-section",
        "mock-market-detail-section",
    ]
    positions = [source.index(token) for token in ordered]
    assert positions == sorted(positions)
