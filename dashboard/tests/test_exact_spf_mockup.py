"""SPF 목업 화면 구조 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_app_shell_uses_ticker_strip_and_top_navigation():
    source = APP_TSX.read_text(encoding="utf-8")

    # 밝은 시안: 시세 띠(실제 데이터) + 위쪽 묶음 메뉴 + 모바일 하단 탭이 셸을 구성한다. 사이드바는 없다
    assert "mock-top-ticker" not in source
    assert "mock-brand-mark" not in source
    assert "shell-sidebar" not in source
    assert "<TickerStrip>" in source
    assert "shell-masthead" in source
    assert "shell-link" in source
    assert "shell-bottom" in source
    assert "API 연동" not in source
    assert "기본 계정" not in source
    assert "mock-ticker-strip" not in source


def test_dashboard_uses_exact_spf_mockup_sections():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "mock-spf-dashboard" in source
    assert "dash-mood" in source
    assert "dash-strip" in source
    assert "dash-top" in source
    assert "mock-news-section" in source
    assert "mock-coin-price-section" in source
    assert "mock-kr-stock-section" in source
    assert "mock-altcoin-season-section" in source
    assert "mock-market-detail-section" in source


def test_css_contains_mockup_desktop_and_mobile_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".shell-masthead" in source
    assert ".shell-ticker" in source
    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr 1.35fr" in source
    assert ".mock-spf-hero" in source
    assert ".shell-bottom" in source
    assert "@media (max-width: 760px)" in source
