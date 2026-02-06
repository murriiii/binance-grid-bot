"""Tests for A1: Risk Enforcement in Order-Pipeline"""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# _validate_order_risk
# ═══════════════════════════════════════════════════════════════


class TestValidateOrderRisk:
    def test_allows_order_when_no_risk_modules(self, bot):
        """Without risk modules, all orders should be allowed (graceful degradation)"""
        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True
        assert reason == ""

    def test_blocks_when_portfolio_stopped(self, bot):
        """Portfolio drawdown reached -> block all orders"""
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is False
        assert "drawdown" in reason.lower()

    def test_blocks_when_portfolio_stopped_sell(self, bot):
        """Portfolio stopped should block SELL orders too"""
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        allowed, _reason = bot._validate_order_risk("SELL", 0.001, 50000.0)
        assert allowed is False

    def test_allows_when_portfolio_not_stopped(self, bot):
        """Portfolio not stopped -> allow orders"""
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = False

        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_blocks_when_cvar_max_exceeded(self, bot):
        """Order value > CVaR max position -> block"""
        mock_sizer = MagicMock()
        sizing_result = MagicMock()
        sizing_result.max_position = 25.0  # Max $25
        mock_sizer.calculate_position_size.return_value = sizing_result
        bot.cvar_sizer = mock_sizer

        # Order for $50 (0.001 BTC * $50000)
        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is False
        assert "CVaR" in reason

    def test_allows_when_cvar_within_limit(self, bot):
        """Order value <= CVaR max position -> allow"""
        mock_sizer = MagicMock()
        sizing_result = MagicMock()
        sizing_result.max_position = 100.0  # Max $100
        mock_sizer.calculate_position_size.return_value = sizing_result
        bot.cvar_sizer = mock_sizer

        # Order for $50 (0.001 BTC * $50000)
        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_cvar_only_checked_for_buys(self, bot):
        """CVaR check should not apply to SELL orders"""
        mock_sizer = MagicMock()
        sizing_result = MagicMock()
        sizing_result.max_position = 1.0  # Very low limit
        mock_sizer.calculate_position_size.return_value = sizing_result
        bot.cvar_sizer = mock_sizer

        # SELL should pass even with tiny CVaR limit
        allowed, _reason = bot._validate_order_risk("SELL", 0.001, 50000.0)
        assert allowed is True

    def test_cvar_failure_allows_order(self, bot):
        """If CVaR calculation fails, order should be allowed (graceful degradation)"""
        mock_sizer = MagicMock()
        mock_sizer.calculate_position_size.side_effect = RuntimeError("DB unavailable")
        bot.cvar_sizer = mock_sizer

        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_blocks_when_allocation_exceeded(self, bot):
        """Order exceeds available capital -> block"""
        mock_constraints = MagicMock()
        mock_constraints.get_available_capital.return_value = 10.0  # Only $10 available
        bot.allocation_constraints = mock_constraints

        # Order for $50 (0.001 BTC * $50000)
        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is False
        assert "available capital" in reason.lower()

    def test_allows_when_allocation_within_limit(self, bot):
        """Order within available capital -> allow"""
        mock_constraints = MagicMock()
        mock_constraints.get_available_capital.return_value = 200.0
        bot.allocation_constraints = mock_constraints

        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_allocation_only_checked_for_buys(self, bot):
        """Allocation check should not apply to SELL orders"""
        mock_constraints = MagicMock()
        mock_constraints.get_available_capital.return_value = 0.0  # No capital
        bot.allocation_constraints = mock_constraints

        allowed, _reason = bot._validate_order_risk("SELL", 0.001, 50000.0)
        assert allowed is True

    def test_allocation_failure_allows_order(self, bot):
        """If allocation check fails, order should be allowed (graceful degradation)"""
        mock_constraints = MagicMock()
        mock_constraints.get_available_capital.side_effect = RuntimeError("error")
        bot.allocation_constraints = mock_constraints

        allowed, _reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is True

    def test_combined_checks_first_failure_wins(self, bot):
        """Portfolio stopped check runs before CVaR and allocation"""
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        # Even with permissive CVaR/allocation, portfolio stop takes precedence
        mock_sizer = MagicMock()
        sizing_result = MagicMock()
        sizing_result.max_position = 999999.0
        mock_sizer.calculate_position_size.return_value = sizing_result
        bot.cvar_sizer = mock_sizer

        allowed, reason = bot._validate_order_risk("BUY", 0.001, 50000.0)
        assert allowed is False
        assert "drawdown" in reason.lower()


