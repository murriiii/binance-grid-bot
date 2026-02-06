"""Tests for src/notifications/ modules to increase coverage."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.api.http_client import HTTPClientError

# ═══════════════════════════════════════════════════════════════
# telegram_bot.py
# ═══════════════════════════════════════════════════════════════


class TestTelegramBot:
    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_message_success(self, mock_http):
        from src.notifications.telegram_bot import TelegramBot

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        bot = TelegramBot(token="test-token", chat_id="12345")
        result = bot.send_message("Hello")

        assert result is True
        mock_client.post.assert_called_once()

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_message_no_token(self, mock_http, monkeypatch):
        from src.notifications.telegram_bot import TelegramBot

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        bot = TelegramBot(token=None, chat_id="12345")
        bot.token = None  # Force override
        result = bot.send_message("Hello")

        assert result is False

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_message_failure(self, mock_http):
        from src.notifications.telegram_bot import TelegramBot

        mock_client = MagicMock()
        mock_client.post.side_effect = HTTPClientError("API error")
        mock_http.return_value = mock_client

        bot = TelegramBot(token="test-token", chat_id="12345")
        result = bot.send_message("Hello")

        assert result is False

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_photo_bytes(self, mock_http):
        from src.notifications.telegram_bot import TelegramBot

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        bot = TelegramBot(token="test-token", chat_id="12345")
        result = bot.send_photo(photo_bytes=b"fake_png_data", caption="Test")

        assert result is True

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_photo_no_token(self, mock_http):
        from src.notifications.telegram_bot import TelegramBot

        bot = TelegramBot(token="test-token", chat_id="12345")
        bot.token = None  # Force no token
        result = bot.send_photo(photo_bytes=b"data")

        assert result is False

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_document(self, mock_http):
        from src.notifications.telegram_bot import TelegramBot

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        bot = TelegramBot(token="test-token", chat_id="12345")

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            f.flush()
            result = bot.send_document(file_path=f.name)

        assert result is True


class TestTradingNotifier:
    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_trade_alert(self, mock_http):
        from src.notifications.telegram_bot import TradingNotifier

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        notifier = TradingNotifier()
        notifier.send_trade_alert(
            action="BUY",
            symbol="BTCUSDT",
            price=65000.0,
            quantity=0.01,
            reasoning="RSI oversold",
            portfolio_value=10000.0,
        )

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_daily_summary(self, mock_http):
        from src.notifications.telegram_bot import TradingNotifier

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        notifier = TradingNotifier()
        notifier.send_daily_summary(
            portfolio_value=10000.0,
            daily_pnl=150.0,
            daily_pnl_pct=1.5,
            positions={"BTCUSDT": 0.01},
            top_performer="SOL",
            worst_performer="DOGE",
            sentiment="Greed",
        )

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_sentiment_alert(self, mock_http):
        from src.notifications.telegram_bot import TradingNotifier

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        notifier = TradingNotifier()
        notifier.send_sentiment_alert(fear_greed=15, signal="STRONG_BUY", reasoning="Extreme Fear")

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_error_alert(self, mock_http):
        from src.notifications.telegram_bot import TradingNotifier

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        notifier = TradingNotifier()
        notifier.send_error_alert(error_type="API Error", details="Connection timeout")

    @patch("src.notifications.telegram_bot.get_http_client")
    def test_send_backtest_result(self, mock_http):
        from src.notifications.telegram_bot import TradingNotifier

        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}
        mock_http.return_value = mock_client

        notifier = TradingNotifier()
        notifier.send_backtest_result(
            initial=10000,
            final=12000,
            total_return=20.0,
            sharpe=1.5,
            max_drawdown=8.0,
            total_trades=50,
            win_rate=65.0,
        )


# ═══════════════════════════════════════════════════════════════
# charts.py
# ═══════════════════════════════════════════════════════════════


class TestCharts:
    def test_create_portfolio_chart(self):
        from src.notifications.charts import create_portfolio_chart

        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        df = pd.DataFrame(
            {"total_value": np.random.default_rng(42).uniform(9000, 11000, 30)}, index=dates
        )

        result = create_portfolio_chart(df)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_create_portfolio_chart_with_benchmark(self):
        from src.notifications.charts import create_portfolio_chart

        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        df = pd.DataFrame(
            {"total_value": np.random.default_rng(42).uniform(9000, 11000, 30)}, index=dates
        )
        bench = pd.DataFrame(
            {"value": np.random.default_rng(43).uniform(9000, 11000, 30)}, index=dates
        )

        result = create_portfolio_chart(df, benchmark_data=bench)
        assert isinstance(result, bytes)

    def test_create_allocation_pie(self):
        from src.notifications.charts import create_allocation_pie

        allocs = {"BTC": 5000, "ETH": 3000, "SOL": 1500, "USDT": 500}
        result = create_allocation_pie(allocs)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_create_trade_chart(self):
        from src.notifications.charts import create_trade_chart

        dates = pd.date_range("2025-01-01", periods=100, freq="h")
        prices = pd.Series(np.random.default_rng(42).uniform(60000, 70000, 100), index=dates)
        trades = [
            {"timestamp": dates[10], "type": "BUY", "price": 62000},
            {"timestamp": dates[50], "type": "SELL", "price": 68000},
        ]

        result = create_trade_chart(prices, trades, "BTCUSDT")
        assert isinstance(result, bytes)

    def test_create_fear_greed_gauge(self):
        from src.notifications.charts import create_fear_greed_gauge

        result = create_fear_greed_gauge(25)
        assert isinstance(result, bytes)

        result2 = create_fear_greed_gauge(75)
        assert isinstance(result2, bytes)

    def test_create_daily_summary_image(self):
        from src.notifications.charts import create_daily_summary_image

        result = create_daily_summary_image(
            portfolio_value=10000.0,
            daily_pnl=150.0,
            daily_pnl_pct=1.5,
            allocations={"BTC": 5000, "ETH": 3000},
            fear_greed=55,
        )
        assert isinstance(result, bytes)

    def test_create_daily_summary_image_with_history(self):
        from src.notifications.charts import create_daily_summary_image

        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        history = pd.DataFrame(
            {"total_value": np.random.default_rng(42).uniform(9000, 11000, 30)}, index=dates
        )

        result = create_daily_summary_image(
            portfolio_value=10000.0,
            daily_pnl=-50.0,
            daily_pnl_pct=-0.5,
            allocations={"BTC": 5000},
            fear_greed=30,
            portfolio_history=history,
        )
        assert isinstance(result, bytes)


# ═══════════════════════════════════════════════════════════════
# ai_assistant.py
# ═══════════════════════════════════════════════════════════════


class TestDeepSeekAssistant:
    @patch("src.notifications.ai_assistant.get_http_client")
    def test_ask(self, mock_http):
        from src.notifications.ai_assistant import DeepSeekAssistant

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "choices": [{"message": {"content": "BTC looks bullish"}}],
            "usage": {"total_tokens": 100},
        }
        mock_http.return_value = mock_client

        assistant = DeepSeekAssistant()
        result = assistant.ask("What about BTC?")

        assert "bullish" in result

    def test_ask_no_api_key(self):
        from src.notifications.ai_assistant import DeepSeekAssistant

        assistant = DeepSeekAssistant()
        assistant.api_key = None
        result = assistant.ask("Test")

        assert "nicht konfiguriert" in result

    @patch("src.notifications.ai_assistant.get_http_client")
    def test_ask_api_error(self, mock_http):
        from src.notifications.ai_assistant import DeepSeekAssistant

        mock_client = MagicMock()
        mock_client.post.side_effect = HTTPClientError("timeout")
        mock_http.return_value = mock_client

        assistant = DeepSeekAssistant()
        result = assistant.ask("Test")

        assert "Fehler" in result

    @patch("src.notifications.ai_assistant.get_http_client")
    def test_analyze_market(self, mock_http):
        from src.notifications.ai_assistant import DeepSeekAssistant

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "choices": [{"message": {"content": "Market analysis result"}}],
            "usage": {"total_tokens": 200},
        }
        mock_http.return_value = mock_client

        assistant = DeepSeekAssistant()
        result = assistant.analyze_market(
            fear_greed=25, trending=["BTC", "SOL"], prices={"BTCUSDT": 65000}
        )

        assert isinstance(result, str)

    def test_get_cost_estimate(self):
        from src.notifications.ai_assistant import DeepSeekAssistant

        assistant = DeepSeekAssistant()
        assistant.total_tokens_used = 50000

        result = assistant.get_cost_estimate()
        assert isinstance(result, str)

    def test_clear_history(self):
        from src.notifications.ai_assistant import DeepSeekAssistant

        assistant = DeepSeekAssistant()
        assistant.conversation_history = [{"role": "user", "content": "test"}]
        assistant.clear_history()

        assert len(assistant.conversation_history) == 0


class TestTelegramAIHandler:
    @patch("src.notifications.ai_assistant.get_http_client")
    def test_handle_ask_command(self, mock_http):
        from src.notifications.ai_assistant import TelegramAIHandler

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "choices": [{"message": {"content": "Answer"}}],
            "usage": {"total_tokens": 50},
        }
        mock_http.return_value = mock_client

        mock_bot = MagicMock()
        handler = TelegramAIHandler(mock_bot)
        result = handler.handle_message("/ask What is grid trading?")

        assert result is not None

    def test_handle_unknown_command(self):
        from src.notifications.ai_assistant import TelegramAIHandler

        mock_bot = MagicMock()
        handler = TelegramAIHandler(mock_bot)
        result = handler.handle_message("random text not a command")

        assert result is None

    def test_handle_aihelp(self):
        from src.notifications.ai_assistant import TelegramAIHandler

        mock_bot = MagicMock()
        handler = TelegramAIHandler(mock_bot)
        result = handler.handle_message("/aihelp")

        assert result is not None

    def test_handle_cost(self):
        from src.notifications.ai_assistant import TelegramAIHandler

        mock_bot = MagicMock()
        handler = TelegramAIHandler(mock_bot)
        result = handler.handle_message("/cost")

        assert result is not None

    def test_handle_clear(self):
        from src.notifications.ai_assistant import TelegramAIHandler

        mock_bot = MagicMock()
        handler = TelegramAIHandler(mock_bot)
        result = handler.handle_message("/clear")

        assert result is not None


# ═══════════════════════════════════════════════════════════════
# claude_assistant.py
# ═══════════════════════════════════════════════════════════════


class TestClaudeAssistant:
    @patch("src.notifications.claude_assistant.get_http_client")
    def test_ask(self, mock_http):
        from src.notifications.claude_assistant import ClaudeAssistant

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "content": [{"text": "Analysis result"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_http.return_value = mock_client

        assistant = ClaudeAssistant()
        assistant.api_key = "test-key"
        result = assistant.ask("What about BTC?")

        assert "Analysis result" in result

    def test_ask_no_key(self):
        from src.notifications.claude_assistant import ClaudeAssistant

        assistant = ClaudeAssistant()
        assistant.api_key = None
        result = assistant.ask("Test")

        assert "nicht konfiguriert" in result

    @patch("src.notifications.claude_assistant.get_http_client")
    def test_ask_api_error(self, mock_http):
        from src.notifications.claude_assistant import ClaudeAssistant

        mock_client = MagicMock()
        mock_client.post.side_effect = HTTPClientError("timeout")
        mock_http.return_value = mock_client

        assistant = ClaudeAssistant()
        assistant.api_key = "test-key"
        result = assistant.ask("Test")

        assert "Fehler" in result

    @patch("src.notifications.claude_assistant.get_http_client")
    def test_explain_trade(self, mock_http):
        from src.notifications.claude_assistant import ClaudeAssistant

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "content": [{"text": "Trade explanation"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_http.return_value = mock_client

        assistant = ClaudeAssistant()
        assistant.api_key = "test-key"
        result = assistant.explain_trade({"action": "BUY", "symbol": "BTC", "price": 65000})

        assert isinstance(result, str)


class TestTelegramClaudeHandler:
    def test_handle_ask(self):
        from src.notifications.claude_assistant import TelegramClaudeHandler

        mock_bot = MagicMock()
        mock_claude = MagicMock()
        mock_claude.ask.return_value = "Response"

        handler = TelegramClaudeHandler(mock_bot, mock_claude)
        result = handler.handle_message("/ask What is grid trading?")

        assert result == "Response"

    def test_handle_help(self):
        from src.notifications.claude_assistant import TelegramClaudeHandler

        mock_bot = MagicMock()
        mock_claude = MagicMock()
        handler = TelegramClaudeHandler(mock_bot, mock_claude)
        result = handler.handle_message("/help")

        assert result is not None

    def test_handle_unknown(self):
        from src.notifications.claude_assistant import TelegramClaudeHandler

        mock_bot = MagicMock()
        mock_claude = MagicMock()
        handler = TelegramClaudeHandler(mock_bot, mock_claude)
        result = handler.handle_message("random text")

        assert result is None

    def test_set_last_trade(self):
        from src.notifications.claude_assistant import TelegramClaudeHandler

        mock_bot = MagicMock()
        mock_claude = MagicMock()
        handler = TelegramClaudeHandler(mock_bot, mock_claude)
        handler.set_last_trade({"action": "BUY"})

        assert handler.last_trade == {"action": "BUY"}


class TestCostTracker:
    def test_add_usage_and_summary(self):
        from src.notifications.claude_assistant import CostTracker

        tracker = CostTracker()
        tracker.add_usage(1000, 500)
        tracker.add_usage(2000, 1000)

        assert tracker.total_input_tokens == 3000
        assert tracker.total_output_tokens == 1500
        assert tracker.total_cost > 0

        summary = tracker.get_summary()
        assert isinstance(summary, str)
