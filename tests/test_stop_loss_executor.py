"""Tests for stop-loss executor with retry and balance awareness."""

from unittest.mock import MagicMock, patch

import pytest

from src.risk.stop_loss_executor import execute_stop_loss_sell


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_account_balance.return_value = 0.5
    client.get_symbol_info.return_value = {
        "min_qty": 0.00001,
        "step_size": 0.00001,
        "min_notional": 5.0,
    }
    client.place_market_sell.return_value = {
        "success": True,
        "order": {"orderId": 123},
    }
    return client


class TestExecuteStopLossSell:
    def test_success_first_attempt(self, mock_client):
        result = execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        assert result["success"] is True
        mock_client.place_market_sell.assert_called_once()

    @patch("src.risk.stop_loss_executor.time.sleep")
    def test_success_on_retry(self, mock_sleep, mock_client):
        mock_client.place_market_sell.side_effect = [
            {"success": False, "error": "timeout"},
            {"success": True, "order": {"orderId": 456}},
        ]

        result = execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        assert result["success"] is True
        assert mock_client.place_market_sell.call_count == 2
        mock_sleep.assert_called_once_with(2)

    @patch("src.risk.stop_loss_executor.time.sleep")
    def test_all_retries_exhausted(self, mock_sleep, mock_client):
        mock_client.place_market_sell.return_value = {
            "success": False,
            "error": "insufficient balance",
        }

        result = execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        assert result["success"] is False
        assert "FAILED after 3 attempts" in result["error"]
        assert mock_client.place_market_sell.call_count == 3

    @patch("src.risk.stop_loss_executor.time.sleep")
    def test_all_retries_exhausted_sends_telegram(self, mock_sleep, mock_client):
        mock_client.place_market_sell.return_value = {
            "success": False,
            "error": "rate limit",
        }
        telegram = MagicMock()

        execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5, telegram=telegram)

        telegram.send.assert_called_once()
        call_msg = telegram.send.call_args[0][0]
        assert "CRITICAL" in call_msg
        assert "Manual sell needed" in call_msg

    def test_balance_aware_uses_min_quantity(self, mock_client):
        """If actual balance < intended, uses actual balance."""
        mock_client.get_account_balance.return_value = 0.3

        execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        sell_qty = mock_client.place_market_sell.call_args[0][1]
        assert sell_qty <= 0.3

    def test_balance_unavailable_uses_intended(self, mock_client):
        """If balance query fails, falls back to intended quantity."""
        mock_client.get_account_balance.side_effect = Exception("API error")

        execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        sell_qty = mock_client.place_market_sell.call_args[0][1]
        assert sell_qty == pytest.approx(0.5, abs=0.0001)

    def test_step_size_rounding(self, mock_client):
        """Quantity is rounded to step_size."""
        mock_client.get_account_balance.return_value = 1.0
        mock_client.get_symbol_info.return_value = {
            "step_size": 0.001,
            "min_qty": 0.001,
            "min_notional": 5.0,
        }

        execute_stop_loss_sell(mock_client, "BTCUSDT", 0.1234567)

        sell_qty = mock_client.place_market_sell.call_args[0][1]
        assert sell_qty == pytest.approx(0.123, abs=1e-8)

    def test_zero_quantity_aborts(self, mock_client):
        """If quantity rounds to zero, abort without trying to sell."""
        mock_client.get_account_balance.return_value = 0.0000001
        mock_client.get_symbol_info.return_value = {
            "step_size": 0.001,
            "min_qty": 0.001,
            "min_notional": 5.0,
        }

        result = execute_stop_loss_sell(mock_client, "BTCUSDT", 0.0000001)

        assert result["success"] is False
        assert "zero quantity" in result["error"]
        mock_client.place_market_sell.assert_not_called()

    def test_symbol_info_unavailable_still_sells(self, mock_client):
        """If symbol_info fails, still attempts sell with unrounded quantity."""
        mock_client.get_symbol_info.side_effect = Exception("API error")
        mock_client.get_account_balance.return_value = 0.5

        result = execute_stop_loss_sell(mock_client, "BTCUSDT", 0.5)

        assert result["success"] is True


class TestStopLossOrderLifecycle:
    """Test the confirm_trigger / reactivate lifecycle."""

    def test_update_does_not_deactivate(self):
        from src.risk.stop_loss import StopLossOrder, StopType

        stop = StopLossOrder(
            id="test-1",
            symbol="BTCUSDT",
            entry_price=100.0,
            quantity=1.0,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )

        triggered = stop.update(current_price=94.0)

        assert triggered is True
        assert stop.is_active is True  # NOT deactivated yet
        assert stop.triggered_price == 94.0

    def test_confirm_trigger_deactivates(self):
        from src.risk.stop_loss import StopLossOrder, StopType

        stop = StopLossOrder(
            id="test-1",
            symbol="BTCUSDT",
            entry_price=100.0,
            quantity=1.0,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )
        stop.update(current_price=94.0)
        stop.confirm_trigger()

        assert stop.is_active is False
        assert stop.result_pnl_pct == pytest.approx(-6.0, abs=0.1)

    def test_reactivate_after_failed_sell(self):
        from src.risk.stop_loss import StopLossOrder, StopType

        stop = StopLossOrder(
            id="test-1",
            symbol="BTCUSDT",
            entry_price=100.0,
            quantity=1.0,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )
        stop.update(current_price=94.0)
        stop.reactivate()

        assert stop.is_active is True
        assert stop.triggered_price is None
        assert stop.triggered_at is None

    def test_legacy_trigger_still_works(self):
        """Backward compat: trigger() deactivates in one step."""
        from src.risk.stop_loss import StopLossOrder, StopType

        stop = StopLossOrder(
            id="test-1",
            symbol="BTCUSDT",
            entry_price=100.0,
            quantity=1.0,
            stop_type=StopType.FIXED,
            stop_percentage=5.0,
        )
        stop.trigger(94.0)

        assert stop.is_active is False
        assert stop.triggered_price == 94.0
        assert stop.result_pnl_pct == pytest.approx(-6.0, abs=0.1)
