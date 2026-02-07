"""Tests for AI-Enhanced Coin Auto-Discovery."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class TestCoinDiscovery:
    """Tests for CoinDiscovery class."""

    def test_singleton_pattern(self, reset_new_singletons):
        """CoinDiscovery follows SingletonMixin pattern."""
        from src.scanner.coin_discovery import CoinDiscovery

        s1 = CoinDiscovery.get_instance()
        s2 = CoinDiscovery.get_instance()
        assert s1 is s2

    @patch("src.api.http_client.get_http_client")
    def test_fetch_all_usdt_pairs(self, mock_http, reset_new_singletons):
        """Should fetch and filter USDT trading pairs."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_http.return_value.get.return_value = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                },
                {
                    "symbol": "ETHBTC",
                    "baseAsset": "ETH",
                    "quoteAsset": "BTC",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                },
                {
                    "symbol": "XRPUSDT",
                    "baseAsset": "XRP",
                    "quoteAsset": "USDT",
                    "status": "BREAK",
                    "isSpotTradingAllowed": True,
                },
            ]
        }

        discovery = CoinDiscovery()
        pairs = discovery._fetch_all_usdt_pairs()

        assert len(pairs) == 1
        assert pairs[0]["symbol"] == "BTCUSDT"

    @patch("src.api.http_client.get_http_client")
    def test_fetch_all_usdt_pairs_api_failure(self, mock_http, reset_new_singletons):
        """Should return empty list on API failure."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_http.return_value.get.side_effect = RuntimeError("API down")

        discovery = CoinDiscovery()
        pairs = discovery._fetch_all_usdt_pairs()
        assert pairs == []

    @patch("src.api.http_client.get_http_client")
    def test_filter_by_volume(self, mock_http, reset_new_singletons):
        """Should filter pairs by minimum volume."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_http.return_value.get.return_value = [
            {"symbol": "AAAUSDT", "quoteVolume": "5000000"},
            {"symbol": "BBBUSDT", "quoteVolume": "100000"},
            {"symbol": "CCCUSDT", "quoteVolume": "2000000"},
        ]

        discovery = CoinDiscovery()
        pairs = [
            {"symbol": "AAAUSDT", "base_asset": "AAA"},
            {"symbol": "BBBUSDT", "base_asset": "BBB"},
            {"symbol": "CCCUSDT", "base_asset": "CCC"},
        ]
        result = discovery._filter_by_volume(pairs)

        assert len(result) == 2
        assert result[0]["symbol"] == "AAAUSDT"  # Sorted by volume desc
        assert result[1]["symbol"] == "CCCUSDT"

    def test_format_discovery_history_empty(self, reset_new_singletons):
        """Should handle empty history."""
        from src.scanner.coin_discovery import CoinDiscovery

        discovery = CoinDiscovery()
        result = discovery._format_discovery_history([])
        assert "erster Durchlauf" in result

    def test_format_discovery_history_with_results(self, reset_new_singletons):
        """Should format history with outcomes."""
        from src.scanner.coin_discovery import CoinDiscovery

        discovery = CoinDiscovery()
        history = [
            {
                "symbol": "AAAUSDT",
                "ai_approved": True,
                "ai_category": "DEFI",
                "ai_tier": 2,
                "ai_reason": "Good liquidity",
                "was_added": True,
                "was_deactivated": False,
                "deactivated_reason": None,
                "trades_after_30d": 45,
                "win_rate_after_30d": 62,
                "avg_return_after_30d": 3.2,
                "was_good_discovery": True,
                "discovered_at": datetime.utcnow() - timedelta(days=40),
            },
            {
                "symbol": "BBBUSDT",
                "ai_approved": True,
                "ai_category": "MEME",
                "ai_tier": 3,
                "ai_reason": "High vol",
                "was_added": True,
                "was_deactivated": True,
                "deactivated_reason": "No trades after 7 days",
                "trades_after_30d": 2,
                "win_rate_after_30d": 30,
                "avg_return_after_30d": -4.1,
                "was_good_discovery": False,
                "discovered_at": datetime.utcnow() - timedelta(days=45),
            },
            {
                "symbol": "CCCUSDT",
                "ai_approved": False,
                "ai_category": "AI",
                "ai_tier": 2,
                "ai_reason": "Low volume",
                "was_added": False,
                "was_deactivated": False,
                "deactivated_reason": None,
                "trades_after_30d": None,
                "win_rate_after_30d": None,
                "avg_return_after_30d": None,
                "was_good_discovery": None,
                "discovered_at": datetime.utcnow() - timedelta(days=10),
            },
        ]

        result = discovery._format_discovery_history(history)
        assert "OK AAAUSDT" in result
        assert "FAIL BBBUSDT" in result
        assert "SKIP CCCUSDT" in result

    @patch("src.api.http_client.get_http_client")
    def test_ai_evaluate_parses_json(self, mock_http, reset_new_singletons):
        """Should parse AI JSON response correctly."""
        from src.scanner.coin_discovery import CoinDiscovery

        ai_response = json.dumps(
            [
                {
                    "symbol": "AAAUSDT",
                    "category": "DEFI",
                    "tier": 2,
                    "risk": "medium",
                    "approved": True,
                    "reason": "Good liquidity",
                }
            ]
        )

        mock_http.return_value.post.return_value = {
            "choices": [{"message": {"content": ai_response}}]
        }
        mock_http.return_value.get.return_value = {"symbols": []}

        discovery = CoinDiscovery()
        discovery.api_key = "test-key"

        candidates = [{"symbol": "AAAUSDT", "base_asset": "AAA", "volume_24h": 5_000_000}]

        with (
            patch("src.data.playbook.TradingPlaybook"),
            patch("src.tasks.base.get_db_connection", return_value=None),
        ):
            result = discovery._ai_evaluate(candidates, [])

        assert len(result) == 1
        assert result[0]["symbol"] == "AAAUSDT"
        assert result[0]["approved"] is True

    @patch("src.api.http_client.get_http_client")
    def test_ai_evaluate_handles_markdown_code_blocks(self, mock_http, reset_new_singletons):
        """Should handle AI response wrapped in markdown code blocks."""
        from src.scanner.coin_discovery import CoinDiscovery

        ai_response = '```json\n[{"symbol": "AAAUSDT", "category": "DEFI", "tier": 2, "risk": "low", "approved": false, "reason": "No"}]\n```'

        mock_http.return_value.post.return_value = {
            "choices": [{"message": {"content": ai_response}}]
        }

        discovery = CoinDiscovery()
        discovery.api_key = "test-key"

        candidates = [{"symbol": "AAAUSDT", "base_asset": "AAA", "volume_24h": 2_000_000}]

        with (
            patch("src.data.playbook.TradingPlaybook"),
            patch("src.tasks.base.get_db_connection", return_value=None),
        ):
            result = discovery._ai_evaluate(candidates, [])

        assert len(result) == 1
        assert result[0]["approved"] is False

    @patch("src.api.http_client.get_http_client")
    def test_ai_evaluate_handles_invalid_json(self, mock_http, reset_new_singletons):
        """Should return empty list on invalid JSON."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_http.return_value.post.return_value = {
            "choices": [{"message": {"content": "Sorry, I can't do that."}}]
        }

        discovery = CoinDiscovery()
        discovery.api_key = "test-key"

        with (
            patch("src.data.playbook.TradingPlaybook"),
            patch("src.tasks.base.get_db_connection", return_value=None),
        ):
            result = discovery._ai_evaluate(
                [{"symbol": "X", "base_asset": "X", "volume_24h": 1}], []
            )

        assert result == []

    def test_run_discovery_no_api_key(self, reset_new_singletons):
        """Should fail gracefully without API key."""
        from src.scanner.coin_discovery import CoinDiscovery

        discovery = CoinDiscovery()
        discovery.api_key = None

        result = discovery.run_discovery()
        assert "DEEPSEEK_API_KEY not set" in result["errors"]

    @patch("src.tasks.base.get_db_connection")
    def test_run_discovery_no_db(self, mock_db, reset_new_singletons):
        """Should fail gracefully without DB."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_db.return_value = None

        discovery = CoinDiscovery()
        discovery.api_key = "test-key"

        result = discovery.run_discovery()
        assert "No DB connection" in result["errors"]

    @patch("src.tasks.base.get_db_connection")
    @patch.object(
        __import__("src.scanner.coin_discovery", fromlist=["CoinDiscovery"]).CoinDiscovery,
        "_fetch_all_usdt_pairs",
        return_value=[],
    )
    def test_run_discovery_no_pairs(self, _mock_fetch, mock_db, reset_new_singletons):
        """Should handle no pairs found."""
        from src.scanner.coin_discovery import CoinDiscovery

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn

        discovery = CoinDiscovery()
        discovery.api_key = "test-key"

        result = discovery.run_discovery()
        assert "Failed to fetch exchange info" in result["errors"]


