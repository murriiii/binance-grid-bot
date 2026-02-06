"""Tests for src/api/binance_client.py and src/data/fetcher.py."""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ═══════════════════════════════════════════════════════════════
# format_decimal
# ═══════════════════════════════════════════════════════════════


class TestFormatDecimal:
    def test_float(self):
        from src.api.binance_client import format_decimal

        assert format_decimal(1.5) == "1.5"

    def test_removes_trailing_zeros(self):
        from src.api.binance_client import format_decimal

        assert format_decimal(1.50000) == "1.5"

    def test_integer_value(self):
        from src.api.binance_client import format_decimal

        assert format_decimal(100.0) == "100"

    def test_decimal_input(self):
        from src.api.binance_client import format_decimal

        assert format_decimal(Decimal("0.00123000")) == "0.00123"

    def test_string_input(self):
        from src.api.binance_client import format_decimal

        assert format_decimal("0.001") == "0.001"

    def test_no_scientific_notation(self):
        from src.api.binance_client import format_decimal

        result = format_decimal(0.00000001)
        assert "e" not in result
        assert result == "0.00000001"


# ═══════════════════════════════════════════════════════════════
# RateLimiter
# ═══════════════════════════════════════════════════════════════


class TestRateLimiter:
    def test_acquire_under_limit(self):
        from src.api.binance_client import RateLimiter

        rl = RateLimiter(max_requests=100, window_seconds=60)
        rl.acquire()
        current, max_req = rl.get_usage()
        assert current == 1
        assert max_req == 100

    def test_get_usage(self):
        from src.api.binance_client import RateLimiter

        rl = RateLimiter(max_requests=10, window_seconds=60)
        rl.acquire()
        rl.acquire()
        current, max_req = rl.get_usage()
        assert current == 2
        assert max_req == 10

    def test_old_requests_expire(self):
        from src.api.binance_client import RateLimiter

        rl = RateLimiter(max_requests=10, window_seconds=1)
        rl.acquire()
        # Manually age the request
        rl.requests[0] = time.time() - 2
        current, _ = rl.get_usage()
        assert current == 0


# ═══════════════════════════════════════════════════════════════
# BinanceClient
# ═══════════════════════════════════════════════════════════════


