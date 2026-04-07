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

    def test_expires_when_seconds_zero(self):
        cooldown = AlertCooldown(seconds=0.0)
        cooldown.set("BTC/USDT:emergency")
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
