"""
Claude Assistant für Telegram
Beantwortet Fragen zu Trading, Portfolio, Strategien

Benötigt: ANTHROPIC_API_KEY in .env

Kosten: ~$3 pro 1M Input Tokens, ~$15 pro 1M Output Tokens (Sonnet)
Bei normaler Nutzung: ~$0.01-0.05 pro Frage
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


class ClaudeAssistant:
    """
    Claude Sonnet Integration für Trading-Fragen.

    Features:
    - Beantwortet Fragen zu deinem Portfolio
    - Erklärt Trading-Konzepte
    - Analysiert Markt-Situationen
    - Hat Kontext über deinen Bot
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-20250514"

    # System-Prompt mit Trading-Kontext
    SYSTEM_PROMPT = """Du bist ein Trading-Assistent für einen Krypto-Portfolio-Bot.

Der Bot nutzt:
- Markowitz Mean-Variance Optimierung für Asset-Allokation
- Dynamische Risiko-Skalierung (mehr Risiko bei kleinem Portfolio)
- Fear & Greed Index + CoinGecko Sentiment
- Fokus auf Altcoins (SOL, ARB, AVAX, etc.)

Der Nutzer ist Wirtschaftsmathematiker und versteht mathematische Konzepte.

Antworte präzise und technisch. Nutze Formeln wenn sinnvoll.
Antworte auf Deutsch."""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print("⚠️  ANTHROPIC_API_KEY nicht gesetzt - Claude deaktiviert")

    def ask(self, question: str, context: str | None = None, max_tokens: int = 1024) -> str:
        """
        Stelle eine Frage an Claude.

        Args:
            question: Die Frage
            context: Optionaler Kontext (z.B. aktuelles Portfolio)
            max_tokens: Max Antwortlänge

        Returns:
            Antwort als String
        """
        if not self.api_key:
            return "❌ Claude API nicht konfiguriert. Füge ANTHROPIC_API_KEY zur .env hinzu."

        # Baue die Nachricht
        user_message = question
        if context:
            user_message = f"Kontext:\n{context}\n\nFrage: {question}"

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.MODEL,
                    "max_tokens": max_tokens,
                    "system": self.SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_message}],
                },
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()["content"][0]["text"]
            else:
                return f"❌ API Fehler: {response.status_code} - {response.text}"

        except Exception as e:
            return f"❌ Fehler: {e!s}"

    def explain_trade(self, trade_info: dict) -> str:
        """Erklärt einen Trade im Detail"""
        context = f"""
Trade Info:
- Aktion: {trade_info.get("action")}
- Symbol: {trade_info.get("symbol")}
- Preis: ${trade_info.get("price")}
- Menge: {trade_info.get("quantity")}
- Automatische Begründung: {trade_info.get("reasoning")}
"""
        return self.ask(
            "Erkläre diesen Trade ausführlicher. Warum ist das mathematisch sinnvoll?",
            context=context,
        )

    def analyze_portfolio(self, portfolio: dict, prices: dict) -> str:
        """Analysiert das aktuelle Portfolio"""
        context = f"""
Portfolio-Positionen: {portfolio}
Aktuelle Preise: {prices}
"""
        return self.ask(
            "Analysiere dieses Portfolio. Ist die Diversifikation gut? "
            "Welche Risiken siehst du? Was würdest du ändern?",
            context=context,
        )


class TelegramClaudeHandler:
    """
    Verarbeitet /ask Befehle in Telegram.

    Usage in Telegram:
    /ask Was ist die Sharpe Ratio?
    /ask Warum ist SOL gerade übergewichtet?
    /explain (nach einem Trade)
    """

    def __init__(self, telegram_bot, claude: ClaudeAssistant):
        self.telegram = telegram_bot
        self.claude = claude
        self.last_trade = None  # Speichert letzten Trade für /explain

    def handle_message(self, text: str) -> str | None:
        """
        Verarbeitet eingehende Telegram-Nachrichten.

        Returns:
            Antwort oder None wenn nicht relevant
        """
        if text.startswith("/ask "):
            question = text[5:].strip()
            if question:
                return self.claude.ask(question)
            return "Usage: /ask <deine Frage>"

        elif text.startswith("/explain"):
            if self.last_trade:
                return self.claude.explain_trade(self.last_trade)
            return "Kein Trade zum Erklären. Warte auf den nächsten Trade."

        elif text.startswith("/help"):
            return """🤖 *Claude Assistant Befehle*

/ask <frage> - Stelle eine Frage zu Trading/Portfolio
/explain - Erkläre den letzten Trade im Detail
/status - Zeige Portfolio-Status
/sentiment - Aktuelles Markt-Sentiment

Beispiele:
• /ask Was ist die Sharpe Ratio?
• /ask Warum Altcoins bei kleinem Portfolio?
• /ask Erkläre Markowitz Optimierung"""

        return None

    def set_last_trade(self, trade: dict):
        """Speichert letzten Trade für /explain"""
        self.last_trade = trade


# Kosten-Tracker
class CostTracker:
    """Trackt API-Kosten"""

    # Sonnet Preise (Stand 2024)
    INPUT_COST_PER_1M = 3.00  # $3 pro 1M Input Tokens
    OUTPUT_COST_PER_1M = 15.00  # $15 pro 1M Output Tokens

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def add_usage(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    @property
    def total_cost(self) -> float:
        input_cost = (self.total_input_tokens / 1_000_000) * self.INPUT_COST_PER_1M
        output_cost = (self.total_output_tokens / 1_000_000) * self.OUTPUT_COST_PER_1M
        return input_cost + output_cost

    def get_summary(self) -> str:
        return f"""
📊 Claude API Kosten:
├ Input: {self.total_input_tokens:,} Tokens
├ Output: {self.total_output_tokens:,} Tokens
└ Gesamt: ${self.total_cost:.4f}
"""
