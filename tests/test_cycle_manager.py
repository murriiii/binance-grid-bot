"""
Tests für CycleManager
"""

from datetime import datetime, timedelta


class TestTradingCycle:
    """Tests für TradingCycle Dataclass"""

    def test_trading_cycle_creation(self):
        """Test TradingCycle Erstellung"""
        from src.core.cycle_manager import TradingCycle

        cycle = TradingCycle(
            id="cycle-123",
            cohort_id="cohort-456",
            cohort_name="balanced",
            cycle_number=1,
            start_date=datetime.now(),
            end_date=None,
            status="active",
            starting_capital=1000.0,
            ending_capital=None,
        )

        assert cycle.cycle_number == 1
        assert cycle.starting_capital == 1000.0
        assert cycle.status == "active"
        assert cycle.cohort_name == "balanced"

    def test_trading_cycle_with_metrics(self):
        """Test TradingCycle mit vollständigen Metriken"""
        from src.core.cycle_manager import TradingCycle

        cycle = TradingCycle(
            id="cycle-123",
            cohort_id="cohort-456",
            cohort_name="aggressive",
            cycle_number=5,
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now(),
            status="completed",
            starting_capital=1000.0,
            ending_capital=1150.0,
            trades_count=25,
            total_pnl=150.0,
            total_pnl_pct=15.0,
            winning_trades=15,
            losing_trades=10,
            max_drawdown=0.08,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=1.8,
            kelly_fraction=0.25,
            var_95=0.04,
            cvar_95=0.06,
        )

        assert cycle.total_pnl == 150.0
        assert cycle.sharpe_ratio == 1.5
        assert cycle.winning_trades == 15

    def test_cycle_win_rate_calculation(self):
        """Test Win Rate Berechnung"""
        from src.core.cycle_manager import TradingCycle

        cycle = TradingCycle(
            id="test",
            cohort_id="test",
            cohort_name="test",
            cycle_number=1,
            start_date=datetime.now(),
            end_date=None,
            status="active",
            starting_capital=1000.0,
            ending_capital=None,
            trades_count=20,
            winning_trades=12,
            losing_trades=8,
        )

        win_rate = cycle.winning_trades / cycle.trades_count
        assert abs(win_rate - 0.6) < 0.01


class TestCycleManager:
    """Tests für Cycle Manager"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.core.cycle_manager import CycleManager

        c1 = CycleManager.get_instance()
        c2 = CycleManager.get_instance()

        assert c1 is c2

    def test_manager_initialization(self, reset_new_singletons):
        """Test Manager Initialisierung"""
        from src.core.cycle_manager import CycleManager

        manager = CycleManager()

        # Sollte ohne Fehler initialisieren
        assert manager is not None