class TestBinanceClient:
    @pytest.fixture()
    def client(self):
        with patch("src.api.binance_client.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            from src.api.binance_client import BinanceClient

            bc = BinanceClient(testnet=True)
            return bc

    def test_init_testnet(self, client):
        assert client.testnet is True

    @patch("src.api.binance_client.Client")
    def test_init_live(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        from src.api.binance_client import BinanceClient

        bc = BinanceClient(testnet=False)
        assert bc.testnet is False

    def test_get_account_balance(self, client):
        client.client.get_account.return_value = {
            "balances": [
                {"asset": "BTC", "free": "0.5"},
                {"asset": "USDT", "free": "1000.0"},
            ]
        }
        balance = client.get_account_balance("USDT")
        assert balance == 1000.0

    def test_get_account_balance_not_found(self, client):
        client.client.get_account.return_value = {"balances": [{"asset": "BTC", "free": "0.5"}]}
        balance = client.get_account_balance("ETH")
        assert balance == 0.0

    def test_get_account_balance_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_account.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        balance = client.get_account_balance("USDT")
        assert balance == 0.0

    def test_get_current_price(self, client):
        client.client.get_symbol_ticker.return_value = {"price": "65000.50"}
        price = client.get_current_price("BTCUSDT")
        assert price == 65000.50

    def test_get_current_price_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_symbol_ticker.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        price = client.get_current_price("BTCUSDT")
        assert price == 0.0

    def test_get_symbol_info(self, client):
        client.client.get_symbol_info.return_value = {
            "filters": [
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.00001",
                    "maxQty": "1000",
                    "stepSize": "0.00001",
                },
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "NOTIONAL", "minNotional": "10"},
            ]
        }
        info = client.get_symbol_info("BTCUSDT")
        assert info["min_qty"] == 0.00001
        assert info["step_size"] == 0.00001
        assert info["min_notional"] == 10.0

    def test_get_symbol_info_not_found(self, client):
        client.client.get_symbol_info.return_value = None
        info = client.get_symbol_info("INVALID")
        assert info is None

    def test_get_symbol_info_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_symbol_info.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        info = client.get_symbol_info("BTCUSDT")
        assert info is None

    def test_place_market_buy(self, client):
        client.client.order_market_buy.return_value = {"orderId": 123}
        result = client.place_market_buy("BTCUSDT", 100.0)
        assert result["success"] is True
        assert result["order"]["orderId"] == 123

    def test_place_market_buy_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.order_market_buy.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        result = client.place_market_buy("BTCUSDT", 100.0)
        assert result["success"] is False
        assert "error" in result

    def test_place_market_sell(self, client):
        client.client.order_market_sell.return_value = {"orderId": 456}
        result = client.place_market_sell("BTCUSDT", 0.01)
        assert result["success"] is True

    def test_place_market_sell_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.order_market_sell.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        result = client.place_market_sell("BTCUSDT", 0.01)
        assert result["success"] is False

    def test_place_limit_buy(self, client):
        client.client.order_limit_buy.return_value = {"orderId": 789}
        result = client.place_limit_buy("BTCUSDT", 0.01, 60000.0)
        assert result["success"] is True

    def test_place_limit_buy_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.order_limit_buy.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        result = client.place_limit_buy("BTCUSDT", 0.01, 60000.0)
        assert result["success"] is False

    def test_place_limit_sell(self, client):
        client.client.order_limit_sell.return_value = {"orderId": 101}
        result = client.place_limit_sell("BTCUSDT", 0.01, 70000.0)
        assert result["success"] is True

    def test_place_limit_sell_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.order_limit_sell.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        result = client.place_limit_sell("BTCUSDT", 0.01, 70000.0)
        assert result["success"] is False

    def test_get_open_orders(self, client):
        client.client.get_open_orders.return_value = [{"orderId": 1}, {"orderId": 2}]
        orders = client.get_open_orders("BTCUSDT")
        assert len(orders) == 2

    def test_get_open_orders_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_open_orders.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        orders = client.get_open_orders("BTCUSDT")
        assert orders == []

    def test_cancel_order(self, client):
        client.client.cancel_order.return_value = {"status": "CANCELED"}
        result = client.cancel_order("BTCUSDT", 123)
        assert result["success"] is True

    def test_cancel_order_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.cancel_order.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        result = client.cancel_order("BTCUSDT", 123)
        assert result["success"] is False

    def test_get_order_status(self, client):
        client.client.get_order.return_value = {"status": "FILLED", "orderId": 123}
        order = client.get_order_status("BTCUSDT", 123)
        assert order["status"] == "FILLED"

    def test_get_order_status_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_order.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        order = client.get_order_status("BTCUSDT", 123)
        assert order is None

    def test_get_all_orders(self, client):
        client.client.get_all_orders.return_value = [{"orderId": 1}]
        orders = client.get_all_orders("BTCUSDT")
        assert len(orders) == 1

    def test_get_all_orders_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_all_orders.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        orders = client.get_all_orders("BTCUSDT")
        assert orders == []

    def test_get_24h_ticker(self, client):
        client.client.get_ticker.return_value = {
            "priceChange": "1000.0",
            "priceChangePercent": "1.5",
            "highPrice": "66000.0",
            "lowPrice": "64000.0",
            "volume": "5000.0",
            "quoteVolume": "325000000.0",
        }
        ticker = client.get_24h_ticker("BTCUSDT")
        assert ticker["price_change"] == 1000.0
        assert ticker["price_change_percent"] == 1.5
        assert ticker["volume"] == 5000.0

    def test_get_24h_ticker_error(self, client):
        from binance.exceptions import BinanceAPIException

        client.client.get_ticker.side_effect = BinanceAPIException(MagicMock(), 400, "error")
        ticker = client.get_24h_ticker("BTCUSDT")
        assert ticker is None

    def test_get_rate_limit_status(self, client):
        status = client.get_rate_limit_status()
        assert isinstance(status, str)
        assert "/" in status

    def test_retry_call_server_error(self, client):
        from binance.exceptions import BinanceAPIException

        exc = BinanceAPIException(MagicMock(), 500, "Server Error")
        exc.code = -1000
        exc.status_code = 500

        client.client.get_account.side_effect = [exc, exc, {"balances": []}]
        with patch("time.sleep"):
            result = client._retry_call(client.client.get_account, retries=3)
        assert result == {"balances": []}

    def test_retry_call_non_retryable_error(self, client):
        from binance.exceptions import BinanceAPIException

        exc = BinanceAPIException(MagicMock(), 400, "Bad Request")
        exc.code = -1100
        exc.status_code = 400

        client.client.get_account.side_effect = exc
        with pytest.raises(BinanceAPIException):
            client._retry_call(client.client.get_account, retries=3)


# ═══════════════════════════════════════════════════════════════
# BinanceDataFetcher
# ═══════════════════════════════════════════════════════════════