# ═══════════════════════════════════════════════════════════════
# _check_circuit_breaker
# ═══════════════════════════════════════════════════════════════


class TestCircuitBreaker:
    def test_first_call_initializes(self, bot):
        """First call should set the price and not trigger"""
        assert bot._last_known_price == 0.0
        triggered = bot._check_circuit_breaker(50000.0)
        assert triggered is False
        assert bot._last_known_price == 50000.0

    def test_normal_movement_no_trigger(self, bot):
        """Normal price movement should not trigger circuit breaker"""
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(48000.0)  # -4%
        assert triggered is False
        assert bot._last_known_price == 48000.0

    def test_flash_crash_triggers(self, bot):
        """Drop > 10% should trigger circuit breaker and stop bot"""
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(44000.0)  # -12%
        assert triggered is True
        assert bot.running is False

    def test_exactly_10_pct_triggers(self, bot):
        """Exactly 10% drop should trigger"""
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(45000.0)  # -10%
        assert triggered is True

    def test_price_increase_no_trigger(self, bot):
        """Price increase should never trigger"""
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(55000.0)  # +10%
        assert triggered is False
        assert bot._last_known_price == 55000.0

    def test_zero_price_no_trigger(self, bot):
        """Zero current price should not trigger (bad data protection)"""
        bot._last_known_price = 50000.0
        triggered = bot._check_circuit_breaker(0)
        assert triggered is False

    def test_price_tracks_over_multiple_calls(self, bot):
        """Price should update on each non-triggering call"""
        bot._check_circuit_breaker(50000.0)  # Initialize
        bot._check_circuit_breaker(48000.0)  # -4%
        assert bot._last_known_price == 48000.0

        # Now -12% from 48000 would be 42240
        triggered = bot._check_circuit_breaker(42000.0)  # -12.5% from 48000
        assert triggered is True


# ═══════════════════════════════════════════════════════════════
# Integration: Risk checks in place_initial_orders
# ═══════════════════════════════════════════════════════════════


