"""Tests for PaperBinanceClient."""

from decimal import Decimal
from unittest.mock import patch

import pytest


class TestPaperBinanceClient:
    """Tests for the Paper Trading client."""

    def _make_client(self, initial_usdt=1000.0, tmp_path=None):
        """Create a fresh PaperBinanceClient."""
        from src.api.paper_client import PaperBinanceClient

        state_dir = str(tmp_path) if tmp_path else "/tmp/paper_test"
        return PaperBinanceClient(
            initial_usdt=initial_usdt,
            state_dir=state_dir,
            cohort_name="test",
        )

    def test_initial_balance(self, tmp_path):
        """Should start with the initial USDT balance."""
        client = self._make_client(1000.0, tmp_path)
        assert client.get_account_balance("USDT") == 1000.0
        assert client.get_account_balance("BTC") == 0.0

    def test_testnet_is_false(self, tmp_path):
        """Paper client should report testnet=False."""
        client = self._make_client(tmp_path=tmp_path)
        assert client.testnet is False

    def test_client_self_reference(self, tmp_path):
        """client.client should reference self for compatibility."""
        client = self._make_client(tmp_path=tmp_path)
        assert client.client is client

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_place_limit_buy(self, mock_price, tmp_path):
        """Should create a buy order and reserve USDT."""
        mock_price.return_value = 50000.0  # Won't fill immediately (price > limit)

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.01, 40000.0)

        assert result["success"] is True
        assert result["order"]["side"] == "BUY"
        # USDT reserved: 0.01 * 40000 = 400
        assert client.get_account_balance("USDT") == pytest.approx(600.0, abs=0.01)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_place_limit_buy_insufficient_balance(self, mock_price, tmp_path):
        """Should reject buy when balance is insufficient."""
        mock_price.return_value = 50000.0

        client = self._make_client(100.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.01, 50000.0)  # Cost: $500

        assert result["success"] is False
        assert "Insufficient" in result["error"]

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_place_limit_buy_immediate_fill(self, mock_price, tmp_path):
        """Should fill immediately if current price <= limit."""
        mock_price.return_value = 39000.0  # Below limit of 40000

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.01, 40000.0)

        assert result["success"] is True
        assert result["order"]["status"] == "FILLED"
        # Should have BTC now
        assert client.get_account_balance("BTC") > 0

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_place_limit_sell(self, mock_price, tmp_path):
        """Should create sell order and reserve base asset."""
        mock_price.return_value = 39000.0

        client = self._make_client(1000.0, tmp_path)
        # First buy some BTC
        client.place_limit_buy("BTCUSDT", 0.01, 40000.0)  # Fills at 39000

        # Now place a sell
        mock_price.return_value = 40000.0  # Below sell limit
        btc_balance = client.get_account_balance("BTC")
        result = client.place_limit_sell("BTCUSDT", btc_balance, 45000.0)

        assert result["success"] is True
        assert result["order"]["side"] == "SELL"

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_cancel_order_releases_funds(self, mock_price, tmp_path):
        """Canceling a buy should release reserved USDT."""
        mock_price.return_value = 50000.0  # Won't fill

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.01, 40000.0)
        order_id = result["order"]["orderId"]

        # USDT should be reserved
        assert client.get_account_balance("USDT") == pytest.approx(600.0, abs=0.01)

        # Cancel
        cancel = client.cancel_order("BTCUSDT", order_id)
        assert cancel["success"] is True

        # USDT should be restored
        assert client.get_account_balance("USDT") == pytest.approx(1000.0, abs=0.01)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_get_open_orders(self, mock_price, tmp_path):
        """Should return only NEW orders."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        client.place_limit_buy("BTCUSDT", 0.005, 40000.0)
        client.place_limit_buy("BTCUSDT", 0.005, 38000.0)

        orders = client.get_open_orders("BTCUSDT")
        assert len(orders) == 2
        assert all(o["status"] == "NEW" for o in orders)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_order_matching_on_price_check(self, mock_price, tmp_path):
        """Orders should fill when price moves past limit."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        client.place_limit_buy("BTCUSDT", 0.01, 40000.0)

        # Price drops below limit
        mock_price.return_value = 39000.0
        client.get_current_price("BTCUSDT")

        # Order should be filled now
        orders = client.get_open_orders("BTCUSDT")
        assert len(orders) == 0
        assert client.get_account_balance("BTC") > 0

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_market_buy(self, mock_price, tmp_path):
        """Market buy should fill immediately."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_market_buy("BTCUSDT", 500.0)

        assert result["success"] is True
        assert result["order"]["status"] == "FILLED"
        assert client.get_account_balance("BTC") > 0
        assert client.get_account_balance("USDT") < 1000.0

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_market_sell(self, mock_price, tmp_path):
        """Market sell should fill immediately."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        # Buy first
        client.place_market_buy("BTCUSDT", 500.0)
        btc = client.get_account_balance("BTC")

        # Sell
        result = client.place_market_sell("BTCUSDT", btc)
        assert result["success"] is True
        assert result["order"]["status"] == "FILLED"
        assert client.get_account_balance("BTC") == pytest.approx(0.0, abs=1e-8)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_fee_deduction(self, mock_price, tmp_path):
        """Fees should be deducted on fills (0.1%)."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_market_buy("BTCUSDT", 1000.0)

        # Should receive qty minus 0.1% fee
        qty = 1000.0 / 50000.0  # 0.02 BTC
        expected = qty * (1 - 0.001)  # 0.01998
        assert client.get_account_balance("BTC") == pytest.approx(expected, rel=0.01)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_state_persistence(self, mock_price, tmp_path):
        """State should persist across restarts."""
        mock_price.return_value = 50000.0

        client1 = self._make_client(1000.0, tmp_path)
        client1.place_market_buy("BTCUSDT", 500.0)
        btc_after_buy = client1.get_account_balance("BTC")

        # Create new client pointing to same state dir
        from src.api.paper_client import PaperBinanceClient

        client2 = PaperBinanceClient(
            initial_usdt=1000.0,
            state_dir=str(tmp_path),
            cohort_name="test",
        )

        assert client2.get_account_balance("BTC") == pytest.approx(btc_after_buy, rel=0.01)

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_get_all_orders(self, mock_price, tmp_path):
        """Should return all orders including filled/canceled."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)

        # Place and cancel one
        r1 = client.place_limit_buy("BTCUSDT", 0.005, 40000.0)
        client.cancel_order("BTCUSDT", r1["order"]["orderId"])

        # Place a market
        client.place_market_buy("BTCUSDT", 100.0)

        all_orders = client.get_all_orders("BTCUSDT")
        assert len(all_orders) == 2

        statuses = {o["status"] for o in all_orders}
        assert "CANCELED" in statuses
        assert "FILLED" in statuses

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_get_order_status(self, mock_price, tmp_path):
        """Should return order status by ID."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.005, 40000.0)
        order_id = result["order"]["orderId"]

        status = client.get_order_status("BTCUSDT", order_id)
        assert status is not None
        assert status["status"] == "NEW"

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_get_order_status_wrong_symbol(self, mock_price, tmp_path):
        """Should return None for wrong symbol."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", 0.005, 40000.0)
        order_id = result["order"]["orderId"]

        status = client.get_order_status("ETHUSDT", order_id)
        assert status is None

    def test_rate_limit_status(self, tmp_path):
        """Should return paper mode string."""
        client = self._make_client(tmp_path=tmp_path)
        assert "Paper" in client.get_rate_limit_status()

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_portfolio_summary(self, mock_price, tmp_path):
        """Should calculate total portfolio value."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        client.place_market_buy("BTCUSDT", 500.0)

        summary = client.get_portfolio_summary()
        # Total should be approximately initial minus fees
        assert summary["total_value_usd"] == pytest.approx(1000.0, rel=0.01)
        assert "BTC" in summary["positions"]

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_decimal_quantity_support(self, mock_price, tmp_path):
        """Should accept Decimal quantities."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_limit_buy("BTCUSDT", Decimal("0.01"), Decimal("40000"))

        assert result["success"] is True

    def test_cancel_nonexistent_order(self, tmp_path):
        """Should fail gracefully for nonexistent order."""
        client = self._make_client(tmp_path=tmp_path)
        result = client.cancel_order("BTCUSDT", 99999)
        assert result["success"] is False

    @patch("src.api.paper_client.PaperBinanceClient._fetch_mainnet_price")
    def test_cancel_filled_order(self, mock_price, tmp_path):
        """Should not cancel already filled order."""
        mock_price.return_value = 50000.0

        client = self._make_client(1000.0, tmp_path)
        result = client.place_market_buy("BTCUSDT", 100.0)
        order_id = result["order"]["orderId"]

        cancel = client.cancel_order("BTCUSDT", order_id)
        assert cancel["success"] is False
