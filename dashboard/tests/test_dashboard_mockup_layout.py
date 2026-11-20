"""대시보드 목업 반응형 UI 계약 테스트."""

from __future__ import annotations

from pathlib import Path


DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")
RESEARCH_TSX = Path("dashboard/frontend/src/components/screens/Research.tsx")


def test_dashboard_uses_mockup_card_layout_classes():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "mock-spf-dashboard" in source
    assert "mock-real-stack" in source
    assert "dash-mood" in source
    assert "dash-strip" in source
    assert "dash-top" in source
    assert "mock-news-section" in source
    assert "mock-coin-price-section" in source
    assert "mock-us-stock-section" in source
    assert "mock-kr-stock-section" in source
    assert "mock-market-detail-section" in source


def test_dashboard_css_matches_desktop_mockup_grid():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr 1.35fr" in source
    assert ".mock-spf-hero" in source
    assert "min-height: 266px" in source
    assert ".mock-main-chart" in source
    assert "height: 226px" in source
    assert ".mock-horizon-grid" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in source


def test_dashboard_css_has_mobile_mockup_stack():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert "@media (max-width: 760px)" in source
    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr" in source
    assert ".shell-bottom" in source
    assert ".mock-spf-hero" in source


def test_market_main_cards_are_compact_in_mock_shell():
    source = INDEX_CSS.read_text(encoding="utf-8")
    overview_grid = source[source.index(".mock-overview-grid {"):source.index(".mock-compact-grid {")]

    assert ".mock-data-card" in source
    assert "min-height: 132px" in source
    assert ".mock-market-overview .dashboard-market-card" in source
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))" in overview_grid
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" not in overview_grid


def test_research_screen_uses_common_page_spacing():
    source = RESEARCH_TSX.read_text(encoding="utf-8")

    assert "maxWidth: 1200" not in source
    assert "margin: '0 auto'" not in source
    assert "padding: '20px 16px'" not in source
    assert "display: 'flex'" in source
    assert "flexDirection: 'column'" in source


def test_mobile_coin_and_stock_cards_scroll_horizontally_at_desktop_card_width():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".mock-market-overview .mock-overview-grid" in source
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in source
    assert ".mock-coin-price-section .mock-compact-grid" in source
    assert ".mock-us-stock-section .mock-compact-grid" in source
    assert ".mock-kr-stock-section .mock-compact-grid" in source
    card_grid_start = source.index(".mock-coin-price-section .mock-compact-grid")
    mobile_card_grid = source[card_grid_start:source.index(".mock-record-card", card_grid_start)]
    assert "grid-auto-flow: column" in mobile_card_grid
    assert "grid-auto-columns: 170px" in mobile_card_grid
    assert "overflow-x: auto" in mobile_card_grid
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" not in mobile_card_grid


def test_mobile_index_card_value_row_wraps_without_clipping_change_percent():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".dashboard-index-value-row" in source
    row_start = source.index(".dashboard-index-value-row {")
    row_block = source[row_start:source.index("}", row_start)]
    assert "flex-wrap: wrap" in row_block
    assert "min-width: 0" in row_block

    value_start = source.index(".dashboard-main-value {")
    value_block = source[value_start:source.index("}", value_start)]
    assert "overflow-wrap: anywhere" in value_block


def test_stock_index_card_does_not_render_touch_sticky_sparkline_tooltip():
    source = Path("dashboard/frontend/src/components/shared/StockIndexCard.tsx").read_text(encoding="utf-8")

    assert "<Tooltip" not in source

def test_dashboard_stock_grid_and_price_strip_avoid_lonely_cards():
    css = INDEX_CSS.read_text(encoding="utf-8")
    tsx = DASHBOARD_TSX.read_text(encoding="utf-8")

    # 주식 슬롯 7개: 768~1279px 4열(4+3), 1280px 이상 7열
    start = css.index(".mock-us-stock-section .mock-compact-grid,")
    block = css[start:css.index(".stock-card-name", start)]
    assert "repeat(4, minmax(0, 1fr))" in block
    assert "@media (min-width: 1024px)" in css[start - 80:start]
    assert "repeat(7, minmax(0, 1fr))" in block

    # 가격 띠: 칸 수를 CSS 변수로 넘겨 1280px 이상은 한 줄, 그 아래는 두 줄로 고르게
    assert "'--dash-cols': cells.length" in tsx
    assert "Math.ceil(cells.length / 2)" in tsx
    strip = css[css.index(".dash-strip-grid {"):css.index(".dash-strip-editor {")]
    # 한 줄 기준은 1366px, 값 글자 규칙은 기본 규칙 뒤에 있어야 덮어쓰이지 않는다
    assert strip.index(".dash-cell-price {") < strip.index("@media (min-width: 1366px)")
    assert "repeat(var(--dash-cols, 11), minmax(max-content, 1fr))" in strip
    assert "repeat(var(--dash-cols-half, 6), minmax(max-content, 1fr))" in strip
    # 768~1023px은 기존 auto-fit, 두 줄 규칙은 1024px부터
    assert "repeat(auto-fit, minmax(96px, 1fr))" in strip
    assert strip.index("@media (min-width: 1024px)") < strip.index("--dash-cols-half, 6")
