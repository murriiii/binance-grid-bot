"""
AI Assistant für Telegram (DeepSeek)
Viel günstiger als Claude/GPT - perfekt für Trading-Bot

DeepSeek Preise (Stand 2024):
- Input: $0.14 pro 1M Tokens (vs $3 bei Claude)
- Output: $0.28 pro 1M Tokens (vs $15 bei Claude)
= ca. 20-50x günstiger!

Das macht professionelle AI-Features auch bei kleinem Portfolio sinnvoll.
"""

import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()


class DeepSeekAssistant:
    """
    DeepSeek Integration für Trading-Fragen und Analyse.

    Günstig genug für:
    - Jede Trade-Begründung erweitern
    - Tägliche Markt-Analyse
    - News-Zusammenfassungen
    - Beliebig viele Fragen
    """

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"  # Oder "deepseek-coder" für technische Fragen

    SYSTEM_PROMPT = """Du bist ein professioneller Trading-Assistent für einen Krypto-Portfolio-Bot.

Der Bot nutzt:
- Markowitz Mean-Variance Optimierung für Asset-Allokation
- Dynamische Risiko-Skalierung (aggressiv bei kleinem Portfolio, konservativ bei großem)
- Fear & Greed Index + CoinGecko Social Sentiment
- Fokus auf Altcoins: SOL, ARB, AVAX, OP, INJ, LINK, etc.
- Kelly Criterion für Positionsgrößen
- Wöchentliches Rebalancing

Der Nutzer hat Wirtschaftsmathematik studiert und versteht:
- Portfolio-Theorie, Markowitz, Efficient Frontier
- Stochastik, Wahrscheinlichkeitstheorie
- Optimierungsverfahren

Antworte präzise, technisch und auf Deutsch.
Nutze mathematische Notation wenn sinnvoll (LaTeX-Style).
Sei direkt - keine Floskeln."""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.conversation_history: list[dict] = []
        self.total_tokens_used = 0

        if not self.api_key:
            print("⚠️  DEEPSEEK_API_KEY nicht gesetzt")

    def ask(
        self,
        question: str,
        context: str | None = None,
        max_tokens: int = 1024,
        keep_history: bool = False,
    ) -> str:
        """
        Stelle eine Frage an DeepSeek.

        Args:
            question: Die Frage
            context: Optionaler Kontext
            max_tokens: Max Antwortlänge
            keep_history: Konversation merken für Follow-ups

        Returns:
            Antwort als String
        """
        if not self.api_key:
            return "❌ DeepSeek API nicht konfiguriert. Füge DEEPSEEK_API_KEY zur .env hinzu."

        # Baue Nachricht
        user_content = question
        if context:
            user_content = f"Kontext:\n{context}\n\nFrage: {question}"

        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        if keep_history:
            messages.extend(self.conversation_history)

        messages.append({"role": "user", "content": user_content})

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]

                # Token-Tracking
                usage = data.get("usage", {})
                self.total_tokens_used += usage.get("total_tokens", 0)

                # History speichern
                if keep_history:
                    self.conversation_history.append({"role": "user", "content": user_content})
                    self.conversation_history.append({"role": "assistant", "content": answer})

                return answer
            else:
                return f"❌ API Fehler: {response.status_code} - {response.text}"

        except Exception as e:
            return f"❌ Fehler: {e!s}"

    def clear_history(self):
        """Löscht Konversations-History"""
        self.conversation_history = []

    def analyze_market(self, fear_greed: int, trending: list[str], prices: dict) -> str:
        """Tägliche Markt-Analyse"""
        context = f"""
Aktuelle Marktdaten:
- Fear & Greed Index: {fear_greed}
- Trending Coins: {", ".join(trending)}
- Preise (24h): {prices}
Datum: {datetime.now().strftime("%Y-%m-%d")}
"""
        return self.ask(
            "Erstelle eine kurze Markt-Analyse. Was bedeutet der aktuelle Fear&Greed? "
            "Welche Chancen/Risiken siehst du? Max 150 Wörter.",
            context=context,
            max_tokens=500,
        )

    def enhance_trade_reasoning(self, trade: dict, portfolio_context: str) -> str:
        """Erweitert die automatische Trade-Begründung"""
        context = f"""
Trade:
- Aktion: {trade.get("action")}
- Asset: {trade.get("symbol")}
- Preis: ${trade.get("price")}
- Wert: ${trade.get("value")}
- Auto-Begründung: {trade.get("reasoning")}

Portfolio-Kontext:
{portfolio_context}
"""
        return self.ask(
            "Erkläre diesen Trade verständlich in 2-3 Sätzen. "
            "Warum ist das mathematisch/strategisch sinnvoll?",
            context=context,
            max_tokens=300,
        )

    def explain_concept(self, concept: str) -> str:
        """Erklärt ein Trading/Mathe-Konzept"""
        return self.ask(
            f"Erkläre das Konzept '{concept}' im Kontext von Krypto-Trading. "
            "Nutze mathematische Notation wo sinnvoll. "
            "Gib ein praktisches Beispiel.",
            max_tokens=800,
        )

    def analyze_coin(self, symbol: str, price_history: str, social_data: str) -> str:
        """Analysiert einen spezifischen Coin"""
        context = f"""
Coin: {symbol}
Preis-Entwicklung (7 Tage): {price_history}
Social Daten: {social_data}
"""
        return self.ask(
            f"Analysiere {symbol}. Stärken, Schwächen, aktuelles Momentum? "
            "Sollte der Bot die Position erhöhen/reduzieren?",
            context=context,
            max_tokens=500,
        )

    def get_cost_estimate(self) -> str:
        """Zeigt geschätzte Kosten"""
        # DeepSeek Preise
        input_cost = (self.total_tokens_used * 0.5 / 1_000_000) * 0.14
        output_cost = (self.total_tokens_used * 0.5 / 1_000_000) * 0.28
        total = input_cost + output_cost

        return f"""
📊 DeepSeek API Nutzung:
├ Tokens: {self.total_tokens_used:,}
└ Geschätzte Kosten: ${total:.4f}

💡 Bei DeepSeek-Preisen:
   ~7.000 Fragen = $1
"""


