"""Tests for src/tasks/data_tasks.py, market_tasks.py, and portfolio_tasks.py."""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# data_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskFetchEtfFlows:
    @patch("src.data.etf_flows.ETFFlowTracker.get_instance")
    def test_happy_path(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_etf_flows

        mock_tracker = MagicMock()
        mock_tracker.fetch_and_store_daily.return_value = [{"date": "2025-01-01", "flow": 100}]
        mock_tracker.get_institutional_signal.return_value = (0.6, "Strong inflow")
        mock_tracker_cls.return_value = mock_tracker

        task_fetch_etf_flows()

        mock_tracker.fetch_and_store_daily.assert_called_once()
        mock_tracker.get_institutional_signal.assert_called_once()

    @patch("src.data.etf_flows.ETFFlowTracker.get_instance")
    def test_no_flows(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_etf_flows

        mock_tracker = MagicMock()
        mock_tracker.fetch_and_store_daily.return_value = None
        mock_tracker_cls.return_value = mock_tracker

        task_fetch_etf_flows()

        mock_tracker.get_institutional_signal.assert_not_called()

    @patch("src.data.etf_flows.ETFFlowTracker.get_instance")
    def test_exception(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_etf_flows

        mock_tracker_cls.side_effect = Exception("API down")
        task_fetch_etf_flows()


class TestTaskFetchSocialSentiment:
    @patch("src.data.social_sentiment.SocialSentimentProvider.get_instance")
    def test_happy_path(self, mock_provider_cls):
        from src.tasks.data_tasks import task_fetch_social_sentiment

        mock_provider = MagicMock()
        metrics = MagicMock()
        metrics.composite_sentiment = 0.8
        metrics.social_volume = 50000
        mock_provider.get_aggregated_sentiment.return_value = metrics
        mock_provider_cls.return_value = mock_provider

        task_fetch_social_sentiment()

        assert mock_provider.get_aggregated_sentiment.call_count == 3

    @patch("src.data.social_sentiment.SocialSentimentProvider.get_instance")
    def test_no_metrics(self, mock_provider_cls):
        from src.tasks.data_tasks import task_fetch_social_sentiment

        mock_provider = MagicMock()
        mock_provider.get_aggregated_sentiment.return_value = None
        mock_provider_cls.return_value = mock_provider

        task_fetch_social_sentiment()

    @patch("src.data.social_sentiment.SocialSentimentProvider.get_instance")
    def test_exception(self, mock_provider_cls):
        from src.tasks.data_tasks import task_fetch_social_sentiment

        mock_provider_cls.side_effect = Exception("fail")
        task_fetch_social_sentiment()


class TestTaskFetchTokenUnlocks:
    @patch("src.data.token_unlocks.TokenUnlockTracker.get_instance")
    def test_happy_path(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_token_unlocks

        mock_tracker = MagicMock()
        mock_tracker.fetch_and_store_upcoming.return_value = [MagicMock()]
        unlock = MagicMock()
        unlock.expected_impact = "HIGH"
        unlock.symbol = "SOL"
        unlock.unlock_date.strftime.return_value = "15.01.2025"
        unlock.unlock_pct_of_supply = 5.2
        unlock.unlock_value_usd = 50_000_000
        mock_tracker.get_significant_unlocks.return_value = [unlock]
        mock_tracker_cls.return_value = mock_tracker

        task_fetch_token_unlocks()

        mock_tracker.fetch_and_store_upcoming.assert_called_once_with(days=14)
        mock_tracker.get_significant_unlocks.assert_called_once_with(days=7, min_pct=2.0)

    @patch("src.data.token_unlocks.TokenUnlockTracker.get_instance")
    def test_no_significant(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_token_unlocks

        mock_tracker = MagicMock()
        mock_tracker.fetch_and_store_upcoming.return_value = [MagicMock()]
        mock_tracker.get_significant_unlocks.return_value = []
        mock_tracker_cls.return_value = mock_tracker

        task_fetch_token_unlocks()

    @patch("src.data.token_unlocks.TokenUnlockTracker.get_instance")
    def test_exception(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_fetch_token_unlocks

        mock_tracker_cls.side_effect = Exception("fail")
        task_fetch_token_unlocks()


class TestTaskWhaleCheck:
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.core.config.get_config")
    @patch("src.data.whale_alert.WhaleAlertTracker")
    def test_happy_path(self, mock_tracker_cls, mock_config, mock_tg):
        from src.tasks.data_tasks import task_whale_check

        whale = MagicMock()
        whale.amount_usd = 10_000_000
        whale.symbol = "BTC"
        whale.amount = 100
        whale.potential_impact = "BULLISH"
        whale.from_owner = "unknown"
        whale.to_owner = "binance"

        mock_tracker = MagicMock()
        mock_tracker.fetch_recent_whales.return_value = [whale]
        mock_tracker_cls.return_value = mock_tracker

        config = MagicMock()
        config.whale.alert_threshold = 5_000_000
        mock_config.return_value = config

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_whale_check()

        mock_telegram.send_whale_alert.assert_called_once()

    @patch("src.data.whale_alert.WhaleAlertTracker")
    def test_no_whales(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_whale_check

        mock_tracker = MagicMock()
        mock_tracker.fetch_recent_whales.return_value = []
        mock_tracker_cls.return_value = mock_tracker

        task_whale_check()

    @patch("src.data.whale_alert.WhaleAlertTracker")
    def test_exception(self, mock_tracker_cls):
        from src.tasks.data_tasks import task_whale_check

        mock_tracker_cls.side_effect = Exception("fail")
        task_whale_check()


# ═══════════════════════════════════════════════════════════════
# market_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskMarketSnapshot:
    @patch("src.tasks.market_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_happy_path(self, mock_md, mock_db):
        from src.tasks.market_tasks import task_market_snapshot

        mock_market = MagicMock()
        fg = MagicMock()
        fg.value = 45
        mock_market.get_fear_greed.return_value = fg
        mock_market.get_price.return_value = 65000.0
        mock_market.get_btc_dominance.return_value = 52.3
        mock_md.return_value = mock_market

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        task_market_snapshot()

        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called()

    @patch("src.tasks.market_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.market_tasks import task_market_snapshot

        mock_db.return_value = None
        task_market_snapshot()


class TestTaskSentimentCheck:
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.data.market_data.get_market_data")
    def test_happy_path(self, mock_md, mock_tg):
        from src.tasks.market_tasks import task_sentiment_check

        mock_market = MagicMock()
        fg = MagicMock()
        fg.value = 20
        fg.classification = "Extreme Fear"
        mock_market.get_fear_greed.return_value = fg
        mock_md.return_value = mock_market

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_sentiment_check()

        mock_telegram.send_sentiment_alert.assert_called_once_with(20, "Extreme Fear")


# ═══════════════════════════════════════════════════════════════
# portfolio_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskUpdateWatchlist:
    @patch("src.data.watchlist.get_watchlist_manager")
    def test_happy_path(self, mock_wm):
        from src.tasks.portfolio_tasks import task_update_watchlist

        mock_manager = MagicMock()
        mock_manager.update_market_data.return_value = 25
        mock_manager.check_liquidity.return_value = ["LOWCAP1"]
        mock_wm.return_value = mock_manager

        task_update_watchlist()

        mock_manager.update_market_data.assert_called_once()
        mock_manager.check_liquidity.assert_called_once()

    @patch("src.data.watchlist.get_watchlist_manager")
    def test_no_deactivated(self, mock_wm):
        from src.tasks.portfolio_tasks import task_update_watchlist

        mock_manager = MagicMock()
        mock_manager.update_market_data.return_value = 25
        mock_manager.check_liquidity.return_value = []
        mock_wm.return_value = mock_manager

        task_update_watchlist()

    @patch("src.data.watchlist.get_watchlist_manager")
    def test_exception(self, mock_wm):
        from src.tasks.portfolio_tasks import task_update_watchlist

        mock_wm.side_effect = Exception("fail")
        task_update_watchlist()


class TestTaskScanOpportunities:
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    @patch("src.scanner.get_coin_scanner")
    def test_happy_path(self, mock_scanner, mock_db):
        from src.tasks.portfolio_tasks import task_scan_opportunities

        opp = MagicMock()
        opp.total_score = 0.75
        opp.symbol = "SOLUSDT"
        opp.category = "L2"
        opp.direction.name = "LONG"
        opp.risk_level.value = "MEDIUM"
        opp.signals = ["RSI_oversold", "volume_spike"]

        mock_sc = MagicMock()
        mock_sc.scan_opportunities.return_value = [opp]
        mock_sc.get_scan_stats.return_value = {"total_opportunities": 1, "average_score": 0.75}
        mock_sc.get_top_opportunities.return_value = [opp]
        mock_scanner.return_value = mock_sc

        mock_db.return_value = None

        task_scan_opportunities()

        mock_sc.scan_opportunities.assert_called_once_with(force_refresh=True)

    @patch("src.scanner.get_coin_scanner")
    def test_no_opportunities(self, mock_scanner):
        from src.tasks.portfolio_tasks import task_scan_opportunities

        mock_sc = MagicMock()
        mock_sc.scan_opportunities.return_value = []
        mock_scanner.return_value = mock_sc

        task_scan_opportunities()

    @patch("src.scanner.get_coin_scanner")
    def test_exception(self, mock_scanner):
        from src.tasks.portfolio_tasks import task_scan_opportunities

        mock_scanner.side_effect = Exception("fail")
        task_scan_opportunities()


class TestTaskPortfolioRebalance:
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    @patch("src.scanner.get_coin_scanner")
    @patch("src.portfolio.get_portfolio_allocator")
    def test_happy_path(self, mock_alloc, mock_scanner, mock_db):
        from src.tasks.portfolio_tasks import task_portfolio_rebalance

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "balanced"}]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_allocator = MagicMock()
        mock_allocator.get_portfolio_stats.return_value = {"position_count": 0, "total_value": 0}
        result = MagicMock()
        result.allocations = {"BTCUSDT": 500, "ETHUSDT": 300}
        result.total_allocated = 800
        result.cash_remaining = 200
        mock_allocator.calculate_allocation.return_value = result
        mock_alloc.return_value = mock_allocator

        mock_sc = MagicMock()
        mock_sc.get_top_opportunities.return_value = [MagicMock()]
        mock_scanner.return_value = mock_sc

        task_portfolio_rebalance()

        mock_allocator.calculate_allocation.assert_called_once()

    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.portfolio_tasks import task_portfolio_rebalance

        mock_db.return_value = None
        task_portfolio_rebalance()


class TestTaskCoinPerformanceUpdate:
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    @patch("src.data.watchlist.get_watchlist_manager")
    def test_happy_path(self, mock_wm, mock_db):
        from src.tasks.portfolio_tasks import task_coin_performance_update

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"symbol": "BTCUSDT", "total_trades": 10, "winning_trades": 7, "avg_return": 1.5}
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_manager = MagicMock()
        mock_wm.return_value = mock_manager

        task_coin_performance_update()

        mock_manager.update_coin_performance.assert_called_once()
        mock_conn.close.assert_called()

    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.portfolio_tasks import task_coin_performance_update

        mock_db.return_value = None
        task_coin_performance_update()
