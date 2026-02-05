"""
Tests für MetricsCalculator
"""

from datetime import datetime


class TestMetricsCalculator:
    """Tests für Risk-Metriken Berechnungen"""

    def test_sharpe_ratio_positive(self, sample_returns, reset_new_singletons):
        """Test Sharpe Ratio Berechnung mit positiven Returns"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        sharpe = calc.calculate_sharpe_ratio(sample_returns)

        # Sharpe sollte eine Zahl sein
        assert isinstance(sharpe, float)
        # Bei leicht positiven Returns sollte Sharpe in vernünftigem Bereich sein
        assert -10 < sharpe < 10

    def test_sortino_ratio(self, sample_returns, reset_new_singletons):
        """Test Sortino Ratio Berechnung"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        sortino = calc.calculate_sortino_ratio(sample_returns)

        assert isinstance(sortino, float)
        assert -20 < sortino < 20

    def test_max_drawdown(self, sample_returns, reset_new_singletons):
        """Test Maximum Drawdown Berechnung"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        mdd = calc.calculate_max_drawdown(sample_returns)

        # Drawdown sollte eine Zahl sein
        assert isinstance(mdd, float)
        # Max Drawdown ist typischerweise <= 1
        assert mdd <= 1

    def test_var_calculation(self, sample_returns, reset_new_singletons):
        """Test Value at Risk Berechnung"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        var_95 = calc.calculate_var(sample_returns, confidence=0.95)
        var_99 = calc.calculate_var(sample_returns, confidence=0.99)

        # VaR sollte Zahlen sein
        assert isinstance(var_95, float)
        assert isinstance(var_99, float)

    def test_cvar_calculation(self, sample_returns, reset_new_singletons):
        """Test Conditional VaR Berechnung"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        cvar = calc.calculate_cvar(sample_returns, confidence=0.95)

        assert isinstance(cvar, float)

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc1 = MetricsCalculator.get_instance()
        calc2 = MetricsCalculator.get_instance()

        assert calc1 is calc2

    def test_calculator_initialization(self, reset_new_singletons):
        """Test Calculator Initialisierung"""
        from src.analysis.metrics_calculator import MetricsCalculator

        calc = MetricsCalculator()
        assert calc is not None


class TestRiskMetrics:
    """Tests für RiskMetrics Dataclass"""

    def test_risk_metrics_creation(self):
        """Test RiskMetrics Erstellung"""
        from src.analysis.metrics_calculator import RiskMetrics

        metrics = RiskMetrics(
            timestamp=datetime.now(),
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            volatility_daily=0.03,
            volatility_weekly=0.07,
            current_drawdown=0.05,
            max_drawdown=0.15,
            var_95=0.05,
            var_99=0.08,
            cvar_95=0.07,
            cvar_99=0.10,
            kelly_fraction=0.25,
            half_kelly=0.125,
            optimal_position_size=500.0,
            win_rate=0.60,
            profit_factor=1.8,
            avg_win=50.0,
            avg_loss=30.0,
            consecutive_wins=3,
            consecutive_losses=1,
        )

        assert metrics.sharpe_ratio == 1.5
        assert metrics.half_kelly == 0.125
        assert metrics.win_rate == 0.60


class TestPositionSizeResult:
    """Tests für PositionSizeResult Dataclass"""

    def test_position_size_result_creation(self):
        """Test PositionSizeResult Erstellung"""
        from src.analysis.metrics_calculator import PositionSizeResult

        result = PositionSizeResult(
            recommended_size=1000.0,
            max_size=2500.0,
            risk_budget_used=0.02,
            cvar_contribution=0.05,
            kelly_fraction=0.15,
            method_used="CVaR-Kelly Hybrid",
            constraints_hit=["max_position"],
        )

        assert result.recommended_size == 1000.0
        assert result.method_used == "CVaR-Kelly Hybrid"
        assert "max_position" in result.constraints_hit