class TestBinanceDataFetcher:
    @patch("src.data.fetcher.get_http_client")
    def test_fetch_klines(self, mock_http):
        from src.data.fetcher import BinanceDataFetcher

        # 12-column Binance kline format
        mock_data = [
            [
                1700000000000,
                "65000",
                "66000",
                "64000",
                "65500",
                "100",
                1700003600000,
                "6500000",
                500,
                "50",
                "3250000",
                "0",
            ],
            [
                1700003600000,
                "65500",
                "66500",
                "65000",
                "66000",
                "120",
                1700007200000,
                "7800000",
                600,
                "60",
                "3900000",
                "0",
            ],
        ]
        mock_http.return_value.get.return_value = mock_data

        with patch("pathlib.Path.mkdir"):
            fetcher = BinanceDataFetcher()

        df = fetcher.fetch_klines("BTCUSDT", interval="1d")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 2

    @patch("src.data.fetcher.get_http_client")
    def test_fetch_klines_with_dates(self, mock_http):
        from src.data.fetcher import BinanceDataFetcher

        mock_data = [
            [
                1700000000000,
                "65000",
                "66000",
                "64000",
                "65500",
                "100",
                1700003600000,
                "6500000",
                500,
                "50",
                "3250000",
                "0",
            ],
        ]
        mock_http.return_value.get.return_value = mock_data

        with patch("pathlib.Path.mkdir"):
            fetcher = BinanceDataFetcher()

        df = fetcher.fetch_klines("BTCUSDT", start_date="2024-01-01", end_date="2024-12-31")
        assert len(df) == 1

    @patch("src.data.fetcher.get_http_client")
    def test_fetch_multiple_symbols(self, mock_http):
        from src.data.fetcher import BinanceDataFetcher

        mock_data = [
            [
                1700000000000,
                "65000",
                "66000",
                "64000",
                "65500",
                "100",
                1700003600000,
                "6500000",
                500,
                "50",
                "3250000",
                "0",
            ],
        ]
        mock_http.return_value.get.return_value = mock_data

        with patch("pathlib.Path.mkdir"), patch("time.sleep"):
            fetcher = BinanceDataFetcher()
            result = fetcher.fetch_multiple_symbols(symbols=["BTCUSDT", "ETHUSDT"], days=30)

        assert isinstance(result, pd.DataFrame)

    @patch("src.data.fetcher.get_http_client")
    def test_fetch_multiple_symbols_error(self, mock_http):
        from src.data.fetcher import BinanceDataFetcher

        mock_http.return_value.get.side_effect = Exception("API Error")

        with patch("pathlib.Path.mkdir"), patch("time.sleep"):
            fetcher = BinanceDataFetcher()
            result = fetcher.fetch_multiple_symbols(symbols=["BTCUSDT"], days=30)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch("src.data.fetcher.get_http_client")
    def test_get_available_symbols(self, mock_http):
        from src.data.fetcher import BinanceDataFetcher

        mock_http.return_value.get.return_value = {
            "symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING"},
                {"symbol": "ETHUSDT", "status": "TRADING"},
                {"symbol": "BTCEUR", "status": "TRADING"},
                {"symbol": "OLDUSDT", "status": "BREAK"},
            ]
        }

        with patch("pathlib.Path.mkdir"):
            fetcher = BinanceDataFetcher()
            symbols = fetcher.get_available_symbols()

        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "BTCEUR" not in symbols  # Not USDT pair
        assert "OLDUSDT" not in symbols  # Not TRADING

    @patch("src.data.fetcher.get_http_client")
    def test_save_and_load_cache(self, mock_http, tmp_path):
        from src.data.fetcher import BinanceDataFetcher

        with patch("pathlib.Path.mkdir"):
            fetcher = BinanceDataFetcher()

        fetcher.CACHE_DIR = tmp_path

        df = pd.DataFrame({"close": [65000, 66000]}, index=pd.date_range("2024-01-01", periods=2))
        fetcher.save_to_cache(df, "test_data")

        loaded = fetcher.load_from_cache("test_data")
        assert loaded is not None
        assert len(loaded) == 2

    @patch("src.data.fetcher.get_http_client")
    def test_load_from_cache_missing(self, mock_http, tmp_path):
        from src.data.fetcher import BinanceDataFetcher

        with patch("pathlib.Path.mkdir"):
            fetcher = BinanceDataFetcher()

        fetcher.CACHE_DIR = tmp_path
        loaded = fetcher.load_from_cache("nonexistent")
        assert loaded is None
