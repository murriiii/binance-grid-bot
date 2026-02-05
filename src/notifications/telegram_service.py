"""
Zentraler Telegram Service für alle Benachrichtigungen.
Ersetzt alle verstreuten Telegram-Implementierungen.
"""

import io
import logging
import os
from datetime import datetime
from typing import Optional

from src.api.http_client import HTTPClientError, get_http_client

logger = logging.getLogger("trading_bot")


class TelegramService:
    """
    Zentraler Service für alle Telegram-Benachrichtigungen.

    Features:
    - Einheitliche API für alle Module
    - Automatische Fehlerbehandlung
    - Message Rate Limiting
    - Photo/Chart Support

    Usage:
        telegram = TelegramService.get_instance()
        telegram.send("Hello World")
        telegram.send_urgent("Alert!")
    """

    _instance: Optional["TelegramService"] = None

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        self.http = get_http_client()

        if not self.enabled:
            logger.warning("Telegram Service nicht konfiguriert (Token oder Chat-ID fehlt)")

    @classmethod
    def get_instance(cls) -> "TelegramService":
        """Singleton-Instanz"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def send(
        self, message: str, parse_mode: str = "HTML", disable_notification: bool = False
    ) -> bool:
        """
        Sendet eine Nachricht.

        Args:
            message: Nachrichtentext (HTML oder Markdown)
            parse_mode: 'HTML' oder 'Markdown'
            disable_notification: True für stille Nachricht

        Returns:
            True wenn erfolgreich
        """
        if not self.enabled:
            return False

        try:
            self.http.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_notification": disable_notification,
                },
                api_type="telegram",
            )
            return True
        except HTTPClientError as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def send_urgent(self, message: str) -> bool:
        """Sendet eine dringende Nachricht mit Prefix"""
        return self.send(f"🚨 <b>URGENT</b>\n\n{message}")

    def send_trade_alert(
        self,
        trade_type: str,
        symbol: str,
        price: float,
        quantity: float,
        profit_loss: float | None = None,
    ) -> bool:
        """Sendet eine formatierte Trade-Benachrichtigung"""
        emoji = "🟢" if trade_type == "BUY" else "🔴"
        pnl_text = f"\nP/L: {profit_loss:+.2f}%" if profit_loss is not None else ""

        message = f"""
{emoji} <b>ORDER FILLED</b>

Type: {trade_type}
Symbol: {symbol}
Price: ${price:,.2f}
Quantity: {quantity}{pnl_text}
"""
        return self.send(message)

    def send_daily_summary(
        self,
        portfolio_value: float,
        daily_change: float,
        trades_today: int,
        win_rate: float,
        fear_greed: int,
    ) -> bool:
        """Sendet den täglichen Report"""
        trend = "Bullish" if fear_greed > 50 else "Bearish" if fear_greed < 30 else "Neutral"

        message = f"""
📊 <b>TAGES-REPORT</b> {datetime.now().strftime("%Y-%m-%d")}

💰 <b>Portfolio:</b> <code>${portfolio_value:.2f}</code>
📈 <b>Heute:</b> <code>{daily_change:+.2f}%</code>

<b>Trades heute:</b> {trades_today}
<b>Win Rate:</b> {win_rate:.0f}%

<b>Markt:</b>
├ Fear & Greed: {fear_greed}
└ Trend: {trend}

<i>Gute Nacht!</i> 🌙
"""
        return self.send(message, disable_notification=True)

    def send_stop_loss_alert(
        self, symbol: str, trigger_price: float, stop_price: float, quantity: float
    ) -> bool:
        """Sendet Stop-Loss Warnung"""
        message = f"""
🛑 <b>STOP-LOSS TRIGGERED</b>

Symbol: {symbol}
Preis: ${trigger_price:,.2f}
Stop: ${stop_price:,.2f}
Menge: {quantity}
"""
        return self.send_urgent(message)

    def send_whale_alert(
        self,
        symbol: str,
        amount: float,
        amount_usd: float,
        direction: str,
        from_owner: str,
        to_owner: str,
    ) -> bool:
        """Sendet Whale-Alert"""
        emoji = "🔴🐋" if direction == "BEARISH" else "🟢🐋" if direction == "BULLISH" else "🐋"

        message = f"""
{emoji} <b>WHALE ALERT</b>

{amount:,.0f} {symbol} (${amount_usd:,.0f})

From: <code>{from_owner}</code>
To: <code>{to_owner}</code>

Impact: <b>{direction}</b>
"""
        return self.send(message)

    def send_macro_alert(self, events: list) -> bool:
        """Sendet Makro-Event Warnung"""
        event_list = "\n".join([f"• {e['date']}: {e['name']}" for e in events[:5]])

        message = f"""
⚠️ <b>MACRO ALERT</b>

Wichtige Events in den nächsten 48h:

{event_list}

<i>Erhöhte Volatilität möglich.</i>
"""
        return self.send(message)

    def send_sentiment_alert(self, value: int, classification: str) -> bool:
        """Sendet Sentiment-Warnung bei Extremen"""
        if value <= 20:
            emoji = "🟢"
            title = "EXTREME FEAR ALERT"
            advice = "Historisch sind Werte unter 20 oft gute Kaufgelegenheiten."
        elif value >= 80:
            emoji = "🔴"
            title = "EXTREME GREED ALERT"
            advice = "Historisch sind Werte über 80 oft Warnsignale."
        else:
            return False  # Kein Alert bei normalem Sentiment

        message = f"""
{emoji} <b>{title}</b>

Fear & Greed Index: <code>{value}</code> ({classification})

{advice}
"""
        return self.send(message)

    def send_photo(self, photo_bytes: bytes, caption: str | None = None) -> bool:
        """Sendet ein Foto/Chart"""
        if not self.enabled:
            return False

        try:
            import requests

            files = {"photo": ("chart.png", io.BytesIO(photo_bytes), "image/png")}
            data = {"chat_id": self.chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"

            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendPhoto",
                data=data,
                files=files,
                timeout=30,
            )
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Telegram photo error: {e}")
            return False

    def send_error(self, error_message: str, context: str = "") -> bool:
        """Sendet Fehlermeldung"""
        message = f"""
❌ <b>ERROR</b>

{error_message}
"""
        if context:
            message += f"\n<i>Context: {context}</i>"

        return self.send(message)

    def send_startup(self, mode: str, symbol: str, investment: float) -> bool:
        """Sendet Startup-Nachricht"""
        message = f"""
🤖 <b>Trading Bot gestartet</b>

Mode: {mode}
Symbol: {symbol}
Investment: ${investment:.2f}
"""
        return self.send(message)

    def send_shutdown(self, reason: str = "") -> bool:
        """Sendet Shutdown-Nachricht"""
        message = "🛑 <b>Trading Bot gestoppt</b>"
        if reason:
            message += f"\n\nGrund: {reason}"
        return self.send(message)


# Convenience-Funktion für schnellen Zugriff
def get_telegram() -> TelegramService:
    """Gibt die globale TelegramService-Instanz zurück"""
    return TelegramService.get_instance()
