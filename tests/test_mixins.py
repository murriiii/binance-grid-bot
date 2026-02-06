"""Unit tests for GridBot mixins: RiskGuardMixin, OrderManagerMixin, StateManagerMixin."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.bot import GridBot
from src.strategies.grid_strategy import GridStrategy


@pytest.fixture
def bot_with_strategy(bot_config, mock_binance):
    """GridBot with initialized strategy and stop-loss manager."""
    with (
        patch("src.core.bot.TelegramNotifier") as mock_tg_cls,
        patch.object(GridBot, "_init_memory"),
        patch.object(GridBot, "_init_stop_loss"),
        patch.object(GridBot, "_init_risk_modules"),
    ):
        b = GridBot(bot_config)
        b.client = mock_binance
        b.telegram = mock_tg_cls.return_value
        b.memory = None
        b.cvar_sizer = None
        b.allocation_constraints = None

        # Create a real strategy
        b.symbol_info = {
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.0,
        }
        b.strategy = GridStrategy(
            lower_price=47500.0,
            upper_price=52500.0,
            num_grids=3,
            total_investment=100,
            symbol_info=b.symbol_info,
        )

        # Stop-loss manager
        from src.risk.stop_loss import StopLossManager

        b.stop_loss_manager = StopLossManager()
        return b


# ═══════════════════════════════════════════════════════════════
# RiskGuardMixin Tests
# ═══════════════════════════════════════════════════════════════


class TestRiskGuardMixin:
    """Tests for _validate_order_risk, _check_circuit_breaker, _check_stop_losses."""

    def test_validate_order_risk_allowed_no_modules(self, bot):
        """Without risk modules, all orders pass."""
        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True
        assert reason == ""

    def test_validate_order_risk_blocked_by_portfolio_stop(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.stop_loss_manager.portfolio_stopped = True

        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is False
        assert "drawdown" in reason.lower()

    def test_validate_order_risk_cvar_blocks(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.cvar_sizer = MagicMock()
        sizing = MagicMock()
        sizing.max_position = 10.0  # Only $10 allowed
        bot.cvar_sizer.calculate_position_size.return_value = sizing
        bot.client.get_account_balance.return_value = 1000.0

        # Try to place a $500 order
        allowed, reason = bot._validate_order_risk("BUY", 0.01, 50000.0)
        assert allowed is False
        assert "CVaR" in reason

    def test_validate_order_risk_cvar_allows(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.cvar_sizer = MagicMock()
        sizing = MagicMock()
        sizing.max_position = 100000.0
        bot.cvar_sizer.calculate_position_size.return_value = sizing
        bot.client.get_account_balance.return_value = 1000.0

        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_validate_order_risk_sell_skips_cvar(self, bot_with_strategy):
        """CVaR check only applies to BUY orders."""
        bot = bot_with_strategy
        bot.cvar_sizer = MagicMock()
        sizing = MagicMock()
        sizing.max_position = 1.0  # Would block BUY
        bot.cvar_sizer.calculate_position_size.return_value = sizing

        allowed, _ = bot._validate_order_risk("SELL", 0.01, 50000.0)
        assert allowed is True

    def test_circuit_breaker_first_call_stores_price(self, bot_with_strategy):
        bot = bot_with_strategy
        assert bot._last_known_price == 0.0
        triggered = bot._check_circuit_breaker(50000.0)
        assert triggered is False
        assert bot._last_known_price == 50000.0

    def test_circuit_breaker_normal_movement(self, bot_with_strategy):
        bot = bot_with_strategy
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(49000.0)  # -2%
        assert triggered is False
        assert bot._last_known_price == 49000.0

    def test_circuit_breaker_triggered(self, bot_with_strategy):
        bot = bot_with_strategy
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(44000.0)  # -12%
        assert triggered is True
        assert bot.running is False  # _emergency_stop called

    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    def test_check_stop_losses_confirm_on_success(self, mock_sell, bot_with_strategy):
        bot = bot_with_strategy
        mock_sell.return_value = {"success": True, "order": {"orderId": 1}}

        # Create a stop that will trigger at 45000
        from src.risk.stop_loss import StopType

        bot.stop_loss_manager.create_stop(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.001,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )

        bot._check_stop_losses(47000.0)  # Below stop price

        mock_sell.assert_called_once()

    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    def test_check_stop_losses_reactivate_on_failure(self, mock_sell, bot_with_strategy):
        bot = bot_with_strategy
        mock_sell.return_value = {"success": False, "error": "API error"}

        from src.risk.stop_loss import StopType

        bot.stop_loss_manager.create_stop(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.001,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )

        bot._check_stop_losses(47000.0)

        # Stop should still be active after reactivation
        active_stops = [s for s in bot.stop_loss_manager.stops.values() if s.is_active]
        assert len(active_stops) == 1


# ═══════════════════════════════════════════════════════════════
# OrderManagerMixin Tests
# ═══════════════════════════════════════════════════════════════


class TestOrderManagerMixin:
    def test_place_initial_orders(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.place_initial_orders()

        assert len(bot.active_orders) > 0
        bot.client.place_limit_buy.assert_called()

    def test_place_initial_orders_skips_small_notional(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.symbol_info["min_notional"] = 999999.0  # Unrealistically high
        bot.place_initial_orders()

        # No orders placed because notional too small
        assert len(bot.active_orders) == 0

    def test_check_orders_filled_buy_places_sell(self, bot_with_strategy):
        bot = bot_with_strategy

        # Use an actual grid level price (first level of the grid)
        grid_price = float(bot.strategy.levels[0].price)
        grid_qty = float(bot.strategy.levels[0].quantity)

        bot.active_orders[100] = {
            "type": "BUY",
            "price": grid_price,
            "quantity": grid_qty,
            "created_at": "2024-01-01T00:00:00",
        }

        bot.client.get_open_orders.return_value = []
        bot.client.get_order_status.return_value = {
            "status": "FILLED",
            "price": str(grid_price),
            "executedQty": str(grid_qty),
        }

        bot.check_orders()

        # Old order should be replaced by new sell at next grid level
        assert 100 not in bot.active_orders
        bot.client.place_limit_sell.assert_called()

    def test_check_orders_canceled_removed(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.active_orders[100] = {
            "type": "BUY",
            "price": 48750.0,
            "quantity": 0.00068,
            "created_at": "2024-01-01T00:00:00",
        }

        bot.client.get_open_orders.return_value = []
        bot.client.get_order_status.return_value = {
            "status": "CANCELED",
            "executedQty": "0",
        }

        bot.check_orders()
        assert 100 not in bot.active_orders

    def test_process_partial_fill(self, bot_with_strategy):
        bot = bot_with_strategy
        bot.active_orders[100] = {
            "type": "BUY",
            "price": 48750.0,
            "quantity": 0.001,
            "created_at": "2024-01-01T00:00:00",
        }

        order_status = {
            "price": "48750.0",
            "executedQty": "0.0005",
        }

        bot._process_partial_fill(100, bot.active_orders[100], order_status)
        assert 100 not in bot.active_orders

    def test_process_pending_followups(self, bot_with_strategy):
        bot = bot_with_strategy

        # Use an actual grid level price so strategy returns a follow-up
        grid_price = float(bot.strategy.levels[0].price)
        bot._pending_followups = [
            {"type": "BUY", "price": grid_price, "quantity": 0.001},
        ]

        bot._process_pending_followups()

        assert len(bot._pending_followups) == 0
        # Should have placed a follow-up sell at the next grid level
        bot.client.place_limit_sell.assert_called()


# ═══════════════════════════════════════════════════════════════
# StateManagerMixin Tests
# ═══════════════════════════════════════════════════════════════


class TestStateManagerMixin:
    def test_save_state_roundtrip(self, bot_with_strategy, tmp_path):
        bot = bot_with_strategy
        bot.state_file = tmp_path / "test_state.json"

        bot.active_orders = {
            100: {
                "type": "BUY",
                "price": 48750.0,
                "quantity": 0.001,
                "created_at": "2024-01-01T00:00:00",
            }
        }

        bot.save_state()

        assert bot.state_file.exists()
        with open(bot.state_file) as f:
            state = json.load(f)
        assert "100" in state["active_orders"]
        assert state["symbol"] == "BTCUSDT"

    def test_save_state_atomic_write(self, bot_with_strategy, tmp_path):
        """Save uses temp file + rename for atomicity."""
        bot = bot_with_strategy
        bot.state_file = tmp_path / "test_state.json"
        bot.active_orders = {}

        bot.save_state()

        # Temp file should be cleaned up
        assert not (tmp_path / "test_state.tmp").exists()
        assert bot.state_file.exists()

    def test_load_state_validates_against_binance(self, bot_with_strategy, tmp_path):
        bot = bot_with_strategy
        bot.state_file = tmp_path / "test_state.json"

        # Write a state file
        state = {
            "timestamp": "2024-01-01T00:00:00",
            "symbol": "BTCUSDT",
            "active_orders": {
                "100": {
                    "type": "BUY",
                    "price": 48750.0,
                    "quantity": 0.001,
                    "created_at": "2024-01-01T00:00:00",
                }
            },
            "config": {
                "symbol": "BTCUSDT",
                "investment": 100,
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
            },
        }
        with open(bot.state_file, "w") as f:
            json.dump(state, f)

        # Binance says order is still NEW
        bot.client.get_order_status.return_value = {
            "status": "NEW",
            "executedQty": "0",
        }

        result = bot.load_state()
        assert result is True
        assert 100 in bot.active_orders

    def test_load_state_detects_downtime_fill(self, bot_with_strategy, tmp_path):
        bot = bot_with_strategy
        bot.state_file = tmp_path / "test_state.json"

        state = {
            "timestamp": "2024-01-01T00:00:00",
            "symbol": "BTCUSDT",
            "active_orders": {
                "100": {
                    "type": "BUY",
                    "price": 48750.0,
                    "quantity": 0.001,
                    "created_at": "2024-01-01T00:00:00",
                }
            },
            "config": {
                "symbol": "BTCUSDT",
                "investment": 100,
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
            },
        }
        with open(bot.state_file, "w") as f:
            json.dump(state, f)

        # Binance says order was FILLED during downtime
        bot.client.get_order_status.return_value = {
            "status": "FILLED",
            "price": "48750.0",
            "executedQty": "0.001",
        }

        result = bot.load_state()

        # Order was filled, not restored as active
        assert 100 not in bot.active_orders
        # Should have queued a follow-up
        assert len(bot._pending_followups) == 1
        assert bot._pending_followups[0]["type"] == "BUY"
        assert bot._pending_followups[0]["price"] == 48750.0

    def test_load_state_rejects_changed_symbol(self, bot_with_strategy, tmp_path):
        bot = bot_with_strategy
        bot.state_file = tmp_path / "test_state.json"

        state = {
            "timestamp": "2024-01-01T00:00:00",
            "symbol": "ETHUSDT",
            "active_orders": {},
            "config": {
                "symbol": "ETHUSDT",  # Different from bot's BTCUSDT
                "investment": 100,
            },
        }
        with open(bot.state_file, "w") as f:
            json.dump(state, f)

        result = bot.load_state()
        assert result is False

    def test_load_state_returns_false_no_file(self, bot_with_strategy, tmp_path):
        bot = bot_with_strategy
        bot.state_file = tmp_path / "nonexistent.json"

        result = bot.load_state()
        assert result is False
