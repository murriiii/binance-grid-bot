"""Tests for HybridOrchestrator."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.hybrid_config import HybridConfig
from src.core.hybrid_orchestrator import HybridOrchestrator, SymbolState
from src.core.mode_manager import ModeManager
from src.core.trading_mode import TradingMode


@pytest.fixture
def config():
    return HybridConfig(
        initial_mode="GRID",
        enable_mode_switching=True,
        hold_trailing_stop_pct=7.0,
        grid_range_percent=5.0,
        num_grids=3,
        cash_exit_timeout_hours=2.0,
        total_investment=400.0,
        min_position_usd=10.0,
        max_symbols=8,
    )


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.testnet = True
    client.get_current_price.return_value = 50000.0
    client.get_account_balance.return_value = 1000.0
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
            "executedQty": "0.001",
            "cummulativeQuoteQty": "50.0",
            "price": "50000.0",
        },
    }
    client.place_market_sell.return_value = {"success": True, "order": {"orderId": 2}}
    client.place_limit_buy.return_value = {
        "success": True,
        "order": {"orderId": 100},
    }
    client.cancel_order.return_value = {"success": True}
    return client


@pytest.fixture
def orchestrator(config, mock_client):
    ModeManager.reset_instance()
    with (
        patch("src.core.hybrid_orchestrator.TelegramNotifier"),
        patch("src.core.hybrid_orchestrator.StopLossManager"),
    ):
        orch = HybridOrchestrator(config, client=mock_client)
        orch.add_symbol("BTCUSDT", 50.0)
        orch.add_symbol("ETHUSDT", 50.0)
        yield orch
    ModeManager.reset_instance()


# ------------------------------------------------------------------
# SymbolState
# ------------------------------------------------------------------


class TestSymbolState:
    def test_to_dict_roundtrip(self):
        state = SymbolState("BTCUSDT")
        state.mode = TradingMode.HOLD
        state.hold_entry_price = 50000.0
        state.hold_quantity = 0.001
        state.hold_stop_id = "stop-123"
        state.allocation_usd = 50.0
        state.cash_exit_started = datetime(2026, 1, 1, 12, 0, 0)

        data = state.to_dict()
        restored = SymbolState.from_dict(data)

        assert restored.symbol == "BTCUSDT"
        assert restored.mode == TradingMode.HOLD
        assert restored.hold_entry_price == 50000.0
        assert restored.hold_quantity == 0.001
        assert restored.hold_stop_id == "stop-123"
        assert restored.allocation_usd == 50.0
        assert restored.cash_exit_started == datetime(2026, 1, 1, 12, 0, 0)

    def test_default_values(self):
        state = SymbolState("ETHUSDT")
        assert state.mode == TradingMode.GRID
        assert state.hold_quantity == 0.0
        assert state.cash_exit_started is None


# ------------------------------------------------------------------
# Orchestrator init and symbol management
# ------------------------------------------------------------------


class TestOrchestratorInit:
    def test_init_with_config(self, config, mock_client):
        with (
            patch("src.core.hybrid_orchestrator.TelegramNotifier"),
            patch("src.core.hybrid_orchestrator.StopLossManager"),
        ):
            orch = HybridOrchestrator(config, client=mock_client)
            assert orch.config is config
            assert orch.client is mock_client
            assert len(orch.symbols) == 0

    def test_add_symbol(self, orchestrator):
        assert "BTCUSDT" in orchestrator.symbols
        assert orchestrator.symbols["BTCUSDT"].allocation_usd == 50.0

    def test_add_symbol_updates_allocation(self, orchestrator):
        orchestrator.add_symbol("BTCUSDT", 100.0)
        assert orchestrator.symbols["BTCUSDT"].allocation_usd == 100.0

    def test_remove_symbol(self, orchestrator):
        orchestrator.remove_symbol("BTCUSDT")
        assert "BTCUSDT" not in orchestrator.symbols

    def test_remove_nonexistent_symbol(self, orchestrator):
        orchestrator.remove_symbol("XYZUSDT")  # Should not raise


# ------------------------------------------------------------------
# GRID mode execution
# ------------------------------------------------------------------


class TestGridMode:
    def test_execute_grid_creates_bot(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        assert state.grid_bot is None

        with (
            patch.object(orchestrator, "_create_grid_bot") as mock_create,
        ):
            mock_bot = MagicMock()
            mock_create.return_value = mock_bot

            orchestrator._execute_grid(state)

            mock_create.assert_called_once_with(state)
            mock_bot.tick.assert_called_once()

    def test_execute_grid_reuses_existing_bot(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        mock_bot = MagicMock()
        state.grid_bot = mock_bot

        orchestrator._execute_grid(state)
        mock_bot.tick.assert_called_once()

    def test_execute_grid_handles_none_bot(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        with patch.object(orchestrator, "_create_grid_bot", return_value=None):
            orchestrator._execute_grid(state)
            # Should not raise


# ------------------------------------------------------------------
# HOLD mode execution
# ------------------------------------------------------------------


class TestHoldMode:
    def test_execute_hold_buys_when_no_position(self, orchestrator, mock_client):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.0

        orchestrator._execute_hold(state)

        mock_client.place_market_buy.assert_called_once_with("BTCUSDT", 50.0)
        assert state.hold_quantity == 0.001
        assert state.hold_entry_price == 50000.0  # 50.0 / 0.001
        orchestrator.stop_loss_manager.create_stop.assert_called_once()

    def test_execute_hold_skips_if_already_holding(self, orchestrator, mock_client):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001

        orchestrator._execute_hold(state)
        mock_client.place_market_buy.assert_not_called()

    def test_execute_hold_handles_buy_failure(self, orchestrator, mock_client):
        mock_client.place_market_buy.return_value = {
            "success": False,
            "error": "insufficient funds",
        }
        state = orchestrator.symbols["BTCUSDT"]

        orchestrator._execute_hold(state)
        assert state.hold_quantity == 0.0

    def test_execute_hold_handles_zero_price(self, orchestrator, mock_client):
        mock_client.get_current_price.return_value = 0.0
        state = orchestrator.symbols["BTCUSDT"]

        orchestrator._execute_hold(state)
        mock_client.place_market_buy.assert_not_called()


# ------------------------------------------------------------------
# CASH mode execution
# ------------------------------------------------------------------


class TestCashMode:
    def test_execute_cash_cancels_grid(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        mock_bot = MagicMock()
        mock_bot.active_orders = {100: {"type": "BUY"}, 101: {"type": "SELL"}}
        state.grid_bot = mock_bot

        orchestrator._execute_cash(state)

        assert state.grid_bot is None

    def test_execute_cash_tightens_stop_first(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001
        state.hold_entry_price = 50000.0

        with patch.object(orchestrator, "_tighten_trailing_stop") as mock_tighten:
            orchestrator._execute_cash(state)
            mock_tighten.assert_called_once_with(state)
            assert state.cash_exit_started is not None

    def test_execute_cash_market_sells_on_timeout(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001
        state.hold_entry_price = 50000.0
        state.cash_exit_started = datetime.now() - timedelta(hours=3)

        with patch.object(orchestrator, "_market_sell_position") as mock_sell:
            orchestrator._execute_cash(state)
            mock_sell.assert_called_once_with(state)

    def test_execute_cash_waits_before_timeout(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001
        state.hold_entry_price = 50000.0
        state.cash_exit_started = datetime.now() - timedelta(minutes=30)

        with patch.object(orchestrator, "_market_sell_position") as mock_sell:
            orchestrator._execute_cash(state)
            mock_sell.assert_not_called()


# ------------------------------------------------------------------
# Market sell
# ------------------------------------------------------------------


class TestMarketSell:
    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    def test_market_sell_position(self, mock_executor, orchestrator, mock_client):
        mock_executor.return_value = {"success": True, "order": {}}
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001
        state.hold_entry_price = 50000.0
        state.hold_stop_id = "stop-123"

        orchestrator._market_sell_position(state)

        mock_executor.assert_called_once()
        assert state.hold_quantity == 0.0
        assert state.hold_stop_id is None
        assert state.cash_exit_started is None

    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    def test_market_sell_handles_failure(self, mock_executor, orchestrator, mock_client):
        mock_executor.return_value = {
            "success": False,
            "order": None,
            "error": "insufficient qty",
        }
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001

        orchestrator._market_sell_position(state)
        # On failure, state should NOT be reset (will retry next tick)
        assert state.hold_quantity == 0.001


# ------------------------------------------------------------------
# Transitions
# ------------------------------------------------------------------


class TestTransitions:
    def test_grid_to_hold_cancels_grid(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        mock_bot = MagicMock()
        mock_bot.active_orders = {}
        state.grid_bot = mock_bot

        with patch.object(orchestrator, "_cancel_grid_orders") as mock_cancel:
            orchestrator._transition_grid_to_hold(state)
            mock_cancel.assert_called_once_with(state)
            assert state.grid_bot is None

    def test_grid_to_cash(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        mock_bot = MagicMock()
        mock_bot.active_orders = {}
        state.grid_bot = mock_bot

        with patch.object(orchestrator, "_cancel_grid_orders"):
            orchestrator._transition_grid_to_cash(state)
            assert state.grid_bot is None
            assert state.cash_exit_started is None

    def test_hold_to_grid_cancels_stop(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_stop_id = "stop-123"
        state.hold_quantity = 0.001

        orchestrator._transition_hold_to_grid(state)

        orchestrator.stop_loss_manager.cancel_stop.assert_called_once_with("stop-123")
        assert state.hold_stop_id is None
        assert state.hold_quantity == 0.0

    def test_hold_to_cash_tightens_stop(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.hold_quantity = 0.001

        with patch.object(orchestrator, "_tighten_trailing_stop") as mock_tighten:
            orchestrator._transition_hold_to_cash(state)
            mock_tighten.assert_called_once_with(state)
            assert state.cash_exit_started is not None

    def test_cash_to_grid_resets(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.cash_exit_started = datetime.now()
        state.hold_quantity = 0.001

        orchestrator._transition_cash_to_grid(state)
        assert state.cash_exit_started is None
        assert state.hold_quantity == 0.0
        assert state.grid_bot is None

    def test_cash_to_hold_resets(self, orchestrator):
        state = orchestrator.symbols["BTCUSDT"]
        state.cash_exit_started = datetime.now()

        orchestrator._transition_cash_to_hold(state)
        assert state.cash_exit_started is None
        assert state.hold_quantity == 0.0

    def test_transition_mode_updates_all_symbols(self, orchestrator):
        for state in orchestrator.symbols.values():
            state.mode = TradingMode.GRID

        with patch.object(orchestrator, "_transition_symbol"):
            orchestrator._transition_mode(TradingMode.GRID, TradingMode.HOLD, "test")

        for state in orchestrator.symbols.values():
            assert state.mode == TradingMode.HOLD


# ------------------------------------------------------------------
# Mode evaluation and switching
# ------------------------------------------------------------------


class TestModeEvaluation:
    def test_evaluate_no_switch_same_mode(self, orchestrator):
        result = orchestrator.evaluate_and_switch("SIDEWAYS", 0.8, 3)
        assert result is False

    def test_evaluate_switches_on_bull(self, orchestrator):
        result = orchestrator.evaluate_and_switch("BULL", 0.8, 3)
        assert result is True
        current = orchestrator.mode_manager.get_current_mode().current_mode
        assert current == TradingMode.HOLD

    def test_evaluate_switches_on_bear(self, orchestrator):
        # Emergency bear with high probability
        result = orchestrator.evaluate_and_switch("BEAR", 0.9, 3)
        assert result is True
        current = orchestrator.mode_manager.get_current_mode().current_mode
        assert current == TradingMode.CASH


# ------------------------------------------------------------------
# Tick
# ------------------------------------------------------------------


class TestTick:
    def test_tick_returns_true(self, orchestrator):
        with (
            patch.object(orchestrator, "_execute_grid"),
            patch.object(orchestrator, "_update_stop_losses"),
            patch.object(orchestrator, "save_state"),
        ):
            result = orchestrator.tick()
            assert result is True

    def test_tick_calls_correct_mode_executor(self, orchestrator):
        with (
            patch.object(orchestrator, "_execute_grid") as mock_grid,
            patch.object(orchestrator, "_update_stop_losses"),
            patch.object(orchestrator, "save_state"),
        ):
            orchestrator.tick()
            assert mock_grid.call_count == 2  # BTCUSDT + ETHUSDT

    def test_tick_handles_per_symbol_errors(self, orchestrator):
        with (
            patch.object(orchestrator, "_execute_grid", side_effect=Exception("test error")),
            patch.object(orchestrator, "_update_stop_losses"),
            patch.object(orchestrator, "save_state"),
        ):
            result = orchestrator.tick()
            assert result is True  # Should continue despite per-symbol errors

    def test_tick_resets_error_counter(self, orchestrator):
        orchestrator.consecutive_errors = 3
        with (
            patch.object(orchestrator, "_execute_grid"),
            patch.object(orchestrator, "_update_stop_losses"),
            patch.object(orchestrator, "save_state"),
        ):
            orchestrator.tick()
            assert orchestrator.consecutive_errors == 0


# ------------------------------------------------------------------
# State persistence
# ------------------------------------------------------------------


class TestStatePersistence:
    def test_save_and_load_state(self, orchestrator, tmp_path):
        orchestrator.state_file = tmp_path / "hybrid_state.json"
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001
        orchestrator.symbols["BTCUSDT"].hold_entry_price = 50000.0

        orchestrator.save_state()
        assert orchestrator.state_file.exists()

        # Reset and reload
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.0
        orchestrator.load_state()
        assert orchestrator.symbols["BTCUSDT"].hold_quantity == 0.001

    def test_load_state_missing_file(self, orchestrator, tmp_path):
        orchestrator.state_file = tmp_path / "nonexistent.json"
        result = orchestrator.load_state()
        assert result is False

    def test_load_state_ignores_unknown_symbols(self, orchestrator, tmp_path):
        orchestrator.state_file = tmp_path / "hybrid_state.json"
        orchestrator.save_state()

        # Remove a symbol and reload
        orchestrator.remove_symbol("ETHUSDT")
        orchestrator.load_state()
        assert "ETHUSDT" not in orchestrator.symbols


# ------------------------------------------------------------------
# Stop loss updates
# ------------------------------------------------------------------


class TestStopLossUpdates:
    def test_update_stop_losses(self, orchestrator, mock_client):
        orchestrator.stop_loss_manager.update_all.return_value = []

        orchestrator._update_stop_losses()

        orchestrator.stop_loss_manager.update_all.assert_called_once()
        call_args = orchestrator.stop_loss_manager.update_all.call_args
        prices = call_args[0][0] if call_args[0] else call_args[1].get("prices", {})
        assert "BTCUSDT" in prices
        assert "ETHUSDT" in prices

    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    def test_update_stop_losses_handles_trigger(self, mock_executor, orchestrator, mock_client):
        mock_executor.return_value = {"success": True, "order": {}}
        mock_stop = MagicMock()
        mock_stop.symbol = "BTCUSDT"
        mock_stop.triggered_price = 45000.0
        mock_stop.quantity = 0.001
        orchestrator.stop_loss_manager.update_all.return_value = [mock_stop]

        orchestrator._update_stop_losses()

        mock_executor.assert_called_once()
        mock_stop.confirm_trigger.assert_called_once()
        assert orchestrator.symbols["BTCUSDT"].hold_quantity == 0.0

    def test_update_stop_losses_skips_zero_price(self, orchestrator, mock_client):
        mock_client.get_current_price.return_value = 0.0
        orchestrator.stop_loss_manager.update_all.return_value = []

        orchestrator._update_stop_losses()
        orchestrator.stop_loss_manager.update_all.assert_not_called()


# ------------------------------------------------------------------
# Get status
# ------------------------------------------------------------------


class TestGetStatus:
    def test_get_status(self, orchestrator):
        status = orchestrator.get_status()
        assert status["mode"] == "GRID"
        assert "BTCUSDT" in status["symbols"]
        assert "ETHUSDT" in status["symbols"]
        assert status["running"] is False


# ------------------------------------------------------------------
# Helper: avg fill price
# ------------------------------------------------------------------


class TestAvgFillPrice:
    def test_avg_fill_price_from_cumulative(self, orchestrator):
        order = {"cummulativeQuoteQty": "100.0", "executedQty": "0.002"}
        assert orchestrator._get_avg_fill_price(order) == 50000.0

    def test_avg_fill_price_fallback_to_price(self, orchestrator):
        order = {"price": "49000.0", "executedQty": "0"}
        assert orchestrator._get_avg_fill_price(order) == 49000.0


# ------------------------------------------------------------------
# Phase 5: Multi-coin scan & allocate
# ------------------------------------------------------------------


def _make_opportunity(symbol, score=0.6, confidence=0.5, category="LARGE_CAP"):
    """Helper to create mock Opportunity objects."""
    mock = MagicMock()
    mock.symbol = symbol
    mock.total_score = score
    mock.confidence = confidence
    mock.category = category
    mock.risk_level = MagicMock()
    mock.risk_level.value = "MEDIUM"
    return mock


def _make_allocation_result(allocations, total=0, cash=0):
    """Helper to create mock AllocationResult."""
    mock = MagicMock()
    mock.allocations = allocations
    mock.total_allocated = total or sum(allocations.values())
    mock.cash_remaining = cash
    mock.rejected = {}
    return mock


class TestScanAndAllocate:
    def test_scan_and_allocate_adds_symbols(self, orchestrator):
        # Remove existing symbols first
        orchestrator.symbols.clear()

        opps = [
            _make_opportunity("SOLUSDT", score=0.8),
            _make_opportunity("DOTUSDT", score=0.6),
        ]
        alloc_result = _make_allocation_result(
            {"SOLUSDT": 60.0, "DOTUSDT": 40.0}, total=100.0, cash=300.0
        )

        with (
            patch("src.scanner.coin_scanner.CoinScanner") as mock_scanner_cls,
            patch("src.portfolio.allocator.PortfolioAllocator") as mock_alloc_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan_opportunities.return_value = opps
            mock_scanner_cls.get_instance.return_value = mock_scanner

            mock_allocator = MagicMock()
            mock_allocator.calculate_allocation.return_value = alloc_result
            mock_alloc_cls.get_instance.return_value = mock_allocator

            result = orchestrator.scan_and_allocate(regime="SIDEWAYS")

        assert result is not None
        assert "SOLUSDT" in orchestrator.symbols
        assert "DOTUSDT" in orchestrator.symbols
        assert orchestrator.symbols["SOLUSDT"].allocation_usd == 60.0

    def test_scan_and_allocate_removes_stale_symbols(self, orchestrator):
        # orchestrator has BTCUSDT and ETHUSDT
        alloc_result = _make_allocation_result({"BTCUSDT": 100.0}, total=100.0, cash=300.0)

        with (
            patch("src.scanner.coin_scanner.CoinScanner") as mock_scanner_cls,
            patch("src.portfolio.allocator.PortfolioAllocator") as mock_alloc_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan_opportunities.return_value = [_make_opportunity("BTCUSDT")]
            mock_scanner_cls.get_instance.return_value = mock_scanner

            mock_allocator = MagicMock()
            mock_allocator.calculate_allocation.return_value = alloc_result
            mock_alloc_cls.get_instance.return_value = mock_allocator

            orchestrator.scan_and_allocate()

        assert "BTCUSDT" in orchestrator.symbols
        assert "ETHUSDT" not in orchestrator.symbols

    def test_scan_and_allocate_keeps_symbols_with_positions(self, orchestrator):
        orchestrator.symbols["ETHUSDT"].hold_quantity = 0.5  # Has position

        alloc_result = _make_allocation_result({"BTCUSDT": 100.0}, total=100.0, cash=300.0)

        with (
            patch("src.scanner.coin_scanner.CoinScanner") as mock_scanner_cls,
            patch("src.portfolio.allocator.PortfolioAllocator") as mock_alloc_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan_opportunities.return_value = [_make_opportunity("BTCUSDT")]
            mock_scanner_cls.get_instance.return_value = mock_scanner

            mock_allocator = MagicMock()
            mock_allocator.calculate_allocation.return_value = alloc_result
            mock_alloc_cls.get_instance.return_value = mock_allocator

            orchestrator.scan_and_allocate()

        # ETHUSDT kept because it has a hold position, but allocation zeroed
        assert "ETHUSDT" in orchestrator.symbols
        assert orchestrator.symbols["ETHUSDT"].allocation_usd == 0.0

    def test_scan_and_allocate_no_opportunities(self, orchestrator):
        with (
            patch("src.scanner.coin_scanner.CoinScanner") as mock_scanner_cls,
            patch("src.portfolio.allocator.PortfolioAllocator"),
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan_opportunities.return_value = []
            mock_scanner_cls.get_instance.return_value = mock_scanner

            result = orchestrator.scan_and_allocate()
            assert result is None

    def test_scan_and_allocate_limits_to_max_symbols(self, orchestrator, config):
        config.max_symbols = 2
        opps = [_make_opportunity(f"SYM{i}USDT") for i in range(5)]

        alloc_result = _make_allocation_result({"SYM0USDT": 50.0, "SYM1USDT": 50.0}, total=100.0)

        with (
            patch("src.scanner.coin_scanner.CoinScanner") as mock_scanner_cls,
            patch("src.portfolio.allocator.PortfolioAllocator") as mock_alloc_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan_opportunities.return_value = opps
            mock_scanner_cls.get_instance.return_value = mock_scanner

            mock_allocator = MagicMock()
            mock_allocator.calculate_allocation.return_value = alloc_result
            mock_alloc_cls.get_instance.return_value = mock_allocator

            orchestrator.scan_and_allocate()

            # Allocator should have received at most 2 opportunities
            call_args = mock_allocator.calculate_allocation.call_args
            passed_opps = call_args[1].get("opportunities") or call_args[0][0]
            assert len(passed_opps) <= 2

    def test_scan_and_allocate_handles_import_error(self, orchestrator):
        with patch.dict("sys.modules", {"src.scanner.coin_scanner": None}):
            # Should not raise, returns None gracefully
            result = orchestrator.scan_and_allocate()
            assert result is None


# ------------------------------------------------------------------
# Phase 5: Rebalance
# ------------------------------------------------------------------


class TestRebalance:
    def test_rebalance_skips_if_too_soon(self, orchestrator):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=1)
        result = orchestrator.rebalance()
        assert result == {}

    def test_rebalance_runs_after_interval(self, orchestrator, mock_client):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=7)
        orchestrator.symbols["BTCUSDT"].allocation_usd = 50.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001
        # Current value = 0.001 * 50000 = 50.0 (matches target, no drift)

        result = orchestrator.rebalance()
        assert isinstance(result, dict)

    def test_rebalance_detects_drift(self, orchestrator, mock_client):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=7)

        # Target: 50 USD, but price dropped -> current value ~25 USD (>5% drift)
        orchestrator.symbols["BTCUSDT"].allocation_usd = 50.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001
        mock_client.get_current_price.return_value = 25000.0  # 0.001 * 25000 = 25

        result = orchestrator.rebalance()
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["action"] == "INCREASE"

    def test_rebalance_detects_decrease_needed(self, orchestrator, mock_client):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=7)

        # Target: 50 USD, but price doubled -> current value ~100 USD
        orchestrator.symbols["BTCUSDT"].allocation_usd = 50.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001
        mock_client.get_current_price.return_value = 100000.0  # 0.001 * 100000 = 100

        result = orchestrator.rebalance()
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["action"] == "DECREASE"

    def test_rebalance_no_drift(self, orchestrator, mock_client):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=7)

        orchestrator.symbols["BTCUSDT"].allocation_usd = 50.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001
        mock_client.get_current_price.return_value = 50000.0  # 0.001 * 50000 = 50

        result = orchestrator.rebalance()
        assert "BTCUSDT" not in result  # No drift

    def test_rebalance_empty_symbols(self, orchestrator):
        orchestrator.symbols.clear()
        result = orchestrator.rebalance()
        assert result == {}

    def test_rebalance_updates_timestamp(self, orchestrator, mock_client):
        orchestrator._last_rebalance = None
        orchestrator.symbols["BTCUSDT"].allocation_usd = 50.0
        orchestrator.symbols["BTCUSDT"].hold_quantity = 0.001

        orchestrator.rebalance()
        assert orchestrator._last_rebalance is not None

    def test_rebalance_skips_zero_allocation(self, orchestrator, mock_client):
        orchestrator._last_rebalance = datetime.now() - timedelta(hours=7)
        orchestrator.symbols["BTCUSDT"].allocation_usd = 0.0

        result = orchestrator.rebalance()
        assert "BTCUSDT" not in result


# ------------------------------------------------------------------
# Phase 5: Per-symbol shared client (already tested via GridBot)
# ------------------------------------------------------------------


class TestSharedClient:
    def test_grid_bot_uses_shared_client(self, orchestrator, mock_client):
        state = orchestrator.symbols["BTCUSDT"]
        state.allocation_usd = 50.0

        with patch("src.core.hybrid_orchestrator.GridBot") as mock_bot_cls:
            mock_bot = MagicMock()
            mock_bot.initialize.return_value = True
            mock_bot_cls.return_value = mock_bot

            bot = orchestrator._create_grid_bot(state)

            # Verify shared client was passed
            mock_bot_cls.assert_called_once()
            call_args = mock_bot_cls.call_args
            # GridBot(bot_config, client=self.client)
            passed_client = call_args[1].get("client") if call_args[1] else call_args[0][1]
            assert passed_client is mock_client
