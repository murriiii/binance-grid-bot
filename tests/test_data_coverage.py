"""Tests for src/data/ uncovered modules and src/analysis/technical_indicators.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ═══════════════════════════════════════════════════════════════
# technical_indicators.py
# ═══════════════════════════════════════════════════════════════


class TestTechnicalAnalyzer:
    @pytest.fixture()
    def analyzer(self):
        from src.analysis.technical_indicators import TechnicalAnalyzer

        return TechnicalAnalyzer()

    @pytest.fixture()
    def sample_prices(self):
        rng = np.random.default_rng(42)
        return pd.Series(rng.uniform(60000, 70000, 100))

    @pytest.fixture()
    def sample_df(self):
        rng = np.random.default_rng(42)
        n = 100
        return pd.DataFrame(
            {
                "open": rng.uniform(60000, 70000, n),
                "high": rng.uniform(65000, 72000, n),
                "low": rng.uniform(58000, 65000, n),
                "close": rng.uniform(60000, 70000, n),
                "volume": rng.uniform(1000, 5000, n),
            }
        )

    def test_calculate_rsi(self, analyzer, sample_prices):
        rsi = analyzer.calculate_rsi(sample_prices)
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_prices)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_calculate_macd(self, analyzer, sample_prices):
        macd, signal, histogram = analyzer.calculate_macd(sample_prices)
        assert isinstance(macd, pd.Series)
        assert isinstance(signal, pd.Series)
        assert isinstance(histogram, pd.Series)

    def test_calculate_bollinger_bands(self, analyzer, sample_prices):
        upper, middle, lower = analyzer.calculate_bollinger_bands(sample_prices)
        assert isinstance(upper, pd.Series)
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()

    def test_calculate_atr(self, analyzer, sample_df):
        atr = analyzer.calculate_atr(sample_df["high"], sample_df["low"], sample_df["close"])
        assert isinstance(atr, pd.Series)
        assert (atr.dropna() >= 0).all()

    def test_calculate_sma(self, analyzer, sample_prices):
        sma = analyzer.calculate_sma(sample_prices, period=20)
        assert isinstance(sma, pd.Series)

    def test_calculate_ema(self, analyzer, sample_prices):
        ema = analyzer.calculate_ema(sample_prices, period=12)
        assert isinstance(ema, pd.Series)

    def test_analyze(self, analyzer, sample_df):
        from src.analysis.technical_indicators import TechnicalSignals

        signals = analyzer.analyze(sample_df, symbol="BTCUSDT")
        assert isinstance(signals, TechnicalSignals)
        assert signals.symbol == "BTCUSDT"
        assert signals.rsi is not None
        assert signals.overall_signal is not None

    def test_get_entry_timing(self, analyzer, sample_df):
        signals = analyzer.analyze(sample_df, symbol="BTCUSDT")
        should_buy, reason = analyzer.get_entry_timing(signals)
        assert isinstance(should_buy, bool)
        assert isinstance(reason, str)

    def test_get_exit_timing(self, analyzer, sample_df):
        signals = analyzer.analyze(sample_df, symbol="BTCUSDT")
        should_sell, reason = analyzer.get_exit_timing(signals, entry_price=65000.0)
        assert isinstance(should_sell, bool)
        assert isinstance(reason, str)


class TestGenerateTAReport:
    def test_generate_report(self):
        from src.analysis.technical_indicators import TechnicalAnalyzer, generate_ta_report

        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {
                "open": rng.uniform(60000, 70000, 100),
                "high": rng.uniform(65000, 72000, 100),
                "low": rng.uniform(58000, 65000, 100),
                "close": rng.uniform(60000, 70000, 100),
                "volume": rng.uniform(1000, 5000, 100),
            }
        )

        analyzer = TechnicalAnalyzer()
        signals = analyzer.analyze(df, symbol="BTCUSDT")
        report = generate_ta_report(signals)

        assert isinstance(report, str)
        assert "BTCUSDT" in report


# ═══════════════════════════════════════════════════════════════
# memory.py
# ═══════════════════════════════════════════════════════════════


class TestTradingMemory:
    @patch("src.data.database.DatabaseManager")
    def test_init_with_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True  # Pool must be truthy
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        assert memory.db is not None

    @patch("src.data.database.DatabaseManager")
    def test_save_trade(self, mock_db_cls):
        from src.data.memory import TradeRecord, TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()

        trade = TradeRecord(
            timestamp=datetime.now(),
            action="BUY",
            symbol="BTCUSDT",
            price=65000.0,
            quantity=0.01,
            value_usd=650.0,
            fear_greed=45,
            btc_price=65000.0,
            symbol_24h_change=2.5,
            market_trend="BULLISH",
            math_signal="BUY",
            ai_signal="BUY",
            reasoning="RSI oversold",
        )

        result = memory.save_trade(trade)
        assert result == 42

    @patch("src.data.database.DatabaseManager")
    def test_save_trade_no_db(self, mock_db_cls):
        from src.data.memory import TradeRecord, TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()

        trade = TradeRecord(
            timestamp=datetime.now(),
            action="BUY",
            symbol="BTCUSDT",
            price=65000.0,
            quantity=0.01,
            value_usd=650.0,
            fear_greed=45,
            btc_price=65000.0,
            symbol_24h_change=2.5,
            market_trend="BULLISH",
            math_signal="BUY",
            ai_signal="BUY",
            reasoning="Test",
        )

        result = memory.save_trade(trade)
        assert result == -1

    @patch("src.data.database.DatabaseManager")
    def test_init_no_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()
        assert memory.db is None


# ═══════════════════════════════════════════════════════════════
# whale_alert.py
# ═══════════════════════════════════════════════════════════════


class TestWhaleTransaction:
    def test_exchange_deposit_bearish(self):
        from src.data.whale_alert import WhaleTransaction

        whale = WhaleTransaction(
            timestamp=datetime.now(),
            symbol="BTC",
            amount=100,
            amount_usd=6_500_000,
            tx_type="transfer",
            from_owner="unknown",
            to_owner="binance",
            tx_hash="abc123",
        )

        assert whale.is_exchange_deposit is True
        assert whale.is_exchange_withdrawal is False
        assert whale.potential_impact == "BEARISH"

    def test_withdrawal_bullish(self):
        from src.data.whale_alert import WhaleTransaction

        whale = WhaleTransaction(
            timestamp=datetime.now(),
            symbol="BTC",
            amount=100,
            amount_usd=6_500_000,
            tx_type="transfer",
            from_owner="binance",
            to_owner="unknown",
            tx_hash="abc123",
        )

        assert whale.is_exchange_withdrawal is True
        assert whale.is_exchange_deposit is False
        assert whale.potential_impact == "BULLISH"

    def test_neutral_transfer(self):
        from src.data.whale_alert import WhaleTransaction

        whale = WhaleTransaction(
            timestamp=datetime.now(),
            symbol="BTC",
            amount=100,
            amount_usd=6_500_000,
            tx_type="transfer",
            from_owner="unknown",
            to_owner="unknown",
            tx_hash="abc123",
        )

        assert whale.potential_impact == "NEUTRAL"

    def test_to_alert_message(self):
        from src.data.whale_alert import WhaleTransaction

        whale = WhaleTransaction(
            timestamp=datetime.now(),
            symbol="BTC",
            amount=100,
            amount_usd=6_500_000,
            tx_type="transfer",
            from_owner="unknown",
            to_owner="binance",
            tx_hash="abc123",
        )

        msg = whale.to_alert_message()
        assert "BTC" in msg
        assert isinstance(msg, str)


class TestWhaleAlertTracker:
    @patch("src.data.whale_alert.get_config")
    @patch("src.data.whale_alert.get_http_client")
    def test_init_and_threshold(self, mock_http, mock_config):
        from src.data.whale_alert import WhaleAlertTracker

        config = MagicMock()
        config.whale.btc_threshold = 10_000_000
        config.whale.eth_threshold = 5_000_000
        config.whale.default_threshold = 1_000_000
        mock_config.return_value = config

        mock_http.return_value = MagicMock()

        tracker = WhaleAlertTracker()
        threshold = tracker.get_threshold("BTC")
        assert threshold == 10_000_000

        threshold_default = tracker.get_threshold("DOGE")
        assert threshold_default == 1_000_000

    @patch("src.data.whale_alert.get_config")
    @patch("src.data.whale_alert.get_http_client")
    def test_analyze_whale_activity(self, mock_http, mock_config):
        from src.data.whale_alert import WhaleAlertTracker

        config = MagicMock()
        config.whale.btc_threshold = 10_000_000
        mock_config.return_value = config
        mock_http.return_value = MagicMock()

        tracker = WhaleAlertTracker()
        result = tracker.analyze_whale_activity("BTC", hours=24)

        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# playbook.py
# ═══════════════════════════════════════════════════════════════


class TestTradingPlaybook:
    def test_init_no_db(self):
        from src.data.playbook import TradingPlaybook

        pb = TradingPlaybook(db_connection=None)
        assert pb is not None
        assert pb.conn is None

    def test_get_playbook_for_prompt(self):
        from src.data.playbook import TradingPlaybook

        pb = TradingPlaybook(db_connection=None)
        result = pb.get_playbook_for_prompt()
        assert isinstance(result, str)
        assert "PLAYBOOK" in result

    def test_analyze_and_update_no_db(self):
        from src.data.playbook import TradingPlaybook

        pb = TradingPlaybook(db_connection=None)
        result = pb.analyze_and_update()
        assert "error" in result
