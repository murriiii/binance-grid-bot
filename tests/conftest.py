"""
Pytest Fixtures und Konfiguration
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# ═══════════════════════════════════════════════════════════════
# GRIDBOT FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def bot_config():
    return {
        "symbol": "BTCUSDT",
        "investment": 100,
        "num_grids": 3,
        "grid_range_percent": 5,
        "testnet": True,
    }


@pytest.fixture
def mock_binance():
    with patch("src.core.bot.BinanceClient") as mock_cls:
        client = MagicMock()
        client.get_account_balance.return_value = 1000.0
        client.get_current_price.return_value = 50000.0
        client.get_symbol_info.return_value = {
            "min_qty": 0.00001,
            "max_qty": 9000.0,
            "step_size": 0.00001,
            "tick_size": 0.01,
            "min_notional": 5.0,
        }
        client.get_open_orders.return_value = []
        client.place_limit_buy.return_value = {
            "success": True,
            "order": {"orderId": 100},
        }
        client.place_limit_sell.return_value = {
            "success": True,
            "order": {"orderId": 200},
        }
        mock_cls.return_value = client
        yield client


@pytest.fixture
def bot(bot_config, mock_binance):
    """Create a GridBot with mocked dependencies."""
    from src.core.bot import GridBot

    with (
        patch("src.core.bot.TelegramNotifier"),
        patch.object(GridBot, "_init_memory"),
        patch.object(GridBot, "_init_stop_loss"),
        patch.object(GridBot, "_init_risk_modules"),
    ):
        b = GridBot(bot_config)
        b.client = mock_binance
        b.stop_loss_manager = None
        b.cvar_sizer = None
        b.allocation_constraints = None
        return b


# ═══════════════════════════════════════════════════════════════
# NEW MODULE FIXTURES (Phase 1-5)
# ═══════════════════════════════════════════════════════════════


def _all_singleton_subclasses(cls):
    """Recursively collect all subclasses of SingletonMixin."""
    result = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_singleton_subclasses(sub))
    return result


@pytest.fixture
def reset_new_singletons():
    """Resettet alle neuen Singletons zwischen Tests"""
    yield

    from src.utils.singleton import SingletonMixin

    for cls in _all_singleton_subclasses(SingletonMixin):
        cls.reset_instance()


@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data for technical analysis"""
    import numpy as np

    np.random.seed(42)
    n = 100

    # Generate realistic price data
    returns = np.random.normal(0.001, 0.02, n)
    close = 100 * np.cumprod(1 + returns)

    # Generate high/low around close
    volatility = np.abs(np.random.normal(0, 0.01, n))
    high = close * (1 + volatility)
    low = close * (1 - volatility)
    open_price = close * (1 + np.random.normal(0, 0.005, n))

    volume = np.random.uniform(1000000, 10000000, n)

    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


@pytest.fixture
def sample_returns():
    """Sample return data for risk calculations"""
    import numpy as np

    np.random.seed(42)
    # Generate 100 days of returns with realistic properties
    returns = np.random.normal(0.001, 0.03, 100)  # Mean 0.1%, Std 3%
    return returns


@pytest.fixture
def sample_trade_history():
    """Sample trade history for signal analysis"""
    return [
        {"pnl": 50.0, "pnl_pct": 2.5, "was_correct": True},
        {"pnl": -30.0, "pnl_pct": -1.5, "was_correct": False},
        {"pnl": 80.0, "pnl_pct": 4.0, "was_correct": True},
        {"pnl": -20.0, "pnl_pct": -1.0, "was_correct": False},
        {"pnl": 60.0, "pnl_pct": 3.0, "was_correct": True},
        {"pnl": 40.0, "pnl_pct": 2.0, "was_correct": True},
        {"pnl": -45.0, "pnl_pct": -2.25, "was_correct": False},
        {"pnl": 70.0, "pnl_pct": 3.5, "was_correct": True},
    ]


@pytest.fixture
def sample_signals():
    """Sample signal values for testing"""
    return {
        "fear_greed": 0.3,
        "rsi": -0.2,
        "macd": 0.5,
        "trend": 0.4,
        "volume": 0.1,
        "whale": -0.1,
        "sentiment": 0.2,
        "macro": 0.0,
        "ai": 0.3,
    }


@pytest.fixture
def sample_cohort_config():
    """Sample cohort configuration"""
    return {
        "grid_range_pct": 5.0,
        "min_confidence": 0.5,
        "max_position_pct": 0.25,
        "risk_budget": 0.02,
    }
