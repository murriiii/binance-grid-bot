"""
Tests für CVaRPositionSizer
"""

import numpy as np


class TestCVaRPositionSizer:
    """Tests für CVaR-basiertes Position Sizing"""

    def test_calculate_var(self, sample_returns, reset_new_singletons):
        """Test VaR Berechnung"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()
        var_95 = sizer.calculate_var(sample_returns, confidence=0.95)
        var_99 = sizer.calculate_var(sample_returns, confidence=0.99)

        # VaR sollte positiv sein
        assert var_95 > 0
        assert var_99 > 0
        # 99% VaR sollte >= 95% VaR sein
        assert var_99 >= var_95

    def test_calculate_cvar(self, sample_returns, reset_new_singletons):
        """Test CVaR Berechnung"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()
        cvar = sizer.calculate_cvar(sample_returns, confidence=0.95)
        var = sizer.calculate_var(sample_returns, confidence=0.95)

        # CVaR sollte >= VaR sein
        assert cvar >= var

    def test_calculate_risk_metrics(self, sample_returns, reset_new_singletons):
        """Test Risk Metrics Berechnung"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()
        metrics = sizer.calculate_risk_metrics(sample_returns)

        assert metrics.var_95 > 0
        assert metrics.var_99 >= metrics.var_95
        assert metrics.cvar_95 >= metrics.var_95
        assert metrics.volatility > 0

    def test_calculate_position_size_basic(self, reset_new_singletons):
        """Test grundlegende Position Size Berechnung"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()

        # Mock returns im Cache
        np.random.seed(42)
        sizer._returns_cache["BTCUSDT"] = (
            __import__("datetime").datetime.now(),
            np.random.normal(0.001, 0.03, 50),
        )

        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            portfolio_value=10000.0,
            signal_confidence=0.7,
        )

        # Position sollte > 0 sein
        assert result.recommended_size > 0
        # Sollte unter Max sein
        assert result.recommended_size <= result.max_position

    def test_position_size_confidence_scaling(self, reset_new_singletons):
        """Test dass höhere Confidence zu größerer Position führt"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()

        # Mock returns
        np.random.seed(42)
        sizer._returns_cache["BTCUSDT"] = (
            __import__("datetime").datetime.now(),
            np.random.normal(0.001, 0.03, 50),
        )

        result_low = sizer.calculate_position_size(
            symbol="BTCUSDT",
            portfolio_value=10000.0,
            signal_confidence=0.3,
        )

        result_high = sizer.calculate_position_size(
            symbol="BTCUSDT",
            portfolio_value=10000.0,
            signal_confidence=0.9,
        )

        # Höhere Confidence sollte größere Position ergeben
        assert result_high.recommended_size >= result_low.recommended_size

    def test_adjust_cvar_for_regime(self, reset_new_singletons):
        """Test Regime-Anpassung"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()
        base_cvar = 0.05

        bull_cvar = sizer._adjust_cvar_for_regime(base_cvar, "BULL")
        bear_cvar = sizer._adjust_cvar_for_regime(base_cvar, "BEAR")

        # Bear sollte höheren (konservativeren) CVaR haben
        assert bear_cvar > bull_cvar

    def test_stop_loss_distance(self, reset_new_singletons):
        """Test Stop-Loss Distanz Berechnung"""
        from src.risk.cvar_sizing import CVaRPositionSizer, RiskMetrics

        sizer = CVaRPositionSizer()

        metrics = RiskMetrics(
            var_95=0.04,
            var_99=0.06,
            cvar_95=0.05,
            cvar_99=0.08,
            max_loss_observed=0.10,
            volatility=0.30,
            downside_volatility=0.20,
        )

        stop_loss = sizer.calculate_stop_loss_distance("BTCUSDT", metrics)

        # Stop-Loss sollte zwischen min und max sein
        assert 0.02 <= stop_loss <= 0.15

    def test_available_risk_budget(self, reset_new_singletons):
        """Test verfügbares Risk Budget"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        sizer = CVaRPositionSizer()

        # Keine offenen Positionen
        budget = sizer.get_available_risk_budget(
            portfolio_value=10000.0,
            open_positions=[],
        )

        assert budget == 0.10  # Max 10%

        # Mit offenen Positionen
        budget_with_pos = sizer.get_available_risk_budget(
            portfolio_value=10000.0,
            open_positions=[{"value": 2500, "cvar": 0.05}],  # 25% at 5% CVaR = 1.25%
        )

        assert budget_with_pos < budget

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.risk.cvar_sizing import CVaRPositionSizer

        s1 = CVaRPositionSizer.get_instance()
        s2 = CVaRPositionSizer.get_instance()

        assert s1 is s2


class TestPositionSizeResult:
    """Tests für PositionSizeResult Dataclass"""

    def test_position_size_result_creation(self):
        """Test PositionSizeResult Erstellung"""
        from src.risk.cvar_sizing import PositionSizeResult

        result = PositionSizeResult(
            recommended_size=1000.0,
            max_position=2500.0,
            risk_adjusted_size=1200.0,
            kelly_size=800.0,
            sizing_method="CVaR-based",
            risk_budget_used=0.02,
            confidence_multiplier=0.8,
            hit_max_position=False,
            hit_min_position=False,
            expected_max_loss=50.0,
            cvar_used=0.05,
        )

        assert result.recommended_size == 1000.0
        assert result.sizing_method == "CVaR-based"
        assert result.hit_max_position is False


class TestRiskMetrics:
    """Tests für RiskMetrics Dataclass"""

    def test_risk_metrics_creation(self):
        """Test RiskMetrics Erstellung"""
        from src.risk.cvar_sizing import RiskMetrics

        metrics = RiskMetrics(
            var_95=0.04,
            var_99=0.06,
            cvar_95=0.05,
            cvar_99=0.08,
            max_loss_observed=0.12,
            volatility=0.30,
            downside_volatility=0.22,
        )

        assert metrics.var_95 == 0.04
        assert metrics.cvar_95 == 0.05
        assert metrics.volatility == 0.30