class TelegramAIHandler:
    """
    Verarbeitet AI-Befehle in Telegram.

    Befehle:
    /ask <frage> - Beliebige Frage
    /market - Tägliche Markt-Analyse
    /explain <konzept> - Erkläre ein Konzept
    /coin <symbol> - Analysiere einen Coin
    /cost - Zeige API-Kosten
    """

    def __init__(self, telegram_bot):
        self.telegram = telegram_bot
        self.ai = DeepSeekAssistant()
        self.last_trade = None

    def handle_message(self, text: str, context: dict = None) -> str | None:
        """Verarbeitet Telegram-Nachrichten"""

        text = text.strip()

        if text.startswith("/ask "):
            question = text[5:].strip()
            return self.ai.ask(question, keep_history=True)

        elif text.startswith("/market"):
            fg = context.get("fear_greed", 50) if context else 50
            trending = context.get("trending", []) if context else []
            prices = context.get("prices", {}) if context else {}
            return self.ai.analyze_market(fg, trending, prices)

        elif text.startswith("/explain "):
            concept = text[9:].strip()
            return self.ai.explain_concept(concept)

        elif text.startswith("/coin "):
            symbol = text[6:].strip().upper()
            return self.ai.analyze_coin(symbol, "N/A", "N/A")

        elif text.startswith("/cost"):
            return self.ai.get_cost_estimate()

        elif text.startswith("/clear"):
            self.ai.clear_history()
            return "✅ Konversations-History gelöscht."

        elif text.startswith("/aihelp"):
            return """🤖 *AI Assistant Befehle*

/ask <frage> - Stelle eine beliebige Frage
/market - Aktuelle Markt-Analyse
/explain <konzept> - Erkläre Trading-Konzept
/coin <symbol> - Analysiere einen Coin
/cost - Zeige API-Kosten
/clear - Lösche Chat-History

*Beispiele:*
• /ask Warum ist Rebalancing wichtig?
• /explain Sharpe Ratio
• /explain Kelly Criterion
• /coin SOL
• /ask Was bedeutet ein Fear&Greed von 23?"""

        return None

    def enhance_and_send_trade(self, trade: dict, portfolio_context: str):
        """Erweitert Trade-Begründung mit AI und sendet via Telegram"""
        # Erweiterte Begründung holen
        enhanced = self.ai.enhance_trade_reasoning(trade, portfolio_context)

        emoji = "🟢" if trade["action"] == "BUY" else "🔴"

        message = f"""
{emoji} *TRADE EXECUTED*

*{trade["action"]}* {trade["symbol"]}
├ Preis: `${trade["price"]:,.2f}`
├ Menge: `{trade["quantity"]:.6f}`
└ Wert: `${trade["value"]:,.2f}`

💡 *Begründung:*
_{enhanced}_

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        self.telegram.send_message(message)
