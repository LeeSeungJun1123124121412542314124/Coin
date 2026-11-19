"""SPF 목업 화면 구조 계약 테스트."""

from __future__ import annotations

from pathlib import Path


APP_TSX = Path("dashboard/frontend/src/App.tsx")
DASHBOARD_TSX = Path("dashboard/frontend/src/components/screens/Dashboard.tsx")
INDEX_CSS = Path("dashboard/frontend/src/index.css")


def test_app_shell_uses_mockup_ticker_and_sidebar():
    source = APP_TSX.read_text(encoding="utf-8")

    # 상단 티커는 리디자인에서 제거됨 — 사이드바(그룹 내비)와 모바일 하단 메뉴가 셸을 구성한다
    assert "mock-top-ticker" not in source
    assert "mock-brand-mark" not in source
    assert "shell-sidebar" in source
    assert "shell-link" in source
    assert "shell-bottom" in source
    assert "API 연동" not in source
    assert "기본 계정" not in source
    assert "mock-ticker-strip" not in source


def test_dashboard_uses_exact_spf_mockup_sections():
    source = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert "mock-spf-dashboard" in source
    assert "시장 메인 카드" in source
    assert "mock-market-overview" in source
    assert "mock-news-section" in source
    assert "mock-coin-price-section" in source
    assert "mock-kr-stock-section" in source
    assert "mock-altcoin-season-section" in source
    assert "mock-market-detail-section" in source


def test_css_contains_mockup_desktop_and_mobile_layout():
    source = INDEX_CSS.read_text(encoding="utf-8")

    assert ".shell-sidebar" in source
    assert "grid-template-columns: 232px minmax(0, 1fr)" in source
    assert ".mock-content-grid" in source
    assert "grid-template-columns: 1fr 1.35fr" in source
    assert ".mock-spf-hero" in source
    assert ".shell-bottom" in source
    assert "@media (max-width: 760px)" in source
