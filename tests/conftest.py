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


# ═══════════════════════════════════════════════════════════════
# NEW MODULE FIXTURES (Phase 1-5)
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def reset_new_singletons():
    """Resettet alle neuen Singletons zwischen Tests"""
    yield

    # Reset all new singletons
    try:
        from src.core.cohort_manager import CohortManager

        CohortManager.reset_instance()
    except ImportError:
        pass

    try:
        from src.core.cycle_manager import CycleManager

        CycleManager.reset_instance()
    except ImportError:
        pass

    try:
        from src.analysis.signal_analyzer import SignalAnalyzer

        SignalAnalyzer.reset_instance()
    except ImportError:
        pass

    try:
        from src.analysis.metrics_calculator import MetricsCalculator

        MetricsCalculator.reset_instance()
    except ImportError:
        pass

    try:
        from src.analysis.regime_detection import RegimeDetector

        RegimeDetector.reset_instance()
    except ImportError:
        pass

    try:
        from src.analysis.bayesian_weights import BayesianWeightLearner

        BayesianWeightLearner.reset_instance()
    except ImportError:
        pass

    try:
        from src.analysis.divergence_detector import DivergenceDetector

        DivergenceDetector.reset_instance()
    except ImportError:
        pass

    try:
        from src.data.social_sentiment import SocialSentimentProvider

        SocialSentimentProvider.reset_instance()
    except ImportError:
        pass

    try:
        from src.data.etf_flows import ETFFlowTracker

        ETFFlowTracker.reset_instance()
    except ImportError:
        pass

    try:
        from src.data.token_unlocks import TokenUnlockTracker

        TokenUnlockTracker.reset_instance()
    except ImportError:
        pass

    try:
        from src.optimization.ab_testing import ABTestingFramework

        ABTestingFramework.reset_instance()
    except ImportError:
        pass

    try:
        from src.risk.cvar_sizing import CVaRPositionSizer

        CVaRPositionSizer.reset_instance()
    except ImportError:
        pass

    try:
        from src.strategies.dynamic_grid import DynamicGridStrategy

        DynamicGridStrategy.reset_instance()
    except ImportError:
        pass


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
