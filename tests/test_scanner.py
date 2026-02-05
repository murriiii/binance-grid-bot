"""
Tests für CoinScanner und Opportunity.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.scanner.coin_scanner import CoinScanner
from src.scanner.opportunity import (
    Opportunity,
    OpportunityDirection,
    OpportunityRisk,
)


class TestOpportunity:
    """Tests für Opportunity Dataclass."""

    def test_opportunity_creation(self):
        """Test dass Opportunity korrekt erstellt wird."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            technical_score=0.7,
            volume_score=0.6,
            sentiment_score=0.5,
            whale_score=0.4,
            momentum_score=0.6,
        )

        assert opp.symbol == "BTCUSDT"
        assert opp.category == "LARGE_CAP"
        assert opp.technical_score == 0.7
        assert opp.direction == OpportunityDirection.NEUTRAL
        assert opp.risk_level == OpportunityRisk.MEDIUM

    def test_calculate_total_score_default_weights(self):
        """Test Gesamtscore-Berechnung mit Default-Gewichten."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            technical_score=0.8,
            volume_score=0.6,
            sentiment_score=0.5,
            whale_score=0.4,
            momentum_score=0.7,
        )

        score = opp.calculate_total_score()

        # Expected: 0.8*0.3 + 0.6*0.2 + 0.5*0.15 + 0.4*0.15 + 0.7*0.2
        # = 0.24 + 0.12 + 0.075 + 0.06 + 0.14 = 0.635
        assert 0.63 <= score <= 0.64

    def test_calculate_total_score_custom_weights(self):
        """Test Gesamtscore-Berechnung mit custom Gewichten."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            technical_score=1.0,
            volume_score=0.0,
            sentiment_score=0.0,
            whale_score=0.0,
            momentum_score=0.0,
        )

        # 100% Gewicht auf technical
        score = opp.calculate_total_score({"technical": 1.0})

        assert score == 1.0

    def test_determine_direction_long(self):
        """Test Richtungsbestimmung LONG."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            total_score=0.7,
            signals=["RSI Oversold", "Bullish Divergence", "Support Level"],
        )

        direction = opp.determine_direction()

        assert direction == OpportunityDirection.LONG

    def test_determine_direction_short(self):
        """Test Richtungsbestimmung SHORT."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            total_score=0.7,
            signals=["RSI Overbought", "Bearish Cross", "Resistance Level"],
        )

        direction = opp.determine_direction()

        assert direction == OpportunityDirection.SHORT

    def test_determine_direction_neutral(self):
        """Test Richtungsbestimmung NEUTRAL."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            total_score=0.4,  # Low score
            signals=["RSI Neutral"],
        )

        direction = opp.determine_direction()

        assert direction == OpportunityDirection.NEUTRAL

    def test_determine_risk_low(self):
        """Test Risiko-Level LOW."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            total_score=0.8,
            confidence=0.8,
        )

        risk = opp.determine_risk()

        assert risk == OpportunityRisk.LOW

    def test_determine_risk_high(self):
        """Test Risiko-Level HIGH."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            total_score=0.2,
            confidence=0.3,
        )

        risk = opp.determine_risk()

        assert risk == OpportunityRisk.HIGH

    def test_to_dict(self):
        """Test Konvertierung zu Dictionary."""
        opp = Opportunity(
            symbol="BTCUSDT",
            category="LARGE_CAP",
            technical_score=0.7,
            total_score=0.65,
            confidence=0.6,
            direction=OpportunityDirection.LONG,
            signals=["Test Signal"],
            risk_level=OpportunityRisk.MEDIUM,
            current_price=Decimal("50000"),
        )

        d = opp.to_dict()

        assert d["symbol"] == "BTCUSDT"
        assert d["category"] == "LARGE_CAP"
        assert d["technical_score"] == 0.7
        assert d["direction"] == "LONG"
        assert d["risk_level"] == "MEDIUM"
        assert d["current_price"] == 50000.0

    def test_from_dict(self):
        """Test Erstellung aus Dictionary."""
        data = {
            "symbol": "ETHUSDT",
            "category": "LARGE_CAP",
            "timestamp": "2024-01-15T10:00:00",
            "technical_score": 0.6,
            "volume_score": 0.5,
            "sentiment_score": 0.4,
            "whale_score": 0.3,
            "momentum_score": 0.5,
            "total_score": 0.5,
            "confidence": 0.6,
            "direction": "LONG",
            "signals": ["Test"],
            "risk_level": "LOW",
            "current_price": "3000",
            "volume_24h": "1000000",
        }

        opp = Opportunity.from_dict(data)

        assert opp.symbol == "ETHUSDT"
        assert opp.technical_score == 0.6
        assert opp.direction == OpportunityDirection.LONG
        assert opp.risk_level == OpportunityRisk.LOW
        assert opp.current_price == Decimal("3000")


class TestCoinScanner:
    """Tests für CoinScanner."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton zwischen Tests."""
        CoinScanner.reset_instance()
        yield
        CoinScanner.reset_instance()

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_singleton_pattern(self, mock_psycopg2):
        """Test dass Singleton-Pattern funktioniert."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner1 = CoinScanner.get_instance()
        scanner2 = CoinScanner.get_instance()

        assert scanner1 is scanner2

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_set_weights(self, mock_psycopg2):
        """Test Setzen von benutzerdefinierten Gewichten."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()
        scanner.set_weights({"technical": 0.5, "volume": 0.5})

        # Weights sollten normalisiert sein
        total = sum(scanner._weights.values())
        assert abs(total - 1.0) < 0.01

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_default_weights(self, mock_psycopg2):
        """Test Default Score Weights."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()

        # Default weights should sum to 1.0
        assert abs(sum(scanner._weights.values()) - 1.0) < 0.01
        assert scanner._weights["technical"] == 0.30
        assert scanner._weights["volume"] == 0.20

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_scan_stats_empty(self, mock_psycopg2):
        """Test Stats bei leerem Scan."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()
        stats = scanner.get_scan_stats()

        assert stats["last_scan"] is None
        assert stats["total_opportunities"] == 0

    @patch("src.scanner.coin_scanner.psycopg2")
    @patch("src.data.watchlist.get_watchlist_manager")
    def test_scan_opportunities_no_coins(self, mock_watchlist, mock_psycopg2):
        """Test Scan ohne Coins in Watchlist."""
        mock_psycopg2.connect.return_value = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_tradeable_coins.return_value = []
        mock_watchlist.return_value = mock_manager

        scanner = CoinScanner()
        opportunities = scanner.scan_opportunities()

        assert opportunities == []

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_get_top_opportunities(self, mock_psycopg2):
        """Test Abrufen der Top Opportunities."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()

        # Manuell Opportunities setzen
        scanner._cached_opportunities = [
            Opportunity(symbol="BTC", category="LARGE_CAP", total_score=0.9),
            Opportunity(symbol="ETH", category="LARGE_CAP", total_score=0.8),
            Opportunity(symbol="SOL", category="MID_CAP", total_score=0.7),
            Opportunity(symbol="AVAX", category="MID_CAP", total_score=0.6),
        ]
        scanner._last_scan = datetime.now()

        top_3 = scanner.get_top_opportunities(3)

        assert len(top_3) == 3
        assert top_3[0].symbol == "BTC"
        assert top_3[0].total_score == 0.9

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_get_opportunities_by_category(self, mock_psycopg2):
        """Test Filtern nach Kategorie."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()

        scanner._cached_opportunities = [
            Opportunity(symbol="BTC", category="LARGE_CAP", total_score=0.9),
            Opportunity(symbol="ETH", category="LARGE_CAP", total_score=0.8),
            Opportunity(symbol="SOL", category="MID_CAP", total_score=0.7),
        ]
        scanner._last_scan = datetime.now()

        large_caps = scanner.get_top_opportunities(10, category="LARGE_CAP")

        assert len(large_caps) == 2
        assert all(o.category == "LARGE_CAP" for o in large_caps)

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_get_opportunities_by_direction(self, mock_psycopg2):
        """Test Filtern nach Richtung."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()

        scanner._cached_opportunities = [
            Opportunity(
                symbol="BTC",
                category="LARGE_CAP",
                total_score=0.9,
                direction=OpportunityDirection.LONG,
            ),
            Opportunity(
                symbol="ETH",
                category="LARGE_CAP",
                total_score=0.8,
                direction=OpportunityDirection.SHORT,
            ),
            Opportunity(
                symbol="SOL",
                category="MID_CAP",
                total_score=0.7,
                direction=OpportunityDirection.LONG,
            ),
        ]
        scanner._last_scan = datetime.now()

        longs = scanner.get_top_opportunities(10, direction=OpportunityDirection.LONG)

        assert len(longs) == 2
        assert all(o.direction == OpportunityDirection.LONG for o in longs)

    @patch("src.scanner.coin_scanner.psycopg2")
    def test_get_opportunities_by_risk(self, mock_psycopg2):
        """Test Filtern nach Risiko."""
        mock_psycopg2.connect.return_value = MagicMock()

        scanner = CoinScanner()

        scanner._cached_opportunities = [
            Opportunity(
                symbol="BTC",
                category="LARGE_CAP",
                total_score=0.9,
                risk_level=OpportunityRisk.LOW,
            ),
            Opportunity(
                symbol="ETH",
                category="LARGE_CAP",
                total_score=0.8,
                risk_level=OpportunityRisk.MEDIUM,
            ),
            Opportunity(
                symbol="SOL",
                category="MID_CAP",
                total_score=0.7,
                risk_level=OpportunityRisk.HIGH,
            ),
        ]
        scanner._last_scan = datetime.now()

        low_risk = scanner.get_opportunities_by_risk(OpportunityRisk.LOW)

        assert len(low_risk) == 1
        assert low_risk[0].symbol == "BTC"


class TestOpportunityEnums:
    """Tests für Opportunity Enums."""

    def test_direction_values(self):
        """Test OpportunityDirection Werte."""
        assert OpportunityDirection.LONG.value == "LONG"
        assert OpportunityDirection.SHORT.value == "SHORT"
        assert OpportunityDirection.NEUTRAL.value == "NEUTRAL"

    def test_risk_values(self):
        """Test OpportunityRisk Werte."""
        assert OpportunityRisk.LOW.value == "LOW"
        assert OpportunityRisk.MEDIUM.value == "MEDIUM"
        assert OpportunityRisk.HIGH.value == "HIGH"

    def test_direction_from_string(self):
        """Test Enum-Erstellung aus String."""
        direction = OpportunityDirection("LONG")
        assert direction == OpportunityDirection.LONG

    def test_risk_from_string(self):
        """Test Enum-Erstellung aus String."""
        risk = OpportunityRisk("HIGH")
        assert risk == OpportunityRisk.HIGH
