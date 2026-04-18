"""알트코인 시즌 지수 컬렉터 테스트."""

import pytest
from dashboard.backend.collectors.altcoin_season import _season_label


class TestSeasonLabel:
    def test_altcoin_season_at_75(self):
        assert _season_label(75) == "altcoin_season"

    def test_altcoin_season_at_100(self):
        assert _season_label(100) == "altcoin_season"

    def test_neutral_at_25(self):
        assert _season_label(25) == "neutral"

    def test_neutral_at_50(self):
        assert _season_label(50) == "neutral"

    def test_neutral_at_74(self):
        assert _season_label(74) == "neutral"

    def test_bitcoin_season_at_24(self):
        assert _season_label(24) == "bitcoin_season"

    def test_bitcoin_season_at_0(self):
        assert _season_label(0) == "bitcoin_season"
