"""
Telegram Bot für Trading Notifications
Sendet Alerts, Reports und Charts

Setup:
1. Schreibe @BotFather auf Telegram
2. /newbot → Name und Username wählen
3. Du bekommst einen API Token
4. Schreibe deinem Bot eine Nachricht
5. Hole deine Chat-ID (siehe get_chat_id())
"""

import io
import logging
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trading_bot")


class TelegramBot:
    """
    Telegram Bot für Trading-Benachrichtigungen.

    Features:
    - Text-Nachrichten (Markdown formatiert)
    - Bilder/Charts senden
    - Dokumente (CSV, PDF)
    - Scheduled Reports (extern via cron/scheduler)
    """

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

        if not self.token:
            print("⚠️  TELEGRAM_BOT_TOKEN nicht gesetzt!")
        if not self.chat_id:
            print("⚠️  TELEGRAM_CHAT_ID nicht gesetzt!")

    def send_message(
        self, text: str, parse_mode: str = "Markdown", disable_notification: bool = False
    ) -> bool:
        """
        Sendet eine Text-Nachricht.

        Args:
            text: Nachricht (Markdown oder HTML)
            parse_mode: "Markdown" oder "HTML"
            disable_notification: Stumm senden
        """
        if not self.token or not self.chat_id:
            logger.debug(f"Telegram nicht konfiguriert, Nachricht übersprungen: {text[:100]}...")
            return False

        try:
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_notification": disable_notification,
                },
                timeout=10,
            )
            return response.json().get("ok", False)
        except Exception as e:
            print(f"Telegram Fehler: {e}")
            return False

    def send_photo(
        self, photo_path: str = None, photo_bytes: bytes = None, caption: str = None
    ) -> bool:
        """
        Sendet ein Bild/Chart.

        Args:
            photo_path: Pfad zur Bilddatei
            photo_bytes: Bild als Bytes (für matplotlib)
            caption: Bildunterschrift
        """
        if not self.token or not self.chat_id:
            logger.debug(f"Telegram nicht konfiguriert, Photo übersprungen: {caption}")
            return False

        try:
            if photo_path:
                with open(photo_path, "rb") as f:
                    files = {"photo": f}
                    data = {"chat_id": self.chat_id, "caption": caption}
                    response = requests.post(
                        f"{self.base_url}/sendPhoto", data=data, files=files, timeout=30
                    )
            elif photo_bytes:
                files = {"photo": ("chart.png", io.BytesIO(photo_bytes), "image/png")}
                data = {"chat_id": self.chat_id, "caption": caption}
                response = requests.post(
                    f"{self.base_url}/sendPhoto", data=data, files=files, timeout=30
                )
            else:
                return False

            return response.json().get("ok", False)
        except Exception as e:
            print(f"Telegram Photo Fehler: {e}")
            return False

    def send_document(self, file_path: str, caption: str = None) -> bool:
        """Sendet eine Datei (CSV, PDF, etc.)"""
        if not self.token or not self.chat_id:
            logger.debug(f"Telegram nicht konfiguriert, Dokument übersprungen: {file_path}")
            return False

        try:
            with open(file_path, "rb") as f:
                files = {"document": f}
                data = {"chat_id": self.chat_id, "caption": caption}
                response = requests.post(
                    f"{self.base_url}/sendDocument", data=data, files=files, timeout=30
                )
            return response.json().get("ok", False)
        except Exception as e:
            print(f"Telegram Document Fehler: {e}")
            return False

    def get_chat_id(self) -> None:
        """
        Hilfsfunktion um deine Chat-ID zu finden.

        1. Schreibe deinem Bot eine Nachricht
        2. Rufe diese Funktion auf
        3. Du siehst deine Chat-ID
        """
        if not self.token:
            print("Token nicht gesetzt!")
            return

        response = requests.get(f"{self.base_url}/getUpdates", timeout=10)
        data = response.json()

        if data.get("result"):
            for update in data["result"]:
                chat = update.get("message", {}).get("chat", {})
                print(f"Chat ID: {chat.get('id')}")
                print(f"Username: {chat.get('username')}")
                print(f"First Name: {chat.get('first_name')}")
        else:
            print("Keine Nachrichten gefunden. Schreibe erst deinem Bot!")


