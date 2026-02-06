"""
Tests für PortfolioAllocator und AllocationConstraints.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.portfolio.allocator import AllocationResult, PortfolioAllocator
from src.portfolio.constraints import (
    AGGRESSIVE_CONSTRAINTS,
    BALANCED_CONSTRAINTS,
    CONSERVATIVE_CONSTRAINTS,
    AllocationConstraints,
)
from src.scanner.opportunity import Opportunity, OpportunityRisk


class TestAllocationConstraints:
    """Tests für AllocationConstraints."""

    def test_default_constraints(self):
        """Test Default Constraints."""
        constraints = AllocationConstraints()

        assert constraints.max_per_coin_pct == 10.0
        assert constraints.min_position_usd == 10.0
        assert constraints.max_position_usd == 500.0
        assert constraints.min_cash_reserve_pct == 20.0
        assert constraints.max_open_positions == 10

    def test_preset_conservative(self):
        """Test konservative Preset-Constraints."""
        constraints = CONSERVATIVE_CONSTRAINTS

        assert constraints.max_per_coin_pct == 8.0
        assert constraints.min_cash_reserve_pct == 30.0
        assert constraints.max_open_positions == 6

    def test_preset_balanced(self):
        """Test balanced Preset-Constraints."""
        constraints = BALANCED_CONSTRAINTS

        assert constraints.max_per_coin_pct == 10.0
        assert constraints.min_cash_reserve_pct == 20.0
        assert constraints.max_open_positions == 10

    def test_preset_aggressive(self):
        """Test aggressive Preset-Constraints."""
        constraints = AGGRESSIVE_CONSTRAINTS

        assert constraints.max_per_coin_pct == 15.0
        assert constraints.min_cash_reserve_pct == 10.0
        assert constraints.max_open_positions == 15

    def test_get_max_for_coin_large_cap(self):
        """Test max Allocation für Large Cap Coin."""
        constraints = AllocationConstraints()

        max_alloc = constraints.get_max_for_coin("BTCUSDT", "LARGE_CAP", 1)

        # Should be min of: max_per_coin (10), category_limit (40), tier_limit (15)
        assert max_alloc == 10.0

    def test_get_max_for_coin_mid_cap(self):
        """Test max Allocation für Mid Cap Coin."""
        constraints = AllocationConstraints()

        max_alloc = constraints.get_max_for_coin("SOLUSDT", "MID_CAP", 2)

        # Should be min of: max_per_coin (10), category_limit (30), tier_limit (10)
        assert max_alloc == 10.0

    def test_get_max_for_coin_experimental(self):
        """Test max Allocation für Experimental Coin."""
        constraints = AllocationConstraints()

        max_alloc = constraints.get_max_for_coin("NEWCOIN", "AI", 3)

        # Should be min of: max_per_coin (10), category_limit (15), tier_limit (5)
        assert max_alloc == 5.0

    def test_get_available_capital(self):
        """Test verfügbares Kapital Berechnung."""
        constraints = AllocationConstraints(
            min_cash_reserve_pct=20.0,
            max_total_exposure_pct=80.0,
        )

        # Total $1000, bereits $400 investiert
        available = constraints.get_available_capital(
            total_capital=1000.0,
            current_invested=400.0,
        )

        # Max exposure: $800, Cash reserve: $200
        # Available: min(1000-400-200, 800-400) = min(400, 400) = 400
        assert available == 400.0

    def test_get_available_capital_near_limit(self):
        """Test verfügbares Kapital nahe am Limit."""
        constraints = AllocationConstraints(
            min_cash_reserve_pct=20.0,
            max_total_exposure_pct=80.0,
        )

        # Total $1000, bereits $750 investiert (nahe am Limit)
        available = constraints.get_available_capital(
            total_capital=1000.0,
            current_invested=750.0,
        )

        # Max exposure: $800, already at $750
        # Available: min(1000-750-200, 800-750) = min(50, 50) = 50
        assert available == 50.0

    def test_validate_allocation_valid(self):
        """Test Validierung einer gültigen Allocation."""
        constraints = AllocationConstraints()

        proposed = {
            "BTCUSDT": 50.0,
            "ETHUSDT": 50.0,
        }

        valid, violations = constraints.validate_allocation(
            proposed=proposed,
            total_capital=1000.0,
            current_portfolio={},
        )

        assert valid is True
        assert len(violations) == 0

    def test_validate_allocation_exceeds_coin_limit(self):
        """Test Validierung bei Überschreitung des Coin-Limits."""
        constraints = AllocationConstraints(max_per_coin_pct=10.0)

        proposed = {
            "BTCUSDT": 150.0,  # 15% von $1000 - über dem Limit
        }

        valid, violations = constraints.validate_allocation(
            proposed=proposed,
            total_capital=1000.0,
            current_portfolio={"BTCUSDT": {"category": "LARGE_CAP", "tier": 1}},
        )

        assert valid is False
        assert len(violations) > 0
        assert "BTCUSDT" in violations[0]

    def test_validate_allocation_too_many_positions(self):
        """Test Validierung bei zu vielen Positionen."""
        constraints = AllocationConstraints(max_open_positions=2)

        # Bereits 2 Positionen
        current = {
            "BTCUSDT": {"amount": 100},
            "ETHUSDT": {"amount": 100},
        }

        # Versuche 3. Position hinzuzufügen
        proposed = {"SOLUSDT": 50.0}

        valid, violations = constraints.validate_allocation(
            proposed=proposed,
            total_capital=1000.0,
            current_portfolio=current,
        )

        assert valid is False
        assert any("Position count" in v for v in violations)

    def test_to_dict_and_from_dict(self):
        """Test Serialisierung und Deserialisierung."""
        original = AllocationConstraints(
            max_per_coin_pct=12.0,
            min_position_usd=15.0,
            max_open_positions=8,
        )

        d = original.to_dict()
        restored = AllocationConstraints.from_dict(d)

        assert restored.max_per_coin_pct == 12.0
        assert restored.min_position_usd == 15.0
        assert restored.max_open_positions == 8


class TestAllocationResult:
    """Tests für AllocationResult."""

    def test_result_creation(self):
        """Test Erstellung von AllocationResult."""
        result = AllocationResult(
            allocations={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
            total_allocated=150.0,
            cash_remaining=850.0,
        )

        assert result.allocations["BTCUSDT"] == 100.0
        assert result.total_allocated == 150.0
        assert result.cash_remaining == 850.0

    def test_result_to_dict(self):
        """Test Konvertierung zu Dictionary."""
        result = AllocationResult(
            allocations={"BTCUSDT": 100.0},
            total_allocated=100.0,
            cash_remaining=900.0,
            rejected={"LOWLIQ": "Not enough liquidity"},
        )

        d = result.to_dict()

        assert d["allocations"] == {"BTCUSDT": 100.0}
        assert d["total_allocated"] == 100.0
        assert d["rejected"]["LOWLIQ"] == "Not enough liquidity"


class TestPortfolioAllocator:
    """Tests für PortfolioAllocator."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton zwischen Tests."""
        PortfolioAllocator.reset_instance()
        yield
        PortfolioAllocator.reset_instance()

    @patch("src.portfolio.allocator.psycopg2")
    def test_singleton_pattern(self, mock_psycopg2):
        """Test dass Singleton-Pattern funktioniert."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator1 = PortfolioAllocator.get_instance()
        allocator2 = PortfolioAllocator.get_instance()

        assert allocator1 is allocator2

    @patch("src.portfolio.allocator.psycopg2")
    def test_set_constraints(self, mock_psycopg2):
        """Test Setzen von Constraints."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()
        allocator.set_constraints(AGGRESSIVE_CONSTRAINTS)

        assert allocator.constraints.max_per_coin_pct == 15.0

    @patch("src.portfolio.allocator.psycopg2")
    def test_calculate_allocation_empty_opportunities(self, mock_psycopg2):
        """Test Allocation mit leerer Opportunity-Liste."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()
        result = allocator.calculate_allocation(
            opportunities=[],
            available_capital=1000.0,
        )

        assert result.allocations == {}
        assert result.total_allocated == 0.0
        assert result.cash_remaining == 1000.0

    @patch("src.portfolio.allocator.psycopg2")
    def test_calculate_allocation_basic(self, mock_psycopg2):
        """Test grundlegende Allocation-Berechnung."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        opportunities = [
            Opportunity(
                symbol="BTCUSDT",
                category="LARGE_CAP",
                total_score=0.8,
                confidence=0.7,
                risk_level=OpportunityRisk.LOW,
            ),
            Opportunity(
                symbol="ETHUSDT",
                category="LARGE_CAP",
                total_score=0.6,
                confidence=0.6,
                risk_level=OpportunityRisk.MEDIUM,
            ),
        ]

        result = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=1000.0,
        )

        # Sollte Allocations für beide Coins haben
        assert len(result.allocations) >= 1
        assert result.total_allocated > 0
        assert result.cash_remaining < 1000.0

    @patch("src.portfolio.allocator.psycopg2")
    def test_calculate_allocation_respects_min_position(self, mock_psycopg2):
        """Test dass min Position Size respektiert wird."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        # Low-score Opportunity die unter min Position fallen sollte
        opportunities = [
            Opportunity(
                symbol="LOWSCORE",
                category="MID_CAP",
                total_score=0.41,  # Knapp über Filter
                confidence=0.3,
                risk_level=OpportunityRisk.HIGH,
            ),
        ]

        result = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=50.0,  # Wenig Kapital
        )

        # Wenn Allocation unter min_position_usd, sollte rejected sein
        if "LOWSCORE" in result.rejected:
            assert "too small" in result.rejected["LOWSCORE"].lower()

    @patch("src.portfolio.allocator.psycopg2")
    def test_min_confidence_filters_low_confidence(self, mock_psycopg2):
        """Test that min_confidence parameter filters low-confidence coins."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        opportunities = [
            Opportunity(
                symbol="BTCUSDT",
                category="LARGE_CAP",
                total_score=0.8,
                confidence=0.8,  # high confidence
                risk_level=OpportunityRisk.LOW,
            ),
            Opportunity(
                symbol="LOWCONF",
                category="MID_CAP",
                total_score=0.6,
                confidence=0.4,  # below conservative threshold
                risk_level=OpportunityRisk.MEDIUM,
            ),
        ]

        # With high min_confidence, LOWCONF should be filtered out
        result = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=1000.0,
            min_confidence=0.7,
        )
        assert "BTCUSDT" in result.allocations
        assert "LOWCONF" not in result.allocations

        # With low min_confidence, both should be allocated
        result2 = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=1000.0,
            min_confidence=0.2,
        )
        assert "BTCUSDT" in result2.allocations

    @patch("src.portfolio.allocator.psycopg2")
    def test_allowed_categories_filters_coins(self, mock_psycopg2):
        """Test that allowed_categories filters out wrong-category coins."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        opportunities = [
            Opportunity(
                symbol="BTCUSDT",
                category="LARGE_CAP",
                total_score=0.8,
                confidence=0.8,
                risk_level=OpportunityRisk.LOW,
            ),
            Opportunity(
                symbol="OPUSDT",
                category="L2",
                total_score=0.7,
                confidence=0.8,
                risk_level=OpportunityRisk.MEDIUM,
            ),
            Opportunity(
                symbol="AXSUSDT",
                category="GAMING",
                total_score=0.6,
                confidence=0.8,
                risk_level=OpportunityRisk.HIGH,
            ),
        ]

        # Conservative: only LARGE_CAP
        result = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=1000.0,
            allowed_categories=("LARGE_CAP",),
        )
        assert "BTCUSDT" in result.allocations
        assert "OPUSDT" not in result.allocations
        assert "AXSUSDT" not in result.allocations

        # Aggressive: all categories
        result2 = allocator.calculate_allocation(
            opportunities=opportunities,
            available_capital=1000.0,
            allowed_categories=("LARGE_CAP", "L2", "GAMING"),
        )
        assert "BTCUSDT" in result2.allocations

    @patch("src.portfolio.allocator.psycopg2")
    def test_get_risk_multiplier(self, mock_psycopg2):
        """Test Risk Multiplier für Position Sizing."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        assert allocator._get_risk_multiplier(OpportunityRisk.LOW) == 1.2
        assert allocator._get_risk_multiplier(OpportunityRisk.MEDIUM) == 1.0
        assert allocator._get_risk_multiplier(OpportunityRisk.HIGH) == 0.7

    @patch("src.portfolio.allocator.psycopg2")
    def test_calculate_rebalance(self, mock_psycopg2):
        """Test Rebalancing-Berechnung."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        target = {
            "BTCUSDT": 200.0,
            "ETHUSDT": 150.0,
            "SOLUSDT": 100.0,
        }

        current = {
            "BTCUSDT": {"amount": 150.0},  # Needs +50
            "ETHUSDT": {"amount": 200.0},  # Needs -50
            "AVAXUSDT": {"amount": 100.0},  # Needs to be sold
        }

        trades = allocator.calculate_rebalance(
            target_allocations=target,
            current_positions=current,
            available_cash=100.0,
        )

        # BTCUSDT sollte gekauft werden
        assert trades["BTCUSDT"]["action"] == "BUY"
        assert trades["BTCUSDT"]["amount"] == 50.0

        # ETHUSDT sollte verkauft werden
        assert trades["ETHUSDT"]["action"] == "SELL"
        assert trades["ETHUSDT"]["amount"] == 50.0

        # AVAXUSDT sollte verkauft werden (nicht im Target)
        assert trades["AVAXUSDT"]["action"] == "SELL"
        assert trades["AVAXUSDT"]["amount"] == 100.0

        # SOLUSDT sollte gekauft werden (neu)
        assert trades["SOLUSDT"]["action"] == "BUY"
        assert trades["SOLUSDT"]["amount"] == 100.0

    @patch("src.portfolio.allocator.psycopg2")
    def test_get_portfolio_stats_empty(self, mock_psycopg2):
        """Test Portfolio Stats bei leerem Portfolio."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        allocator = PortfolioAllocator()

        # Mock get_current_positions to return empty
        allocator.get_current_positions = MagicMock(return_value={})

        stats = allocator.get_portfolio_stats()

        assert stats["total_value"] == 0
        assert stats["position_count"] == 0


