"""
Pytest Fixtures und Konfiguration
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Setzt Test-Environment-Variablen"""
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test_api_key")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET", "test_secret")
    monkeypatch.setenv("TRADING_PAIR", "BTCUSDT")
    monkeypatch.setenv("INVESTMENT_AMOUNT", "100")
    monkeypatch.setenv("NUM_GRIDS", "5")
    monkeypatch.setenv("GRID_RANGE_PERCENT", "5")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_deepseek_key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")


@pytest.fixture
def reset_singletons():
    """Resettet alle Singletons zwischen Tests"""
    # Reset config singleton
    import src.core.config as config_module

    config_module._config = None

    # Reset HTTP client singleton
    import src.api.http_client as http_module

    http_module._client_instance = None

    # Reset Telegram singleton
    import src.notifications.telegram_service as telegram_module

    telegram_module.TelegramService._instance = None

    # Reset MarketData singleton
    import src.data.market_data as market_module

    market_module.MarketDataProvider._instance = None

    yield

    # Cleanup after test
    config_module._config = None
    http_module._client_instance = None
    telegram_module.TelegramService._instance = None
    market_module.MarketDataProvider._instance = None


# ═══════════════════════════════════════════════════════════════
# MOCK DATA FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_symbol_info():
    """Beispiel Binance Symbol Info"""
    return {
        "symbol": "BTCUSDT",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "1000000.00",
                "tickSize": "0.01",
            },
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00001",
                "maxQty": "9000.00",
                "stepSize": "0.00001",
            },
            {"filterType": "MIN_NOTIONAL", "minNotional": "5.00"},
        ],
    }


@pytest.fixture
def sample_fear_greed_response():
    """Beispiel Fear & Greed API Response"""
    return {
        "data": [
            {
                "value": "45",
                "value_classification": "Fear",
                "timestamp": str(int(datetime.now().timestamp())),
            }
        ]
    }


@pytest.fixture
def sample_btc_price_response():
    """Beispiel Binance Price Response"""
    return {"symbol": "BTCUSDT", "price": "42500.50"}


@pytest.fixture
def sample_ticker_24h_response():
    """Beispiel 24h Ticker Response"""
    return {
        "symbol": "BTCUSDT",
        "lastPrice": "42500.50",
        "priceChangePercent": "2.5",
        "quoteVolume": "1500000000",
    }


@pytest.fixture
def sample_coingecko_trending():
    """Beispiel CoinGecko Trending Response"""
    return {
        "coins": [
            {"item": {"symbol": "BTC", "name": "Bitcoin", "market_cap_rank": 1, "price_btc": 1.0}},
            {
                "item": {
                    "symbol": "ETH",
                    "name": "Ethereum",
                    "market_cap_rank": 2,
                    "price_btc": 0.05,
                }
            },
            {"item": {"symbol": "SOL", "name": "Solana", "market_cap_rank": 5, "price_btc": 0.002}},
        ]
    }


@pytest.fixture
def sample_whale_transactions():
    """Beispiel Blockchain.com Transactions"""
    return {
        "txs": [
            {
                "time": int(datetime.now().timestamp()),
                "hash": "abc123",
                "inputs": [
                    {
                        "prev_out": {
                            "addr": "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h",
                            "value": 10000000000,
                        }
                    }
                ],
                "out": [{"addr": "unknown_address", "value": 10000000000}],
            }
        ]
    }


@pytest.fixture
def sample_economic_events():
    """Beispiel Economic Calendar Response"""
    return {
        "result": [
            {
                "date": datetime.now().isoformat() + "Z",
                "title": "FOMC Meeting",
                "country": "US",
                "importance": 3,
                "previous": "5.25%",
                "forecast": "5.25%",
                "actual": "",
            }
        ]
    }


# ═══════════════════════════════════════════════════════════════
# MOCK OBJECTS
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def mock_http_client():
    """Mock HTTP Client"""
    mock = MagicMock()
    mock.get.return_value = {}
    mock.post.return_value = {}
    mock.stats = {"requests": 0, "successes": 0, "retries": 0, "failures": 0}
    return mock


@pytest.fixture
def mock_binance_client():
    """Mock Binance Client"""
    mock = MagicMock()
    mock.get_symbol_info.return_value = {
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "LOT_SIZE", "minQty": "0.00001", "stepSize": "0.00001"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "5.00"},
        ],
    }
    mock.get_symbol_ticker.return_value = {"price": "42500.50"}
    mock.create_order.return_value = {"orderId": 12345, "status": "NEW"}
    mock.get_order.return_value = {"orderId": 12345, "status": "FILLED"}
    mock.get_account.return_value = {"balances": [{"asset": "USDT", "free": "1000.00"}]}
    return mock


@pytest.fixture
def mock_db_connection():
    """Mock Database Connection"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": 1}
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn
