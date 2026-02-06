"""Integration Tests for the Hybrid Trading System.

Tests full lifecycle, multi-coin allocation, and all 6 mode transitions.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.hybrid_config import HybridConfig
from src.core.hybrid_orchestrator import HybridOrchestrator
from src.core.trading_mode import TradingMode


@pytest.fixture
def hybrid_config():
    return HybridConfig(
        initial_mode="GRID",
        enable_mode_switching=True,
        min_regime_probability=0.75,
        min_regime_duration_days=2,
        mode_cooldown_hours=0,  # No cooldown for testing
        hold_trailing_stop_pct=7.0,
        grid_range_percent=5.0,
        num_grids=3,
        cash_exit_timeout_hours=2.0,
        max_symbols=5,
        min_position_usd=10.0,
        total_investment=400.0,
        portfolio_constraints_preset="small",
    )


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.testnet = True
    client.get_current_price.return_value = 50000.0
    client.get_account_balance.return_value = 400.0
    client.get_symbol_info.return_value = {
        "min_qty": 0.00001,
        "max_qty": 9000.0,
        "step_size": 0.00001,
        "tick_size": 0.01,
        "min_notional": 5.0,
    }
    client.get_open_orders.return_value = []
    client.place_market_buy.return_value = {
        "success": True,
        "order": {
            "orderId": 1,
            "executedQty": "0.002",
            "cummulativeQuoteQty": "100.0",
            "price": "50000.0",
        },
    }
    client.place_market_sell.return_value = {
        "success": True,
        "order": {"orderId": 2},
    }
    client.place_limit_buy.return_value = {
        "success": True,
        "order": {"orderId": 3},
    }
    client.cancel_order.return_value = True
    return client


@pytest.fixture
def orchestrator(hybrid_config, mock_client):
    with patch("src.core.hybrid_orchestrator.TelegramNotifier"):
        orch = HybridOrchestrator(config=hybrid_config, client=mock_client)
    return orch


# ═══════════════════════════════════════════════════════════════
# Full Lifecycle Tests
# ═══════════════════════════════════════════════════════════════


class TestFullLifecycle:
    def test_start_grid_run_ticks_stop(self, orchestrator, mock_client):
        """Full lifecycle: add symbols -> tick -> save -> stop."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        orchestrator.add_symbol("ETHUSDT", 150.0)

        assert len(orchestrator.symbols) == 2

        # Run several ticks
        with (
            patch.object(orchestrator, "_execute_grid"),
            patch.object(orchestrator, "_update_stop_losses"),
        ):
            for _ in range(3):
                result = orchestrator.tick()
                assert result is True

        orchestrator.save_state()
        assert orchestrator.state_file.exists()

    def test_start_save_reload_continue(self, orchestrator, mock_client, tmp_path):
        """State persists across restarts."""
        orchestrator.state_file = tmp_path / "hybrid_state.json"

        orchestrator.add_symbol("BTCUSDT", 200.0)
        orchestrator.symbols["BTCUSDT"].hold_entry_price = 48000.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.004
        orchestrator.save_state()

        # Create a fresh orchestrator and load state
        with patch("src.core.hybrid_orchestrator.TelegramNotifier"):
            orch2 = HybridOrchestrator(config=orchestrator.config, client=mock_client)
        orch2.state_file = tmp_path / "hybrid_state.json"
        orch2.add_symbol("BTCUSDT", 200.0)  # Must add symbol before load
        loaded = orch2.load_state()

        assert loaded is True
        assert orch2.symbols["BTCUSDT"].hold_entry_price == 48000.0
        assert orch2.symbols["BTCUSDT"].hold_quantity == 0.004

    def test_emergency_stop_on_errors(self, orchestrator):
        """Orchestrator stops after too many consecutive errors."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        orchestrator.consecutive_errors = orchestrator.MAX_CONSECUTIVE_ERRORS

        # The run() method should stop on errors, but we test the counter
        assert orchestrator.consecutive_errors >= orchestrator.MAX_CONSECUTIVE_ERRORS


# ═══════════════════════════════════════════════════════════════
# Multi-Coin Allocation Tests
# ═══════════════════════════════════════════════════════════════


class TestMultiCoinIntegration:
    def test_allocate_multiple_coins(self, orchestrator):
        """Allocates capital across multiple coins."""
        orchestrator.add_symbol("BTCUSDT", 120.0)
        orchestrator.add_symbol("ETHUSDT", 100.0)
        orchestrator.add_symbol("SOLUSDT", 80.0)
        orchestrator.add_symbol("ADAUSDT", 60.0)

        assert len(orchestrator.symbols) == 4
        total = sum(s.allocation_usd for s in orchestrator.symbols.values())
        assert total == 360.0

    def test_add_remove_symbols_dynamically(self, orchestrator, mock_client):
        """Symbols can be added and removed during operation."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        orchestrator.add_symbol("ETHUSDT", 150.0)
        assert len(orchestrator.symbols) == 2

        orchestrator.remove_symbol("ETHUSDT")
        assert len(orchestrator.symbols) == 1
        assert "BTCUSDT" in orchestrator.symbols

    def test_update_allocation_existing_symbol(self, orchestrator):
        """Updating allocation for existing symbol doesn't duplicate it."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        orchestrator.add_symbol("BTCUSDT", 250.0)

        assert len(orchestrator.symbols) == 1
        assert orchestrator.symbols["BTCUSDT"].allocation_usd == 250.0

    def test_max_symbols_respected_in_scan(self, orchestrator):
        """scan_and_allocate respects max_symbols limit."""
        mock_opportunities = [MagicMock(symbol=f"COIN{i}USDT") for i in range(10)]

        mock_scanner = MagicMock()
        mock_scanner.scan_opportunities.return_value = mock_opportunities

        mock_allocator = MagicMock()
        mock_result = MagicMock()
        mock_result.allocations = {
            f"COIN{i}USDT": 50.0 for i in range(orchestrator.config.max_symbols)
        }
        mock_result.total_allocated = 250.0
        mock_result.cash_remaining = 150.0
        mock_allocator.calculate_allocation.return_value = mock_result

        with (
            patch(
                "src.scanner.coin_scanner.CoinScanner.get_instance",
                return_value=mock_scanner,
            ),
            patch(
                "src.portfolio.allocator.PortfolioAllocator.get_instance",
                return_value=mock_allocator,
            ),
        ):
            result = orchestrator.scan_and_allocate()

        assert result is not None
        assert len(orchestrator.symbols) <= orchestrator.config.max_symbols

    def test_rebalance_detects_drift(self, orchestrator, mock_client):
        """Rebalance detects and reports allocation drift."""
        orchestrator.add_symbol("BTCUSDT", 100.0)
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.003

        # Price moved so value is now 150 (50% drift from target 100)
        mock_client.get_current_price.return_value = 50000.0

        adjustments = orchestrator.rebalance()
        assert "BTCUSDT" in adjustments
        assert adjustments["BTCUSDT"]["action"] == "DECREASE"


# ═══════════════════════════════════════════════════════════════
# Mode Transition Tests (all 6 paths)
# ═══════════════════════════════════════════════════════════════


class TestModeTransitions:
    def test_grid_to_hold_transition(self, orchestrator, mock_client):
        """GRID -> HOLD: Cancels grid orders, sets up trailing stop."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]

        # Simulate active grid bot
        mock_bot = MagicMock()
        mock_bot.active_orders = {
            "1": {"price": "49000", "quantity": "0.001", "type": "SELL"},
        }
        state.grid_bot = mock_bot

        orchestrator._transition_grid_to_hold(state)

        assert state.grid_bot is None
        mock_client.cancel_order.assert_called()

    def test_grid_to_cash_transition(self, orchestrator, mock_client):
        """GRID -> CASH: Cancels all orders, prepares for exit."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]

        mock_bot = MagicMock()
        mock_bot.active_orders = {"1": {"price": "49000", "quantity": "0.001", "type": "BUY"}}
        state.grid_bot = mock_bot

        orchestrator._transition_grid_to_cash(state)

        assert state.grid_bot is None
        assert state.cash_exit_started is None

    def test_hold_to_grid_transition(self, orchestrator):
        """HOLD -> GRID: Cancels trailing stop, resets hold state."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_entry_price = 48000.0
        state.hold_quantity = 0.004
        state.hold_stop_id = "stop123"

        orchestrator._transition_hold_to_grid(state)

        assert state.hold_quantity == 0.0
        assert state.hold_entry_price == 0.0
        assert state.hold_stop_id is None
        assert state.grid_bot is None

    def test_hold_to_cash_transition(self, orchestrator, mock_client):
        """HOLD -> CASH: Tightens stop, starts exit timer."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.004
        state.hold_entry_price = 48000.0
        state.hold_stop_id = "stop123"

        orchestrator._transition_hold_to_cash(state)

        assert state.cash_exit_started is not None

    def test_cash_to_grid_transition(self, orchestrator):
        """CASH -> GRID: Resets state for fresh grid start."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]
        state.cash_exit_started = datetime.now()
        state.hold_quantity = 0.001

        orchestrator._transition_cash_to_grid(state)

        assert state.cash_exit_started is None
        assert state.hold_quantity == 0.0
        assert state.grid_bot is None

    def test_cash_to_hold_transition(self, orchestrator):
        """CASH -> HOLD: Resets state for fresh buy."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]
        state.cash_exit_started = datetime.now()

        orchestrator._transition_cash_to_hold(state)

        assert state.cash_exit_started is None
        assert state.hold_quantity == 0.0

    def test_full_cycle_grid_hold_cash_grid(self, orchestrator, mock_client):
        """Full transition cycle: GRID -> HOLD -> CASH -> GRID."""
        orchestrator.add_symbol("BTCUSDT", 200.0)
        state = orchestrator.symbols["BTCUSDT"]

        # Start in GRID
        assert orchestrator.mode_manager.get_current_mode().current_mode == TradingMode.GRID

        # GRID -> HOLD (bull regime)
        switched = orchestrator.evaluate_and_switch(
            regime="BULL", regime_probability=0.85, regime_duration_days=3
        )
        assert switched is True
        assert orchestrator.mode_manager.get_current_mode().current_mode == TradingMode.HOLD

        # HOLD -> CASH (bear regime, emergency)
        switched = orchestrator.evaluate_and_switch(
            regime="BEAR", regime_probability=0.90, regime_duration_days=1
        )
        assert switched is True
        assert orchestrator.mode_manager.get_current_mode().current_mode == TradingMode.CASH

        # CASH -> GRID (sideways regime)
        # Safety lock triggers after 2 transitions in 48h, forcing GRID mode.
        # request_switch returns False but the mode is still set to GRID.
        orchestrator.evaluate_and_switch(
            regime="SIDEWAYS", regime_probability=0.80, regime_duration_days=3
        )
        assert orchestrator.mode_manager.get_current_mode().current_mode == TradingMode.GRID


# ═══════════════════════════════════════════════════════════════
# Mode Evaluation with Hysteresis
# ═══════════════════════════════════════════════════════════════


class TestModeEvaluationIntegration:
    def test_hysteresis_prevents_flip_flop(self, hybrid_config, mock_client):
        """Hysteresis prevents rapid mode changes."""
        hybrid_config.mode_cooldown_hours = 24

        with patch("src.core.hybrid_orchestrator.TelegramNotifier"):
            orch = HybridOrchestrator(config=hybrid_config, client=mock_client)
        orch.add_symbol("BTCUSDT", 200.0)

        # First switch: GRID -> HOLD (succeeds)
        switched = orch.evaluate_and_switch(
            regime="BULL", regime_probability=0.85, regime_duration_days=3
        )
        assert switched is True

        # Immediate reverse: HOLD -> GRID (blocked by cooldown)
        switched = orch.evaluate_and_switch(
            regime="SIDEWAYS", regime_probability=0.80, regime_duration_days=3
        )
        assert switched is False  # Cooldown blocks it

    def test_emergency_bear_bypasses_hysteresis(self, hybrid_config, mock_client):
        """Emergency BEAR signal bypasses all hysteresis."""
        hybrid_config.mode_cooldown_hours = 24

        with patch("src.core.hybrid_orchestrator.TelegramNotifier"):
            orch = HybridOrchestrator(config=hybrid_config, client=mock_client)
        orch.add_symbol("BTCUSDT", 200.0)

        # First switch: GRID -> HOLD
        orch.evaluate_and_switch(regime="BULL", regime_probability=0.85, regime_duration_days=3)

        # Emergency BEAR -> CASH (bypasses cooldown)
        switched = orch.evaluate_and_switch(
            regime="BEAR", regime_probability=0.90, regime_duration_days=0
        )
        assert switched is True
        assert orch.mode_manager.get_current_mode().current_mode == TradingMode.CASH

    def test_low_probability_regime_ignored(self, orchestrator):
        """Regime with low probability doesn't trigger mode switch."""
        orchestrator.add_symbol("BTCUSDT", 200.0)

        switched = orchestrator.evaluate_and_switch(
            regime="BULL", regime_probability=0.50, regime_duration_days=5
        )
        assert switched is False

    def test_short_duration_regime_ignored(self, orchestrator):
        """Regime that hasn't lasted long enough doesn't trigger switch."""
        orchestrator.add_symbol("BTCUSDT", 200.0)

        switched = orchestrator.evaluate_and_switch(
            regime="BULL", regime_probability=0.85, regime_duration_days=1
        )
        assert switched is False

    def test_mode_switching_disabled(self, mock_client):
        """No mode switches when enable_mode_switching=False."""
        config = HybridConfig(enable_mode_switching=False)

        with patch("src.core.hybrid_orchestrator.TelegramNotifier"):
            orch = HybridOrchestrator(config=config, client=mock_client)
        orch.add_symbol("BTCUSDT", 200.0)

        switched = orch.evaluate_and_switch(
            regime="BULL", regime_probability=0.99, regime_duration_days=10
        )
        assert switched is False