class TestPlaceInitialOrdersRisk:
    def test_risk_blocked_orders_not_placed(self, bot, mock_binance):
        """Orders blocked by risk check should not be sent to Binance"""

        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=3,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )
        mock_binance.get_current_price.return_value = 50000.0

        # Block all BUY orders via portfolio stop
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        bot.place_initial_orders()

        # No orders should have been placed
        mock_binance.place_limit_buy.assert_not_called()

    def test_risk_allowed_orders_placed(self, bot, mock_binance):
        """Orders passing risk check should be sent to Binance"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=3,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )
        mock_binance.get_current_price.return_value = 50000.0

        # No risk modules -> all allowed
        bot.place_initial_orders()

        # At least one buy order should have been placed
        assert mock_binance.place_limit_buy.call_count > 0


# ═══════════════════════════════════════════════════════════════
# Integration: Risk checks in check_orders follow-ups
# ═══════════════════════════════════════════════════════════════


class TestCheckOrdersRisk:
    def _setup_filled_order(self, bot, mock_binance, order_type="BUY"):
        """Helper: set up a filled order scenario with a price matching a grid level.

        Uses grid 47500-52500 with 4 grids -> levels at 47500, 48750, 50000, 51250, 52500.
        For BUY: fills at level[1]=48750, follow-up SELL at level[2]=50000.
        For SELL: fills at level[2]=50000, follow-up BUY at level[1]=48750.
        """

        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        # Use actual grid level prices so on_buy_filled/on_sell_filled can match
        if order_type == "BUY":
            fill_price = bot.strategy.levels[1].price  # 48750
        else:
            fill_price = bot.strategy.levels[2].price  # 50000

        fill_qty = bot.strategy.levels[1].quantity

        bot.active_orders = {
            1001: {
                "type": order_type,
                "price": fill_price,
                "quantity": fill_qty,
                "created_at": "2025-01-01T00:00:00",
            }
        }

        # Binance says: order no longer open
        mock_binance.get_open_orders.return_value = []
        # Binance says: order was FILLED
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": str(fill_price),
            "executedQty": str(fill_qty),
        }

    def test_followup_sell_blocked_by_risk(self, bot, mock_binance):
        """Follow-up SELL after BUY fill should be blocked when portfolio stopped"""
        self._setup_filled_order(bot, mock_binance, "BUY")

        # Block via portfolio stop
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        bot.check_orders()

        # SELL should NOT have been placed
        mock_binance.place_limit_sell.assert_not_called()

    def test_followup_buy_blocked_by_risk(self, bot, mock_binance):
        """Follow-up BUY after SELL fill should be blocked when portfolio stopped"""
        self._setup_filled_order(bot, mock_binance, "SELL")

        # Block via portfolio stop
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        bot.check_orders()

        # BUY should NOT have been placed
        mock_binance.place_limit_buy.assert_not_called()

    def test_followup_sell_allowed_without_risk_modules(self, bot, mock_binance):
        """Follow-up SELL should work when no risk modules are loaded"""
        self._setup_filled_order(bot, mock_binance, "BUY")

        bot.check_orders()

        # SELL should have been placed
        mock_binance.place_limit_sell.assert_called_once()

    def test_followup_buy_allowed_without_risk_modules(self, bot, mock_binance):
        """Follow-up BUY should work when no risk modules are loaded"""
        self._setup_filled_order(bot, mock_binance, "SELL")

        bot.check_orders()

        # BUY should have been placed
        mock_binance.place_limit_buy.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# A2: Partial-Fill-Handling
# ═══════════════════════════════════════════════════════════════


class TestPartialFillHandling:
    """Tests for PARTIALLY_FILLED and CANCELED-with-partial-fill handling"""

    def _setup_order(self, bot, mock_binance, order_type="BUY"):
        """Helper: create an active order in the bot"""
        from decimal import Decimal

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.active_orders = {
            2001: {
                "type": order_type,
                "price": Decimal("50000"),
                "quantity": Decimal("0.001"),
                "created_at": "2025-01-01T00:00:00",
            }
        }
        # Order not in open orders anymore
        mock_binance.get_open_orders.return_value = []

    def test_partially_filled_kept_in_active(self, bot, mock_binance):
        """PARTIALLY_FILLED orders should stay in active_orders"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "PARTIALLY_FILLED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.check_orders()

        # Order should still be tracked
        assert 2001 in bot.active_orders
        assert bot.active_orders[2001]["executed_qty"] == 0.0005

    def test_partially_filled_not_deleted(self, bot, mock_binance):
        """PARTIALLY_FILLED should not trigger follow-up orders or deletion"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "PARTIALLY_FILLED",
            "price": "50000.00",
            "executedQty": "0.0003",
        }

        bot.check_orders()

        # No follow-up orders placed
        mock_binance.place_limit_buy.assert_not_called()
        mock_binance.place_limit_sell.assert_not_called()

    def test_canceled_with_partial_fill_processed(self, bot, mock_binance):
        """CANCELED with executedQty > 0 should process the partial fill"""
        self._setup_order(bot, mock_binance, "BUY")
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.check_orders()

        # Order should be removed after processing
        assert 2001 not in bot.active_orders

    def test_canceled_with_partial_fill_creates_stop_loss(self, bot, mock_binance):
        """CANCELED BUY with partial fill should create stop-loss for filled portion"""
        self._setup_order(bot, mock_binance, "BUY")
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.stop_loss_manager = MagicMock()
        bot.check_orders()

        # Stop loss should be created for the partial quantity
        bot.stop_loss_manager.create_stop.assert_called_once()
        call_kwargs = bot.stop_loss_manager.create_stop.call_args
        assert call_kwargs.kwargs["quantity"] == 0.0005

    def test_canceled_with_partial_fill_saves_trade(self, bot, mock_binance):
        """CANCELED with partial fill should save trade to memory"""
        self._setup_order(bot, mock_binance, "BUY")
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.memory = MagicMock()
        # Need to mock TradeRecord import inside _save_trade_to_memory
        with patch("src.core.bot.GridBot._save_trade_to_memory") as mock_save:
            bot._process_partial_fill(
                2001,
                bot.active_orders[2001],
                {"status": "CANCELED", "price": "50000.00", "executedQty": "0.0005"},
            )
            mock_save.assert_called_once()
            # Check that the partial qty was passed, not the original
            call_args = mock_save.call_args
            assert call_args.args[2] == 0.0005  # quantity argument

    def test_canceled_no_fill_cleanly_removed(self, bot, mock_binance):
        """CANCELED with executedQty=0 should be cleanly removed"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0",
        }

        bot.check_orders()

        assert 2001 not in bot.active_orders
        mock_binance.place_limit_buy.assert_not_called()
        mock_binance.place_limit_sell.assert_not_called()

    def test_expired_cleanly_removed(self, bot, mock_binance):
        """EXPIRED orders should be cleanly removed"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "EXPIRED",
            "price": "50000.00",
            "executedQty": "0",
        }

        bot.check_orders()

        assert 2001 not in bot.active_orders

    def test_rejected_cleanly_removed(self, bot, mock_binance):
        """REJECTED orders should be cleanly removed"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "REJECTED",
            "price": "50000.00",
            "executedQty": "0",
        }

        bot.check_orders()

        assert 2001 not in bot.active_orders

    def test_canceled_sell_partial_no_stop_loss(self, bot, mock_binance):
        """CANCELED SELL with partial fill should NOT create stop-loss"""
        self._setup_order(bot, mock_binance, "SELL")
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.stop_loss_manager = MagicMock()
        bot.check_orders()

        # Stop loss should NOT be created for SELL partial fills
        bot.stop_loss_manager.create_stop.assert_not_called()

    def test_canceled_partial_sends_telegram(self, bot, mock_binance):
        """CANCELED with partial fill should send Telegram notification"""
        self._setup_order(bot, mock_binance)
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }

        bot.check_orders()

        # Telegram should have been called with partial fill info
        bot.telegram.send.assert_called()
        call_args = bot.telegram.send.call_args.args[0]
        assert "Partial Fill" in call_args


