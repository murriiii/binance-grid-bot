"""Tests for GridBot.tick() method and external BinanceClient support."""

from unittest.mock import MagicMock, patch

from src.core.bot import GridBot


class TestTick:
    def test_tick_returns_true_on_success(self, bot):
        """tick() returns True when everything is OK."""
        bot.client.get_open_orders.return_value = []
        result = bot.tick()
        assert result is True

    def test_tick_calls_check_orders(self, bot):
        """tick() calls check_orders()."""
        bot.check_orders = MagicMock()
        bot.tick()
        bot.check_orders.assert_called_once()

    def test_tick_calls_save_state(self, bot):
        """tick() calls save_state()."""
        bot.save_state = MagicMock()
        bot.tick()
        bot.save_state.assert_called_once()

    def test_tick_resets_error_counter(self, bot):
        """tick() resets consecutive_errors on success."""
        bot.consecutive_errors = 3
        bot.tick()
        assert bot.consecutive_errors == 0

    def test_tick_returns_false_on_circuit_breaker(self, bot):
        """tick() returns False when circuit breaker triggers."""
        bot._last_known_price = 50000.0
        # Price dropped >10%
        bot.client.get_current_price.return_value = 44000.0
        bot.telegram = MagicMock()

        result = bot.tick()
        assert result is False

    def test_tick_returns_false_on_portfolio_drawdown(self, bot):
        """tick() returns False when portfolio drawdown limit is hit."""
        mock_sl = MagicMock()
        mock_sl.portfolio_stopped = False
        mock_sl.check_portfolio_drawdown.return_value = (True, "Max drawdown reached")
        bot.stop_loss_manager = mock_sl
        bot.telegram = MagicMock()

        result = bot.tick()
        assert result is False

    def test_tick_continues_when_price_unavailable(self, bot):
        """tick() returns True even when price fetch fails."""
        bot.client.get_current_price.return_value = 0.0
        result = bot.tick()
        assert result is True

    def test_tick_checks_stop_losses(self, bot):
        """tick() calls _check_stop_losses when price is available."""
        bot._check_stop_losses = MagicMock()
        bot.client.get_current_price.return_value = 50000.0
        bot.tick()
        bot._check_stop_losses.assert_called_once_with(50000.0)

    def test_tick_skips_stop_losses_when_no_price(self, bot):
        """tick() skips stop loss check when no price available."""
        bot._check_stop_losses = MagicMock()
        bot.client.get_current_price.return_value = 0
        bot.tick()
        bot._check_stop_losses.assert_not_called()

    def test_tick_stops_after_consecutive_price_failures(self, bot):
        """tick() triggers emergency stop after 3 consecutive price failures."""
        bot.client.get_current_price.return_value = 0.0
        bot.telegram = MagicMock()

        # First two failures: continues
        assert bot.tick() is True
        assert bot.tick() is True
        # Third failure: emergency stop
        assert bot.tick() is False

    def test_tick_resets_price_failure_counter_on_success(self, bot):
        """tick() resets consecutive price failure counter when price returns."""
        bot.client.get_current_price.return_value = 0.0
        bot.telegram = MagicMock()

        bot.tick()  # failure 1
        bot.tick()  # failure 2

        # Price returns
        bot.client.get_current_price.return_value = 50000.0
        bot.tick()
        assert bot._consecutive_price_failures == 0

        # Failures start counting from 0 again
        bot.client.get_current_price.return_value = 0.0
        assert bot.tick() is True  # failure 1 again, not 3


class TestExternalClient:
    def test_external_client_used_when_provided(self, bot_config):
        """GridBot uses the provided external client instead of creating one."""
        external_client = MagicMock()
        with (
            patch("src.core.bot.TelegramNotifier"),
            patch.object(GridBot, "_init_memory"),
            patch.object(GridBot, "_init_stop_loss"),
            patch.object(GridBot, "_init_risk_modules"),
        ):
            b = GridBot(bot_config, client=external_client)
            assert b.client is external_client

    def test_internal_client_created_when_not_provided(self, bot_config, mock_binance):
        """GridBot creates its own client when none provided."""
        with (
            patch("src.core.bot.TelegramNotifier"),
            patch.object(GridBot, "_init_memory"),
            patch.object(GridBot, "_init_stop_loss"),
            patch.object(GridBot, "_init_risk_modules"),
        ):
            b = GridBot(bot_config)
            assert b.client is mock_binance

    def test_tick_works_with_external_client(self, bot_config):
        """tick() works correctly with an external BinanceClient."""
        external_client = MagicMock()
        external_client.get_current_price.return_value = 50000.0
        external_client.get_account_balance.return_value = 1000.0
        external_client.get_open_orders.return_value = []

        with (
            patch("src.core.bot.TelegramNotifier"),
            patch.object(GridBot, "_init_memory"),
            patch.object(GridBot, "_init_stop_loss"),
            patch.object(GridBot, "_init_risk_modules"),
        ):
            b = GridBot(bot_config, client=external_client)
            b.stop_loss_manager = None
            b.cvar_sizer = None
            b.allocation_constraints = None

            result = b.tick()
            assert result is True
            external_client.get_current_price.assert_called_once_with("BTCUSDT")