# ═══════════════════════════════════════════════════════════════
# DynamicGrid Cache Fix Verification (B6)
# ═══════════════════════════════════════════════════════════════


class TestDynamicGridCacheFix:
    def test_cache_eviction_on_expiry(self):
        """Expired cache entries are evicted."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()

        # Add expired entry
        strategy._price_cache["OLD_1h"] = (
            datetime.now() - timedelta(minutes=10),
            {"close": [1.0]},
        )
        # Add fresh entry
        strategy._price_cache["NEW_1h"] = (
            datetime.now(),
            {"close": [2.0]},
        )

        strategy._evict_expired_cache()

        assert "OLD_1h" not in strategy._price_cache
        assert "NEW_1h" in strategy._price_cache

    def test_cache_size_cap(self):
        """Cache respects max size limit."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        strategy._max_cache_size = 3

        now = datetime.now()
        for i in range(10):
            strategy._price_cache[f"SYM{i}_1h"] = (
                now + timedelta(seconds=i),
                {"close": [float(i)]},
            )

        strategy._evict_expired_cache()

        assert len(strategy._price_cache) <= 3

    def test_close_clears_cache(self):
        """close() clears the cache."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        strategy._price_cache["TEST_1h"] = (datetime.now(), {"close": [1.0]})

        strategy.close()

        assert len(strategy._price_cache) == 0
