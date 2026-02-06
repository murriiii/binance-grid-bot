"""Tests for pre-testphase fixes (Phases 1-6)."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# Phase 2.1: State file per symbol
# ═══════════════════════════════════════════════════════════════


class TestStateFilePerSymbol:
    """Two GridBots should write to different state files."""

    def test_default_state_file(self, bot):
        """GridBot without state_file config uses default."""
        assert bot.state_file.name == "bot_state.json"

    def test_custom_state_file_from_config(self, mock_binance):
        """GridBot with state_file config uses custom path."""
        from src.core.bot import GridBot

        config = {
            "symbol": "ETHUSDT",
            "investment": 100,
            "num_grids": 3,
            "grid_range_percent": 5,
            "testnet": True,
            "state_file": "grid_state_ETHUSDT.json",
        }

        with (
            patch("src.core.bot.TelegramNotifier"),
            patch.object(GridBot, "_init_memory"),
            patch.object(GridBot, "_init_stop_loss"),
            patch.object(GridBot, "_init_risk_modules"),
        ):
            b = GridBot(config)
            b.client = mock_binance

        assert b.state_file.name == "grid_state_ETHUSDT.json"

    def test_two_bots_different_state_files(self, mock_binance):
        """Two GridBots with different symbols write to different state files."""
        from src.core.bot import GridBot

        configs = [
            {
                "symbol": "BTCUSDT",
                "investment": 100,
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
                "state_file": "grid_state_BTCUSDT.json",
            },
            {
                "symbol": "ETHUSDT",
                "investment": 50,
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
                "state_file": "grid_state_ETHUSDT.json",
            },
        ]

        bots = []
        for cfg in configs:
            with (
                patch("src.core.bot.TelegramNotifier"),
                patch.object(GridBot, "_init_memory"),
                patch.object(GridBot, "_init_stop_loss"),
                patch.object(GridBot, "_init_risk_modules"),
            ):
                b = GridBot(cfg)
                b.client = mock_binance
                bots.append(b)

        assert bots[0].state_file.name != bots[1].state_file.name
        assert bots[0].state_file.name == "grid_state_BTCUSDT.json"
        assert bots[1].state_file.name == "grid_state_ETHUSDT.json"


# ═══════════════════════════════════════════════════════════════
# Phase 2.3: State corruption recovery
# ═══════════════════════════════════════════════════════════════


class TestStateCorruptionRecovery:
    """Corrupt JSON state file should not crash the bot."""

    def test_corrupt_json_returns_false(self, bot, tmp_path):
        """Corrupt state file should return False and reset active_orders."""
        corrupt_file = tmp_path / "corrupt_state.json"
        corrupt_file.write_text("this is not valid json{{{")
        bot.state_file = corrupt_file

        # Pre-populate active_orders to ensure they get cleared
        bot.active_orders = {999: {"type": "BUY", "price": 50000}}

        result = bot.load_state()

        assert result is False
        assert bot.active_orders == {}

    def test_empty_file_returns_false(self, bot, tmp_path):
        """Empty state file should return False."""
        empty_file = tmp_path / "empty_state.json"
        empty_file.write_text("")
        bot.state_file = empty_file

        result = bot.load_state()

        assert result is False
        assert bot.active_orders == {}


# ═══════════════════════════════════════════════════════════════
# Phase 2.2: Config mismatch cancels orders
# ═══════════════════════════════════════════════════════════════


class TestConfigMismatchCancelsOrders:
    """Symbol/investment change should cancel orphaned orders at Binance."""

    def test_symbol_change_cancels_old_orders(self, bot, mock_binance, tmp_path):
        """When symbol changes, old orders for old symbol should be cancelled."""
        state_file = tmp_path / "mismatch_state.json"
        state = {
            "timestamp": datetime.now().isoformat(),
            "symbol": "ETHUSDT",
            "active_orders": {"123": {"type": "BUY", "price": 3000, "quantity": 0.1}},
            "config": {
                "symbol": "ETHUSDT",
                "investment": 100,
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
            },
        }
        state_file.write_text(json.dumps(state))
        bot.state_file = state_file

        # Bot is configured for BTCUSDT but state has ETHUSDT
        mock_binance.get_open_orders.return_value = [
            {"orderId": 123},
            {"orderId": 456},
        ]

        result = bot.load_state()

        assert result is False
        mock_binance.get_open_orders.assert_called_once_with("ETHUSDT")
        assert mock_binance.cancel_order.call_count == 2

    def test_investment_change_cancels_orders(self, bot, mock_binance, tmp_path):
        """When investment changes, old orders should be cancelled."""
        state_file = tmp_path / "invest_mismatch.json"
        state = {
            "timestamp": datetime.now().isoformat(),
            "symbol": "BTCUSDT",
            "active_orders": {},
            "config": {
                "symbol": "BTCUSDT",
                "investment": 200,  # Different from bot's 100
                "num_grids": 3,
                "grid_range_percent": 5,
                "testnet": True,
            },
        }
        state_file.write_text(json.dumps(state))
        bot.state_file = state_file

        mock_binance.get_open_orders.return_value = []

        result = bot.load_state()

        assert result is False
        mock_binance.get_open_orders.assert_called_once_with("BTCUSDT")


# ═══════════════════════════════════════════════════════════════
# Phase 3.1: Trailing distance passthrough
# ═══════════════════════════════════════════════════════════════


class TestTrailingDistancePassthrough:
    """Trailing stop should use stop_percentage as trailing_distance."""

    def test_trailing_stop_uses_stop_percentage_by_default(self):
        """When no explicit trailing_distance, stop_percentage is used."""
        from src.risk.stop_loss import StopLossManager, StopType

        manager = StopLossManager(db_manager=None, telegram_bot=None)
        stop = manager.create_stop(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.1,
            stop_type=StopType.TRAILING,
            stop_percentage=7.0,
        )

        assert stop.trailing_distance == 7.0
        # Initial stop should be 7% below entry
        expected_stop = 50000.0 * (1 - 7.0 / 100)
        assert abs(stop.current_stop_price - expected_stop) < 0.01

    def test_trailing_stop_with_explicit_distance(self):
        """Explicit trailing_distance overrides stop_percentage for trailing."""
        from src.risk.stop_loss import StopLossManager, StopType

        manager = StopLossManager(db_manager=None, telegram_bot=None)
        stop = manager.create_stop(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.1,
            stop_type=StopType.TRAILING,
            stop_percentage=7.0,
            trailing_distance=3.0,
        )

        assert stop.trailing_distance == 3.0
        expected_stop = 50000.0 * (1 - 3.0 / 100)
        assert abs(stop.current_stop_price - expected_stop) < 0.01

    def test_hold_mode_7pct_trailing(self):
        """HOLD mode with 7% should produce 7% trailing distance, not 3% default."""
        from src.risk.stop_loss import StopLossManager, StopType

        manager = StopLossManager(db_manager=None, telegram_bot=None)
        stop = manager.create_stop(
            symbol="BTCUSDT",
            entry_price=100000.0,
            quantity=0.01,
            stop_type=StopType.TRAILING,
            stop_percentage=7.0,
        )

        # Simulate price rising to 110000
        stop.update(110000.0)
        # Trailing stop should be 7% below highest price
        expected = 110000.0 * (1 - 7.0 / 100)
        assert abs(stop.current_stop_price - expected) < 0.01

    def test_fixed_stop_unaffected(self):
        """FIXED stop should not be affected by trailing_distance change."""
        from src.risk.stop_loss import StopLossManager, StopType

        manager = StopLossManager(db_manager=None, telegram_bot=None)
        stop = manager.create_stop(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.1,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )

        expected_stop = 50000.0 * (1 - 5.0 / 100)
        assert abs(stop.current_stop_price - expected_stop) < 0.01


# ═══════════════════════════════════════════════════════════════
# Phase 4: Failed follow-up retry limit
# ═══════════════════════════════════════════════════════════════


class TestFailedFollowupRetryLimit:
    """Follow-up orders should be retried with backoff and eventually abandoned."""

    def test_followup_exceeds_max_retries_gets_removed(self, bot, mock_binance):
        """After MAX_FOLLOWUP_RETRIES, order should be removed."""
        from src.core.order_manager import MAX_FOLLOWUP_RETRIES

        bot.active_orders[999] = {
            "type": "BUY",
            "price": 50000,
            "quantity": 0.001,
            "failed_followup": True,
            "intended_action": {"action": "PLACE_SELL", "price": 51000, "quantity": 0.001},
            "retry_count": MAX_FOLLOWUP_RETRIES,
            "next_retry_after": (datetime.now() - timedelta(minutes=1)).isoformat(),
        }

        bot.strategy = MagicMock()
        bot.stop_loss_manager = None
        mock_binance.get_open_orders.return_value = []

        bot.check_orders()

        assert 999 not in bot.active_orders

    def test_followup_respects_backoff_timer(self, bot, mock_binance):
        """Failed follow-up should not retry before backoff expires."""
        bot.active_orders[999] = {
            "type": "BUY",
            "price": 50000,
            "quantity": 0.001,
            "failed_followup": True,
            "intended_action": {"action": "PLACE_SELL", "price": 51000, "quantity": 0.001},
            "retry_count": 1,
            "next_retry_after": (datetime.now() + timedelta(minutes=10)).isoformat(),
        }

        bot.strategy = MagicMock()
        bot.stop_loss_manager = None
        mock_binance.get_open_orders.return_value = []

        bot.check_orders()

        # Order should still be there (waiting for backoff)
        assert 999 in bot.active_orders
        assert bot.active_orders[999]["failed_followup"] is True

    def test_followup_retry_succeeds(self, bot, mock_binance):
        """Successful retry should place new order and remove failed one."""
        bot.active_orders[999] = {
            "type": "BUY",
            "price": 50000,
            "quantity": 0.001,
            "failed_followup": True,
            "intended_action": {"action": "PLACE_SELL", "price": 51000, "quantity": 0.001},
            "retry_count": 1,
            "next_retry_after": (datetime.now() - timedelta(minutes=1)).isoformat(),
        }

        bot.strategy = MagicMock()
        bot.stop_loss_manager = None
        mock_binance.get_open_orders.return_value = []
        mock_binance.place_limit_sell.return_value = {
            "success": True,
            "order": {"orderId": 1000},
        }

        bot.check_orders()

        assert 999 not in bot.active_orders
        assert 1000 in bot.active_orders
        assert bot.active_orders[1000]["type"] == "SELL"


# ═══════════════════════════════════════════════════════════════
# Phase 5: Mode manager lock expires
# ═══════════════════════════════════════════════════════════════


class TestModeManagerLockExpiry:
    """Safety lock should auto-expire after 7 days."""

    def _create_manager(self):
        from src.core.hybrid_config import HybridConfig
        from src.core.mode_manager import ModeManager

        ModeManager.reset_instance()
        config = HybridConfig()
        config.enable_mode_switching = True
        config.min_regime_probability = 0.75
        config.min_regime_duration_days = 2
        return ModeManager(config)

    def test_locked_mode_blocks_switching(self):
        """While locked, evaluate_mode should return locked mode."""
        from src.core.trading_mode import TradingMode

        manager = self._create_manager()
        manager._locked_mode = TradingMode.GRID
        manager._lock_activated_at = datetime.now()

        mode, reason = manager.evaluate_mode("BULL", 0.9, 5)

        assert mode == TradingMode.GRID
        assert "Safety lock" in reason

    def test_lock_expires_after_7_days(self):
        """After 7 days, lock should be released."""
        from src.core.trading_mode import TradingMode

        manager = self._create_manager()
        manager._locked_mode = TradingMode.GRID
        manager._lock_activated_at = datetime.now() - timedelta(days=8)

        mode, _reason = manager.evaluate_mode("BULL", 0.9, 5)

        # Lock should have been cleared — mode should follow regime
        assert manager._locked_mode is None
        assert mode == TradingMode.HOLD

    def test_lock_active_at_6_days(self):
        """At 6 days, lock should still be active."""
        from src.core.trading_mode import TradingMode

        manager = self._create_manager()
        manager._locked_mode = TradingMode.GRID
        manager._lock_activated_at = datetime.now() - timedelta(days=6)

        mode, _reason = manager.evaluate_mode("BULL", 0.9, 5)

        assert mode == TradingMode.GRID
        assert manager._locked_mode is not None


# ═══════════════════════════════════════════════════════════════
# Phase 6.3: Circuit breaker initialization
# ═══════════════════════════════════════════════════════════════


class TestCircuitBreakerInit:
    """Circuit breaker should be initialized with current price after initialize()."""

    def test_last_known_price_set_after_initialize(self, bot, mock_binance):
        """_last_known_price should be set to current price after successful init."""
        assert bot._last_known_price == 0.0

        mock_binance.get_current_price.return_value = 50000.0
        bot.initialize()

        assert bot._last_known_price == 50000.0