class TradingNotifier:
    """
    High-Level Notification Interface für Trading-Events.
    Formatiert Nachrichten schön für Telegram.
    """

    def __init__(self):
        self.bot = TelegramBot()

    def send_trade_alert(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: float,
        reasoning: str,
        portfolio_value: float,
    ):
        """Sendet Trade-Alert mit Begründung"""
        emoji = "🟢" if action == "BUY" else "🔴"

        message = f"""
{emoji} *TRADE EXECUTED*

*{action}* {symbol}
├ Preis: `${price:,.2f}`
├ Menge: `{quantity:.6f}`
└ Wert: `${price * quantity:,.2f}`

📊 *Portfolio:* `${portfolio_value:,.2f}`

💡 *Begründung:*
_{reasoning}_

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        self.bot.send_message(message)

    def send_daily_summary(
        self,
        portfolio_value: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        positions: dict[str, float],
        top_performer: str,
        worst_performer: str,
        sentiment: str,
    ):
        """Tägliche Portfolio-Zusammenfassung"""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        pnl_sign = "+" if daily_pnl >= 0 else ""

        positions_str = "\n".join(
            [
                f"├ {symbol}: `{value:.2f}%`"
                for symbol, value in sorted(positions.items(), key=lambda x: -x[1])[:5]
            ]
        )

        message = f"""
{pnl_emoji} *TAGES-REPORT* {datetime.now().strftime("%Y-%m-%d")}

💰 *Portfolio:* `${portfolio_value:,.2f}`
{pnl_emoji} *Heute:* `{pnl_sign}${daily_pnl:,.2f}` ({pnl_sign}{daily_pnl_pct:.2f}%)

📊 *Top Positionen:*
{positions_str}

🏆 *Top:* {top_performer}
😢 *Flop:* {worst_performer}

🧠 *Markt-Sentiment:* {sentiment}
"""
        self.bot.send_message(message)

    def send_sentiment_alert(self, fear_greed: int, signal: str, reasoning: str):
        """Sentiment-Warnung bei extremen Werten"""
        if fear_greed < 25:
            emoji = "😱"
            level = "EXTREME FEAR"
        elif fear_greed < 40:
            emoji = "😰"
            level = "FEAR"
        elif fear_greed > 75:
            emoji = "🤑"
            level = "EXTREME GREED"
        elif fear_greed > 60:
            emoji = "😀"
            level = "GREED"
        else:
            emoji = "😐"
            level = "NEUTRAL"

        message = f"""
{emoji} *SENTIMENT ALERT*

Fear & Greed Index: *{fear_greed}* ({level})

Signal: *{signal}*

💡 _{reasoning}_

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        self.bot.send_message(message)

    def send_error_alert(self, error_type: str, details: str):
        """Fehler-Benachrichtigung"""
        message = f"""
🚨 *ERROR ALERT*

Type: `{error_type}`
Details: `{details}`

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        self.bot.send_message(message)

    def send_backtest_result(
        self,
        initial: float,
        final: float,
        total_return: float,
        sharpe: float,
        max_drawdown: float,
        total_trades: int,
        win_rate: float,
    ):
        """Backtest-Ergebnis"""
        emoji = "✅" if total_return > 0 else "❌"

        message = f"""
{emoji} *BACKTEST ABGESCHLOSSEN*

💰 *Performance:*
├ Start: `${initial:,.2f}`
├ Ende: `${final:,.2f}`
├ Return: `{total_return * 100:+.2f}%`
├ Sharpe: `{sharpe:.2f}`
└ Max DD: `{max_drawdown * 100:.2f}%`

📊 *Trades:*
├ Anzahl: `{total_trades}`
└ Win-Rate: `{win_rate * 100:.1f}%`

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        self.bot.send_message(message)


if __name__ == "__main__":
    # Test
    bot = TelegramBot()

    print("Suche nach Chat-ID...")
    bot.get_chat_id()

    print("\nSende Test-Nachricht...")
    bot.send_message("🤖 *Test* vom Trading Bot!\n\nAlles funktioniert.")