# ═══════════════════════════════════════════════════════════════
# A3: Downtime-Fill-Recovery
# ═══════════════════════════════════════════════════════════════


class TestDowntimeFillRecovery:
    """Tests for load_state() recognizing fills during downtime and queuing follow-ups"""

    def _write_state_file(self, bot, orders):
        """Helper: write a bot_state.json with given orders"""
        import json

        state = {
            "timestamp": "2025-01-01T00:00:00",
            "symbol": "BTCUSDT",
            "active_orders": {str(k): v for k, v in orders.items()},
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

    def test_filled_order_queued_as_followup(self, bot, mock_binance):
        """FILLED orders in load_state should be queued in _pending_followups"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": "50000.00",
            "executedQty": "0.001",
        }

        bot.load_state()

        assert len(bot._pending_followups) == 1
        assert bot._pending_followups[0]["type"] == "BUY"
        assert bot._pending_followups[0]["price"] == 50000.0
        assert bot._pending_followups[0]["quantity"] == 0.001

    def test_filled_order_not_in_active(self, bot, mock_binance):
        """FILLED orders should NOT remain in active_orders"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": "50000.00",
            "executedQty": "0.001",
        }

        bot.load_state()

        assert 3001 not in bot.active_orders

    def test_filled_buy_creates_stop_loss(self, bot, mock_binance):
        """FILLED BUY during downtime should create stop-loss"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": "50000.00",
            "executedQty": "0.001",
        }
        bot.stop_loss_manager = MagicMock()

        bot.load_state()

        bot.stop_loss_manager.create_stop.assert_called_once()

    def test_filled_sell_no_stop_loss(self, bot, mock_binance):
        """FILLED SELL during downtime should NOT create stop-loss"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "SELL",
                    "price": 51000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": "51000.00",
            "executedQty": "0.001",
        }
        bot.stop_loss_manager = MagicMock()

        bot.load_state()

        bot.stop_loss_manager.create_stop.assert_not_called()

    def test_filled_sends_telegram(self, bot, mock_binance):
        """FILLED during downtime should send Telegram notification"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "FILLED",
            "price": "50000.00",
            "executedQty": "0.001",
        }

        bot.load_state()

        bot.telegram.send.assert_called()
        call_args = bot.telegram.send.call_args.args[0]
        assert "Downtime-Fill" in call_args

    def test_canceled_partial_during_downtime(self, bot, mock_binance):
        """CANCELED with partial fill during downtime should be processed"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "CANCELED",
            "price": "50000.00",
            "executedQty": "0.0005",
        }
        bot.stop_loss_manager = MagicMock()

        bot.load_state()

        # Should NOT be queued as follow-up (partial fills don't get follow-ups)
        assert len(bot._pending_followups) == 0
        # But should create stop-loss for the partial
        bot.stop_loss_manager.create_stop.assert_called_once()
        assert 3001 not in bot.active_orders

    def test_new_order_still_tracked(self, bot, mock_binance):
        """NEW orders should still be validated and kept"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                }
            },
        )
        mock_binance.get_order_status.return_value = {
            "status": "NEW",
            "price": "50000.00",
            "executedQty": "0",
        }

        result = bot.load_state()

        assert result is True
        assert 3001 in bot.active_orders

    def test_multiple_orders_mixed_status(self, bot, mock_binance):
        """Mix of FILLED, NEW, and CANCELED orders during downtime"""
        self._write_state_file(
            bot,
            {
                3001: {
                    "type": "BUY",
                    "price": 50000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                },
                3002: {
                    "type": "BUY",
                    "price": 49000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                },
                3003: {
                    "type": "SELL",
                    "price": 51000,
                    "quantity": 0.001,
                    "created_at": "2025-01-01T00:00:00",
                },
            },
        )

        def status_for_order(symbol, order_id):
            statuses = {
                3001: {"status": "FILLED", "price": "50000.00", "executedQty": "0.001"},
                3002: {"status": "NEW", "price": "49000.00", "executedQty": "0"},
                3003: {"status": "CANCELED", "price": "51000.00", "executedQty": "0"},
            }
            return statuses.get(order_id)

        mock_binance.get_order_status.side_effect = status_for_order

        result = bot.load_state()

        # 3001 FILLED -> queued as followup, not in active
        assert len(bot._pending_followups) == 1
        assert 3001 not in bot.active_orders
        # 3002 NEW -> still active
        assert 3002 in bot.active_orders
        # 3003 CANCELED no fill -> removed
        assert 3003 not in bot.active_orders
        assert result is True


class TestProcessPendingFollowups:
    """Tests for _process_pending_followups() placing follow-up orders"""

    def test_buy_fill_places_sell_followup(self, bot, mock_binance):
        """Pending BUY fill should place SELL follow-up via strategy"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        # Queue a fill at a level that has a next level above
        fill_price = float(bot.strategy.levels[1].price)
        bot._pending_followups = [{"type": "BUY", "price": fill_price, "quantity": 0.001}]

        bot._process_pending_followups()

        mock_binance.place_limit_sell.assert_called_once()
        assert len(bot._pending_followups) == 0

    def test_sell_fill_places_buy_followup(self, bot, mock_binance):
        """Pending SELL fill should place BUY follow-up via strategy"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        fill_price = float(bot.strategy.levels[2].price)
        bot._pending_followups = [{"type": "SELL", "price": fill_price, "quantity": 0.001}]

        bot._process_pending_followups()

        mock_binance.place_limit_buy.assert_called_once()
        assert len(bot._pending_followups) == 0

    def test_followup_blocked_by_risk(self, bot, mock_binance):
        """Pending follow-ups should be subject to risk checks"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        fill_price = float(bot.strategy.levels[1].price)
        bot._pending_followups = [{"type": "BUY", "price": fill_price, "quantity": 0.001}]

        # Block via portfolio stop
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.portfolio_stopped = True

        bot._process_pending_followups()

        mock_binance.place_limit_sell.assert_not_called()
        mock_binance.place_limit_buy.assert_not_called()

    def test_no_followups_noop(self, bot, mock_binance):
        """Empty pending list should be a no-op"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        bot._process_pending_followups()

        mock_binance.place_limit_sell.assert_not_called()
        mock_binance.place_limit_buy.assert_not_called()

    def test_no_strategy_noop(self, bot, mock_binance):
        """Without strategy, pending followups should not be processed"""
        bot._pending_followups = [{"type": "BUY", "price": 50000.0, "quantity": 0.001}]
        bot.strategy = None

        bot._process_pending_followups()

        mock_binance.place_limit_sell.assert_not_called()
        # Followups should remain (not cleared) since they weren't processed
        assert len(bot._pending_followups) == 1

    def test_successful_followup_added_to_active_orders(self, bot, mock_binance):
        """Placed follow-up order should appear in active_orders"""
        from src.strategies.grid_strategy import GridStrategy

        bot.symbol_info = mock_binance.get_symbol_info.return_value
        bot.strategy = GridStrategy(
            lower_price=47500,
            upper_price=52500,
            num_grids=4,
            total_investment=100,
            symbol_info=bot.symbol_info,
        )

        fill_price = float(bot.strategy.levels[1].price)
        bot._pending_followups = [{"type": "BUY", "price": fill_price, "quantity": 0.001}]

        bot._process_pending_followups()

        # The new order (orderId=200 from mock) should be in active_orders
        assert 200 in bot.active_orders
        assert bot.active_orders[200]["type"] == "SELL"


# ═══════════════════════════════════════════════════════════════
# A4: Stop-Loss DB Persistence + Market-Sell on Trigger
# ═══════════════════════════════════════════════════════════════


class TestStopLossDBPersistence:
    """Tests for stop_loss.py DB load/save and bot.py market-sell on trigger"""

    def test_load_from_db_restores_stops(self):
        """_load_from_db should restore active stops from database"""
        from src.risk.stop_loss import StopLossManager

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": "test-stop-1",
                "symbol": "BTCUSDT",
                "entry_price": 50000.0,
                "stop_price": 47500.0,
                "quantity": 0.001,
                "stop_type": "trailing",
                "stop_percentage": 5.0,
                "trailing_distance": 3.0,
                "highest_price": 51000.0,
                "is_active": True,
                "created_at": "2025-01-01T00:00:00",
            }
        ]
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = StopLossManager(db_manager=mock_db)

        assert "test-stop-1" in manager.stops
        stop = manager.stops["test-stop-1"]
        assert stop.symbol == "BTCUSDT"
        assert stop.entry_price == 50000.0
        assert stop.current_stop_price == 47500.0
        assert stop.highest_price == 51000.0
        assert stop.is_active is True

    def test_load_from_db_no_db_no_error(self):
        """Without DB, _load_from_db should not raise"""
        from src.risk.stop_loss import StopLossManager

        manager = StopLossManager(db_manager=None)
        assert len(manager.stops) == 0

    def test_load_from_db_empty_result(self):
        """Empty DB should result in no stops"""
        from src.risk.stop_loss import StopLossManager

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = StopLossManager(db_manager=mock_db)
        assert len(manager.stops) == 0

    def test_save_to_db_called_on_create(self):
        """create_stop should persist to DB"""
        from src.risk.stop_loss import StopLossManager

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = StopLossManager(db_manager=mock_db)
        manager.create_stop("BTCUSDT", 50000.0, 0.001)

        # get_cursor called for load (1) + save (1) = 2 times
        assert mock_db.get_cursor.call_count == 2

    def test_update_db_on_trigger(self):
        """Triggered stop should update DB"""
        from src.risk.stop_loss import StopLossManager

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = StopLossManager(db_manager=mock_db)
        stop = manager.create_stop("BTCUSDT", 50000.0, 0.001, stop_percentage=5.0)

        # Trigger: price drops below stop
        triggered = manager.update_all(prices={"BTCUSDT": 40000.0})

        assert len(triggered) == 1
        # load(1) + save(1) + update(1) = 3 calls to get_cursor
        assert mock_db.get_cursor.call_count == 3

    def test_create_stop_uses_full_uuid(self):
        """Stop IDs should be full UUIDs (36 chars)"""
        from src.risk.stop_loss import StopLossManager

        manager = StopLossManager(db_manager=None)
        stop = manager.create_stop("BTCUSDT", 50000.0, 0.001)

        assert len(stop.id) == 36  # Full UUID: 8-4-4-4-12

    def test_load_from_db_failure_graceful(self):
        """DB failure during load should not crash the manager"""
        from src.risk.stop_loss import StopLossManager

        mock_db = MagicMock()
        mock_db.get_cursor.side_effect = RuntimeError("DB unavailable")

        manager = StopLossManager(db_manager=mock_db)
        assert len(manager.stops) == 0


class TestStopLossMarketSell:
    """Tests for market-sell execution when stop-loss triggers"""

    def test_market_sell_on_trigger(self, bot, mock_binance):
        """Stop-loss trigger should execute market sell"""
        mock_binance.place_market_sell.return_value = {"success": True, "order": {}}

        bot.stop_loss_manager = MagicMock()
        triggered_stop = MagicMock()
        triggered_stop.symbol = "BTCUSDT"
        triggered_stop.quantity = 0.001
        bot.stop_loss_manager.update_all.return_value = [triggered_stop]

        bot._check_stop_losses(45000.0)

        mock_binance.place_market_sell.assert_called_once_with("BTCUSDT", 0.001)

    def test_market_sell_failure_notifies(self, bot, mock_binance):
        """Failed market sell should send urgent Telegram notification"""
        mock_binance.place_market_sell.return_value = {
            "success": False,
            "error": "Insufficient balance",
        }

        bot.stop_loss_manager = MagicMock()
        triggered_stop = MagicMock()
        triggered_stop.symbol = "BTCUSDT"
        triggered_stop.quantity = 0.001
        bot.stop_loss_manager.update_all.return_value = [triggered_stop]

        bot._check_stop_losses(45000.0)

        # Should send 2 messages: trigger notification + failure notification
        assert bot.telegram.send.call_count == 2
        failure_call = bot.telegram.send.call_args_list[1]
        assert "fehlgeschlagen" in failure_call.args[0]
        assert failure_call.kwargs.get("urgent") is True

    def test_no_trigger_no_sell(self, bot, mock_binance):
        """No triggered stops should not place any sell"""
        bot.stop_loss_manager = MagicMock()
        bot.stop_loss_manager.update_all.return_value = []

        bot._check_stop_losses(50000.0)

        mock_binance.place_market_sell.assert_not_called()
