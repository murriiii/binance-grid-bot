"""
Tests für src/notifications/telegram_service.py
"""

from unittest.mock import patch


class TestTelegramService:
    """Tests für TelegramService"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Testet Singleton-Pattern"""
        from src.notifications.telegram_service import TelegramService, get_telegram

        service1 = get_telegram()
        service2 = get_telegram()
        service3 = TelegramService.get_instance()

        assert service1 is service2
        assert service2 is service3

    def test_disabled_without_credentials(self, reset_new_singletons, monkeypatch):
        """Testet dass Service deaktiviert ist ohne Credentials"""
        from src.notifications.telegram_service import TelegramService

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        TelegramService._instance = None
        service = TelegramService()

        assert service.enabled is False

    def test_enabled_with_credentials(self, reset_new_singletons):
        """Testet dass Service aktiviert ist mit Credentials"""
        from src.notifications.telegram_service import TelegramService

        TelegramService._instance = None
        service = TelegramService()

        assert service.enabled is True
        assert service.token == "test_token"
        assert service.chat_id == "123456789"

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_message(self, mock_post, reset_new_singletons):
        """Testet Nachrichtenversand"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send("Test message")

        assert result is True
        mock_post.assert_called_once()

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_returns_false_on_error(self, mock_post, reset_new_singletons):
        """Testet False bei Fehler"""
        from src.api.http_client import HTTPClientError
        from src.notifications.telegram_service import get_telegram

        mock_post.side_effect = HTTPClientError("API Error")

        service = get_telegram()
        result = service.send("Test message")

        assert result is False

    def test_send_returns_false_when_disabled(self, reset_new_singletons, monkeypatch):
        """Testet False wenn deaktiviert"""
        from src.notifications.telegram_service import TelegramService

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        TelegramService._instance = None
        service = TelegramService()
        result = service.send("Test message")

        assert result is False

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_urgent(self, mock_post, reset_new_singletons):
        """Testet dringende Nachricht"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_urgent("Alert!")

        assert result is True
        # Prüfe dass URGENT im Text ist
        call_args = mock_post.call_args
        assert "URGENT" in str(call_args)

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_trade_alert(self, mock_post, reset_new_singletons):
        """Testet Trade-Alert"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_trade_alert(
            trade_type="BUY", symbol="BTCUSDT", price=42500.0, quantity=0.001, profit_loss=2.5
        )

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_daily_summary(self, mock_post, reset_new_singletons):
        """Testet Daily Summary"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_daily_summary(
            portfolio_value=1000.0, daily_change=2.5, trades_today=5, win_rate=80.0, fear_greed=45
        )

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_stop_loss_alert(self, mock_post, reset_new_singletons):
        """Testet Stop-Loss Alert"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_stop_loss_alert(
            symbol="BTCUSDT", trigger_price=40000.0, stop_price=39000.0, quantity=0.01
        )

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_whale_alert(self, mock_post, reset_new_singletons):
        """Testet Whale Alert"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_whale_alert(
            symbol="BTC",
            amount=1000.0,
            amount_usd=42500000.0,
            direction="BULLISH",
            from_owner="Binance",
            to_owner="Unknown",
        )

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_sentiment_alert_extreme_fear(self, mock_post, reset_new_singletons):
        """Testet Sentiment Alert bei Extreme Fear"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_sentiment_alert(15, "Extreme Fear")

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_sentiment_alert_extreme_greed(self, mock_post, reset_new_singletons):
        """Testet Sentiment Alert bei Extreme Greed"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_sentiment_alert(85, "Extreme Greed")

        assert result is True

    def test_send_sentiment_alert_normal_returns_false(self, reset_new_singletons):
        """Testet dass normales Sentiment keinen Alert sendet"""
        from src.notifications.telegram_service import get_telegram

        service = get_telegram()
        result = service.send_sentiment_alert(50, "Neutral")

        assert result is False

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_error(self, mock_post, reset_new_singletons):
        """Testet Error-Nachricht"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_error("Something went wrong", context="test_function")

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_startup(self, mock_post, reset_new_singletons):
        """Testet Startup-Nachricht"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_startup(mode="TESTNET", symbol="BTCUSDT", investment=100.0)

        assert result is True

    @patch("src.api.http_client.HTTPClient.post")
    def test_send_shutdown(self, mock_post, reset_new_singletons):
        """Testet Shutdown-Nachricht"""
        from src.notifications.telegram_service import get_telegram

        mock_post.return_value = {"ok": True}

        service = get_telegram()
        result = service.send_shutdown(reason="User requested")

        assert result is True
