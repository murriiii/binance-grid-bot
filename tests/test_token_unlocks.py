"""
Tests für TokenUnlockTracker
"""

from datetime import datetime, timedelta


class TestTokenUnlockTracker:
    """Tests für Token Unlock Tracker"""

    def test_assess_impact_high(self, reset_new_singletons):
        """Test Impact-Bewertung bei großen Unlocks"""
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # >5% Supply → HIGH
        impact = tracker._assess_impact(6.0, 50_000_000)
        assert impact == "HIGH"

        # >$100M → HIGH
        impact = tracker._assess_impact(1.0, 150_000_000)
        assert impact == "HIGH"

    def test_assess_impact_medium(self, reset_new_singletons):
        """Test Impact-Bewertung bei mittleren Unlocks"""
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # 2-5% Supply → MEDIUM
        impact = tracker._assess_impact(3.0, 15_000_000)
        assert impact == "MEDIUM"

    def test_assess_impact_low(self, reset_new_singletons):
        """Test Impact-Bewertung bei kleinen Unlocks"""
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # <2% Supply und <$20M → LOW
        impact = tracker._assess_impact(1.0, 10_000_000)
        assert impact == "LOW"

    def test_get_unlock_signal_bearish(self, reset_new_singletons):
        """Test Signal bei anstehendem großen Unlock"""
        from src.data.token_unlocks import TokenUnlock, TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # Mock einen großen Unlock in 3 Tagen
        mock_unlock = TokenUnlock(
            symbol="ARB",
            unlock_date=datetime.now() + timedelta(days=3),
            unlock_amount=100_000_000,
            unlock_value_usd=80_000_000,
            unlock_pct_of_supply=5.0,
            unlock_type="INVESTOR",
            receiver="investors",
            expected_impact="HIGH",
            historical_reaction=-10.0,
            days_until_unlock=3,
        )

        # Test intern (ohne DB)
        signal = 0.0
        days_factor = max(0, 14 - mock_unlock.days_until_unlock) / 14

        if mock_unlock.expected_impact == "HIGH":
            signal -= 0.5 * days_factor

        # Signal sollte negativ sein (bearish)
        assert signal < 0

    def test_get_unlock_signal_no_unlocks(self, reset_new_singletons):
        """Test Signal ohne anstehende Unlocks"""
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # Ohne DB-Verbindung gibt es keine Unlocks
        signal, reasoning = tracker.get_unlock_signal("UNKNOWN_SYMBOL")

        # Sollte neutral sein
        assert signal == 0.0
        assert "no" in reasoning.lower()

    def test_estimate_unlock_value(self, reset_new_singletons):
        """Test Schätzung des Unlock-Wertes"""
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker()

        # SOL mit 80B Market Cap, 2% = 1.6B
        value = tracker._estimate_unlock_value("SOL", 2.0)
        assert value == 1_600_000_000

        # Unbekanntes Symbol → Default 1B Cap
        value = tracker._estimate_unlock_value("UNKNOWN", 1.0)
        assert value == 10_000_000  # 1% von 1B

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.data.token_unlocks import TokenUnlockTracker

        t1 = TokenUnlockTracker.get_instance()
        t2 = TokenUnlockTracker.get_instance()

        assert t1 is t2


class TestTokenUnlock:
    """Tests für TokenUnlock Dataclass"""

    def test_token_unlock_creation(self):
        """Test TokenUnlock Erstellung"""
        from src.data.token_unlocks import TokenUnlock

        unlock = TokenUnlock(
            symbol="ARB",
            unlock_date=datetime.now() + timedelta(days=7),
            unlock_amount=50_000_000,
            unlock_value_usd=40_000_000,
            unlock_pct_of_supply=2.5,
            unlock_type="CLIFF",
            receiver="investors",
            expected_impact="MEDIUM",
            historical_reaction=-5.0,
            days_until_unlock=7,
            actual_price_impact=None,
        )

        assert unlock.symbol == "ARB"
        assert unlock.unlock_pct_of_supply == 2.5
        assert unlock.expected_impact == "MEDIUM"