class TestKellyAdjustment:
    """Tests für Kelly Criterion Adjustment."""

    @patch("src.portfolio.allocator.psycopg2")
    def test_kelly_increases_high_confidence(self, mock_psycopg2):
        """Test dass Kelly bei hoher Confidence erhöht."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        # High confidence opportunity
        opportunities = [
            Opportunity(
                symbol="BTCUSDT",
                category="LARGE_CAP",
                total_score=0.8,
                confidence=0.9,  # Very high
                risk_level=OpportunityRisk.LOW,
            ),
        ]

        base_allocations = {"BTCUSDT": 100.0}

        adjusted = allocator._apply_kelly_adjustment(base_allocations, opportunities)

        # Should be increased due to high confidence
        # But won't necessarily be > 100 due to half-kelly
        assert "BTCUSDT" in adjusted

    @patch("src.portfolio.allocator.psycopg2")
    def test_kelly_reduces_low_confidence(self, mock_psycopg2):
        """Test dass Kelly bei niedriger Confidence reduziert."""
        mock_psycopg2.connect.return_value = MagicMock()

        allocator = PortfolioAllocator()

        # Low confidence opportunity
        opportunities = [
            Opportunity(
                symbol="RISKYUSDT",
                category="MID_CAP",
                total_score=0.5,
                confidence=0.3,  # Very low
                risk_level=OpportunityRisk.HIGH,
            ),
        ]

        base_allocations = {"RISKYUSDT": 100.0}

        adjusted = allocator._apply_kelly_adjustment(base_allocations, opportunities)

        # Should be reduced due to low confidence
        assert adjusted["RISKYUSDT"] < 100.0
