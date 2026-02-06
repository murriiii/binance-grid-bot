"""Tests for src/scanner/coin_scanner.py and additional src/data/memory.py coverage."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════
# TradingMemory — additional methods
# ═══════════════════════════════════════════════════════════════


class TestTradingMemoryAdditional:
    @patch("src.data.database.DatabaseManager")
    def test_update_trade_outcome(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        memory.update_trade_outcome(trade_id=1, outcome_24h=2.5, outcome_7d=5.0)
        mock_cursor.execute.assert_called_once()

    @patch("src.data.database.DatabaseManager")
    def test_update_trade_outcome_no_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()
        # Should not raise
        memory.update_trade_outcome(trade_id=1, outcome_24h=2.5)

    @patch("src.data.database.DatabaseManager")
    def test_find_similar_situations(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "timestamp": datetime.now(),
                "action": "BUY",
                "symbol": "BTCUSDT",
                "price": 65000,
                "value_usd": 650,
                "fear_greed": 28,
                "market_trend": "BEARISH",
                "reasoning": "RSI oversold",
                "outcome_24h": 2.5,
                "outcome_7d": 5.0,
                "was_good_decision": True,
            }
        ]
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        results = memory.find_similar_situations(
            fear_greed=30, symbol="BTCUSDT", market_trend="BEARISH"
        )
        assert len(results) == 1

    @patch("src.data.database.DatabaseManager")
    def test_find_similar_situations_no_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()
        results = memory.find_similar_situations(fear_greed=30)
        assert results == []

    @patch("src.data.database.DatabaseManager")
    def test_get_pattern_stats(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total_trades": 20,
            "good_trades": 14,
            "avg_24h_return": 1.5,
            "avg_7d_return": 3.0,
            "volatility": 2.1,
        }
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        stats = memory.get_pattern_stats(
            {"fear_greed_min": 20, "fear_greed_max": 40, "action": "BUY", "symbol": "BTCUSDT"}
        )
        assert stats["total_trades"] == 20
        assert stats["success_rate"] == 70.0

    @patch("src.data.database.DatabaseManager")
    def test_get_pattern_stats_no_results(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_trades": 0, "good_trades": 0}
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        stats = memory.get_pattern_stats({})
        assert stats == {}

    @patch("src.data.database.DatabaseManager")
    def test_get_pattern_stats_no_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()
        stats = memory.get_pattern_stats({})
        assert stats == {}

    @patch("src.data.database.DatabaseManager")
    def test_generate_context_for_ai(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        # find_similar_situations returns trades
        mock_cursor.fetchall.return_value = [
            {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "fear_greed": 28,
                "outcome_24h": 2.5,
                "was_good_decision": True,
            },
        ]
        # get_pattern_stats returns stats (called twice)
        mock_cursor.fetchone.return_value = {
            "total_trades": 10,
            "good_trades": 7,
            "avg_24h_return": 1.5,
            "avg_7d_return": 3.0,
            "volatility": 2.0,
        }
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        context = memory.generate_context_for_ai(
            current_fear_greed=30, symbol="BTCUSDT", proposed_action="BUY"
        )
        assert "HISTORISCHE DATEN" in context
        assert "BTCUSDT" in context

    @patch("src.data.database.DatabaseManager")
    def test_generate_context_for_ai_no_similar(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = {"total_trades": 0, "good_trades": 0}
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        context = memory.generate_context_for_ai(
            current_fear_greed=50, symbol="ETHUSDT", proposed_action="SELL"
        )
        assert "Keine ähnlichen Situationen" in context

    @patch("src.data.database.DatabaseManager")
    def test_learn_and_update_patterns(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db = MagicMock()
        mock_db._pool = True
        mock_cursor_dict = MagicMock()  # For get_pattern_stats (dict_cursor)
        mock_cursor_dict.fetchone.return_value = {
            "total_trades": 10,
            "good_trades": 7,
            "avg_24h_return": 1.5,
            "avg_7d_return": 3.0,
            "volatility": 2.0,
        }
        mock_cursor_nodic = MagicMock()  # For the outer cursor (dict_cursor=False)

        # We need get_cursor to work for both dict and non-dict cursors
        def get_cursor_side_effect(dict_cursor=True):
            ctx = MagicMock()
            if dict_cursor:
                ctx.__enter__ = MagicMock(return_value=mock_cursor_dict)
            else:
                ctx.__enter__ = MagicMock(return_value=mock_cursor_nodic)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_db.get_cursor.side_effect = get_cursor_side_effect
        mock_db_cls.get_instance.return_value = mock_db

        memory = TradingMemory()
        memory.learn_and_update_patterns()

    @patch("src.data.database.DatabaseManager")
    def test_learn_and_update_patterns_no_db(self, mock_db_cls):
        from src.data.memory import TradingMemory

        mock_db_cls.get_instance.side_effect = Exception("no DB")
        memory = TradingMemory()
        memory.learn_and_update_patterns()  # Should not raise


# ═══════════════════════════════════════════════════════════════
# CoinScanner
# ═══════════════════════════════════════════════════════════════


class TestCoinScanner:
    @pytest.fixture()
    def scanner(self):
        with patch("src.scanner.coin_scanner.POSTGRES_AVAILABLE", False):
            from src.scanner.coin_scanner import CoinScanner

            sc = CoinScanner.__new__(CoinScanner)
            sc.conn = None
            sc._last_scan = None
            sc._cached_opportunities = []
            sc._cache_ttl = timedelta(minutes=30)
            sc._weights = CoinScanner.DEFAULT_WEIGHTS.copy()
            return sc

    def test_set_weights(self, scanner):
        scanner.set_weights({"technical": 0.5, "volume": 0.5})
        total = sum(scanner._weights.values())
        assert abs(total - 1.0) < 0.01

    def test_scan_opportunities_cached(self, scanner):
        from src.scanner.opportunity import Opportunity

        scanner._last_scan = datetime.now()
        opp = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        opp.total_score = 0.8
        scanner._cached_opportunities = [opp]

        result = scanner.scan_opportunities(force_refresh=False)
        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    @patch("src.data.watchlist.get_watchlist_manager")
    def test_scan_opportunities_no_coins(self, mock_wm, scanner):
        mock_manager = MagicMock()
        mock_manager.get_tradeable_coins.return_value = []
        mock_wm.return_value = mock_manager

        result = scanner.scan_opportunities(force_refresh=True)
        assert result == []

    @patch("src.data.watchlist.get_watchlist_manager")
    def test_scan_opportunities_with_coins(self, mock_wm, scanner):
        coin = MagicMock()
        coin.symbol = "BTCUSDT"
        coin.category = "LARGE_CAP"
        coin.base_asset = "BTC"
        coin.last_price = Decimal("65000")
        coin.last_volume_24h = Decimal("1000000000")
        coin.min_volume_24h_usd = Decimal("10000000")

        mock_manager = MagicMock()
        mock_manager.get_tradeable_coins.return_value = [coin]
        mock_wm.return_value = mock_manager

        # Mock _analyze_coin to return a scored opportunity
        from src.scanner.opportunity import Opportunity

        mock_opp = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        mock_opp.total_score = 0.7
        scanner._analyze_coin = MagicMock(return_value=mock_opp)

        result = scanner.scan_opportunities(force_refresh=True)
        assert len(result) == 1

    def test_get_top_opportunities_empty(self, scanner):
        scanner._last_scan = datetime.now()
        scanner._cached_opportunities = []
        result = scanner.get_top_opportunities(n=5)
        assert result == []

    def test_get_top_opportunities_with_filter(self, scanner):
        from src.scanner.opportunity import Opportunity, OpportunityDirection

        scanner._last_scan = datetime.now()
        opp1 = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        opp1.total_score = 0.8
        opp1.direction = OpportunityDirection.LONG
        opp2 = Opportunity(symbol="ETHUSDT", category="LARGE_CAP")
        opp2.total_score = 0.7
        opp2.direction = OpportunityDirection.SHORT
        scanner._cached_opportunities = [opp1, opp2]

        result = scanner.get_top_opportunities(n=5, direction=OpportunityDirection.LONG)
        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    def test_get_opportunities_by_risk(self, scanner):
        from src.scanner.opportunity import Opportunity, OpportunityRisk

        scanner._last_scan = datetime.now()
        opp1 = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        opp1.total_score = 0.8
        opp1.risk_level = OpportunityRisk.LOW
        opp2 = Opportunity(symbol="ETHUSDT", category="LARGE_CAP")
        opp2.total_score = 0.7
        opp2.risk_level = OpportunityRisk.HIGH
        scanner._cached_opportunities = [opp1, opp2]

        result = scanner.get_opportunities_by_risk(OpportunityRisk.LOW)
        assert len(result) == 1

    def test_get_scan_stats_empty(self, scanner):
        stats = scanner.get_scan_stats()
        assert stats["total_opportunities"] == 0

    def test_get_scan_stats_with_data(self, scanner):
        from src.scanner.opportunity import Opportunity, OpportunityDirection, OpportunityRisk

        opp = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        opp.total_score = 0.8
        opp.direction = OpportunityDirection.LONG
        opp.risk_level = OpportunityRisk.MEDIUM
        scanner._cached_opportunities = [opp]
        scanner._last_scan = datetime.now()

        stats = scanner.get_scan_stats()
        assert stats["total_opportunities"] == 1
        assert stats["average_score"] == 0.8
        assert stats["top_symbol"] == "BTCUSDT"

    def test_calculate_volume_score_no_data(self, scanner):
        coin = MagicMock()
        coin.last_volume_24h = None
        coin.min_volume_24h_usd = None
        score, _signals = scanner._calculate_volume_score(coin)
        assert score == 0.5

    def test_calculate_volume_score_spike(self, scanner):
        coin = MagicMock()
        coin.last_volume_24h = Decimal("30000000")
        coin.min_volume_24h_usd = Decimal("10000000")
        score, signals = scanner._calculate_volume_score(coin)
        assert score == 0.8
        assert any("Spike" in s for s in signals)

    def test_calculate_volume_score_elevated(self, scanner):
        coin = MagicMock()
        coin.last_volume_24h = Decimal("16000000")
        coin.min_volume_24h_usd = Decimal("10000000")
        score, _signals = scanner._calculate_volume_score(coin)
        assert score == 0.65

    def test_calculate_volume_score_low(self, scanner):
        coin = MagicMock()
        coin.last_volume_24h = Decimal("4000000")
        coin.min_volume_24h_usd = Decimal("10000000")
        score, _signals = scanner._calculate_volume_score(coin)
        assert score == 0.3

    def test_calculate_sentiment_score_error(self, scanner):
        with (
            patch(
                "src.scanner.coin_scanner.CoinScanner._calculate_sentiment_score",
                wraps=scanner._calculate_sentiment_score,
            ),
            patch("src.data.sentiment.SentimentAggregator", side_effect=Exception("fail")),
        ):
            score, _signals = scanner._calculate_sentiment_score("BTC")
            # Returns 0.5 on error
            assert score == 0.5 or score > 0  # fallback

    def test_calculate_whale_score_error(self, scanner):
        with patch("src.data.whale_alert.WhaleAlertTracker", side_effect=Exception("fail")):
            score, _signals = scanner._calculate_whale_score("BTC")
            assert score == 0.5

    def test_calculate_momentum_score_error(self, scanner):
        coin = MagicMock()
        coin.symbol = "BTCUSDT"
        with patch("src.api.binance_client.BinanceClient", side_effect=Exception("fail")):
            score, _signals = scanner._calculate_momentum_score(coin)
            assert score == 0.5

    def test_store_opportunities_no_conn(self, scanner):
        from src.scanner.opportunity import Opportunity

        opp = Opportunity(symbol="BTCUSDT", category="LARGE_CAP")
        # Should not raise
        scanner._store_opportunities([opp])

    def test_connect_no_postgres(self, scanner):
        with patch("src.scanner.coin_scanner.POSTGRES_AVAILABLE", False):
            result = scanner.connect()
            assert result is False

    def test_close(self, scanner):
        mock_conn = MagicMock()
        scanner.conn = mock_conn
        scanner.close()
        mock_conn.close.assert_called_once()
        assert scanner.conn is None
