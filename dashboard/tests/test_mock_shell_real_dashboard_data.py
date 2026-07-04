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
        "볼륨트래커",
        "SPF",
        "리서치",
        "시장분석",
        "유동성",
        "CVD 스크리너",
        "고래추적",
        "알림히스토리",
        "리더보드",
    ]:
        assert label in source


def test_sidebar_api_status_box_is_removed():
    source = APP_TSX.read_text(encoding="utf-8")

    assert "mock-api-status" not in source
    assert "API 연동" not in source


def test_dashboard_uses_original_data_sections_in_mock_shell():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "useApi<DashboardData>('/api/dashboard'" in source
    assert "useApi<StockIndexItem[]>('/api/stock-indices'" in source
    assert "useApi<StockItem[]>('/api/stock-prices/us'" in source
    assert "useApi<StockItem[]>('/api/stock-prices/kr'" in source
    assert "GlobalMarketCard" in source
    assert "StockIndexCard" in source
    assert "EconomicNewsSection" in source
    assert "AltcoinSeasonCard" in source
    assert "MacroHealthCard" in source


def test_dashboard_restores_card_interactions_and_editors():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "setSelectedSymbol('BTC')" in source
    assert "TradingViewChart" in source
    assert "toTvSymbol" in source
    assert "kimchi_history" in source
    assert "mock-kimchi-chart" in source
    assert "CoinSlotEditor" in source
    assert "handleSlotSave" in source
    assert "setSelectedSymbol(coin.symbol)" in source
    assert "StockSlotEditor" in source
    assert "KrStockChart" in source
    assert "setActiveKrStock" in source


def test_dashboard_section_titles_match_requested_labels():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert 'title="코인가격"' in source
    assert 'title="미국주식"' in source
    assert 'title="한국주식"' in source
    assert "<h1>대시보드</h1>" not in source
    assert "SPF · 코인 가격" not in source
    assert "SPF 추이 · 한국 주식" not in source


def test_dashboard_order_matches_requested_sections():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    ordered = [
        "mock-market-overview",
        "mock-news-section",
        "mock-coin-price-section",
        "mock-us-stock-section",
        "mock-kr-stock-section",
        "mock-altcoin-season-section",
        "mock-market-detail-section",
    ]
    positions = [source.index(token) for token in ordered]
    assert positions == sorted(positions)