class TestTaskAutoDiscovery:
    """Tests for the scheduled task wrapper."""

    @patch("src.scanner.coin_discovery.CoinDiscovery")
    @patch("src.notifications.telegram_service.get_telegram")
    def test_task_sends_notification_on_success(self, mock_tg, mock_disc, reset_new_singletons):
        """Should send Telegram notification when coins are added."""
        from src.tasks.portfolio_tasks import task_auto_discovery

        mock_disc.get_instance.return_value.run_discovery.return_value = {
            "candidates": 10,
            "evaluated": 10,
            "approved": 2,
            "added": 2,
            "errors": [],
        }

        task_auto_discovery()

        mock_tg.return_value.send.assert_called_once()
        call_args = mock_tg.return_value.send.call_args[0][0]
        assert "AUTO-DISCOVERY" in call_args
        assert "2" in call_args

    @patch("src.scanner.coin_discovery.CoinDiscovery")
    @patch("src.notifications.telegram_service.get_telegram")
    def test_task_no_notification_when_none_approved(
        self, mock_tg, mock_disc, reset_new_singletons
    ):
        """Should not send notification when no coins approved."""
        from src.tasks.portfolio_tasks import task_auto_discovery

        mock_disc.get_instance.return_value.run_discovery.return_value = {
            "candidates": 5,
            "evaluated": 5,
            "approved": 0,
            "added": 0,
            "errors": [],
        }

        task_auto_discovery()

        mock_tg.return_value.send.assert_not_called()
