"""Tests for AlertCooldown — 쿨다운 헬퍼 (notification_dispatcher에 캡슐화됨)."""

from __future__ import annotations

from app.notification_dispatcher import AlertCooldown


class TestAlertCooldown:
    def test_not_active_initially(self):
        cooldown = AlertCooldown()
        assert cooldown.is_active("BTC/USDT:emergency") is False

    def test_active_after_set(self):
        cooldown = AlertCooldown()
        cooldown.set("BTC/USDT:emergency")
        assert cooldown.is_active("BTC/USDT:emergency") is True

    def test_not_active_with_zero_cooldown(self):
        # 쿨다운 타입 지정 없이 is_active 호출 시 기본 쿨다운(1h) 적용
        # seconds 파라미터 제거됨 — 유형별 쿨다운으로 대체
        cooldown = AlertCooldown()
        assert cooldown.is_active("BTC/USDT:emergency") is False

    def test_symbols_independent(self):
        cooldown = AlertCooldown()
        cooldown.set("BTC/USDT:emergency")
        assert cooldown.is_active("ETH/USDT:emergency") is False

    def test_alert_types_independent(self):
        cooldown = AlertCooldown()
        cooldown.set("BTC/USDT:emergency")
        assert cooldown.is_active("BTC/USDT:whale") is False

    def test_set_twice_still_active(self):
        cooldown = AlertCooldown()
        cooldown.set("BTC/USDT:emergency")
        cooldown.set("BTC/USDT:emergency")
        assert cooldown.is_active("BTC/USDT:emergency") is True

    def test_multiple_symbols_independent(self):
        cooldown = AlertCooldown()
        cooldown.set("BTC/USDT:emergency")
        cooldown.set("ETH/USDT:whale")
        assert cooldown.is_active("BTC/USDT:emergency") is True
        assert cooldown.is_active("ETH/USDT:whale") is True
        assert cooldown.is_active("ETH/USDT:emergency") is False
        assert cooldown.is_active("BTC/USDT:whale") is False
