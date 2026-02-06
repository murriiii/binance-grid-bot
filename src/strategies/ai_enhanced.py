"""
AI-Enhanced Trading Strategy
Nutzt DeepSeek für professionellere Entscheidungen

Was AI hier macht:
1. News-Analyse → Trading-Signale
2. Sentiment-Interpretation → Timing
3. Anomalie-Erklärung → Risiko-Management
4. Multi-Faktor-Reasoning → Bessere Entscheidungen

Was AI NICHT macht:
- Preise vorhersagen (LLMs können das nicht zuverlässig)
- High-Frequency Trading (zu langsam)
- Order Flow analysieren (braucht andere Daten)
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from src.api.http_client import HTTPClientError, get_http_client

logger = logging.getLogger("trading_bot")


@dataclass
class AISignal:
    """AI-generiertes Trading-Signal"""

    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Ausführliche Begründung
    action: str  # "BUY", "SELL", "HOLD", "REDUCE"
    affected_assets: list[str]
    risk_level: str  # "LOW", "MEDIUM", "HIGH"


class AITradingEnhancer:
    """
    Nutzt DeepSeek um Trading-Entscheidungen zu verbessern.

    WICHTIG: AI ersetzt nicht die mathematischen Modelle!
    AI ist ein FILTER/ENHANCER oben drauf:

    Mathematik (Markowitz, Sharpe) → Basis-Entscheidung
                    ↓
    AI-Filter (News, Sentiment) → Verfeinerte Entscheidung
                    ↓
    Risiko-Check → Finale Entscheidung
    """

    API_URL = "https://api.deepseek.com/v1/chat/completions"

    ANALYSIS_PROMPT_BASE = """Du bist ein quantitativer Trading-Analyst mit EIGENEM ERFAHRUNGSGEDÄCHTNIS.

Du hast Zugang zu einem "Trading Playbook" - das sind DEINE gelernten Regeln aus vergangenen Trades.
NUTZE dieses Wissen aktiv bei deinen Entscheidungen!

Deine Aufgabe: Analysiere die gegebenen Informationen und gib ein strukturiertes Signal.

WICHTIG:
- BEACHTE die Regeln aus deinem Playbook (unten angefügt)
- Wenn das Playbook sagt "vermeide X" - dann vermeide es!
- Wenn das Playbook zeigt dass etwas gut funktioniert hat - bevorzuge es!
- Sei konservativ mit Vorhersagen
- Wenn unsicher, sage "NEUTRAL"
- Begründe IMMER mit konkreten Fakten UND Playbook-Referenzen

Antworte IMMER in diesem JSON-Format:
{
    "direction": "BULLISH/BEARISH/NEUTRAL",
    "confidence": 0.0-1.0,
    "action": "BUY/SELL/HOLD/REDUCE",
    "affected_assets": ["BTC", "SOL", ...],
    "risk_level": "LOW/MEDIUM/HIGH",
    "reasoning": "Deine Begründung hier",
    "playbook_alignment": "Wie passt diese Entscheidung zu meinem Playbook?"
}"""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.last_error_time: datetime | None = None
        self.consecutive_errors = 0
        self.playbook = None
        self._init_playbook()

    def _init_playbook(self):
        """Initialisiert das Playbook für Kontext-Anreicherung"""
        try:
            from src.data.playbook import get_playbook

            self.playbook = get_playbook()
            logger.info("Playbook für AI-Enhancement geladen")
        except Exception as e:
            logger.warning(f"Playbook konnte nicht geladen werden: {e}")
            self.playbook = None

    def _get_system_prompt(self) -> str:
        """Generiert den System-Prompt inklusive Playbook"""
        prompt = self.ANALYSIS_PROMPT_BASE

        if self.playbook:
            playbook_context = self.playbook.get_playbook_for_prompt()
            prompt += f"\n\n{playbook_context}"

        return prompt

    def _get_fallback_response(self, reason: str) -> str:
        """Sichere Fallback-Response wenn API nicht verfügbar"""
        return f'{{"direction": "NEUTRAL", "confidence": 0.0, "action": "HOLD", "affected_assets": [], "risk_level": "HIGH", "reasoning": "Fallback: {reason}"}}'

    def _call_api(self, user_prompt: str) -> str:
        """
        API-Call zu DeepSeek mit Retry-Logik und Fallbacks.

        HTTPClient übernimmt:
        - 3 Retries mit exponentieller Verzögerung
        - 30 Sekunden Timeout (deepseek api_type)
        - Rate Limit Handling (429)
        """
        if not self.api_key:
            return self._get_fallback_response("API nicht konfiguriert")

        try:
            http = get_http_client()
            data = http.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 800,  # Erhöht für Playbook-Referenzen
                    "temperature": 0.3,  # Niedrig für konsistentere Outputs
                },
                api_type="deepseek",
            )

            self.consecutive_errors = 0
            return data["choices"][0]["message"]["content"]

        except HTTPClientError as e:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            logger.warning(f"DeepSeek API error: {e}")
            return self._get_fallback_response(f"API nicht erreichbar: {e}")

    def is_api_healthy(self) -> bool:
        """Prüft ob die API kürzlich funktioniert hat"""
        if self.consecutive_errors >= 3:
            return False
        if self.last_error_time:
            # Wenn letzter Fehler < 5 Minuten her, als unhealthy markieren
            minutes_since_error = (datetime.now() - self.last_error_time).total_seconds() / 60
            if minutes_since_error < 5:
                return False
        return True

    def analyze_news(self, news_items: list[dict]) -> AISignal:
        """
        Analysiert Krypto-News und leitet Signale ab.

        Input: Liste von News mit 'title', 'summary', 'source', 'timestamp'
        Output: Trading-Signal
        """
        news_text = "\n".join(
            [
                f"- [{n.get('source', 'Unknown')}] {n.get('title', '')}: {n.get('summary', '')}"
                for n in news_items[:10]  # Max 10 News
            ]
        )

        prompt = f"""Analysiere diese Krypto-News und gib ein Trading-Signal:

NEWS:
{news_text}

Beachte:
- Regulatorische News haben großen Impact
- Hack/Exploit News sind sehr bearish
- Partnership News sind oft schon eingepreist
- Beachte welche spezifischen Coins betroffen sind
"""
        result = self._call_api(prompt)
        return self._parse_signal(result)

    def analyze_sentiment_context(
        self,
        fear_greed: int,
        social_volume: dict[str, float],
        trending_coins: list[str],
        portfolio_positions: dict[str, float],
    ) -> AISignal:
        """
        Interpretiert Sentiment-Daten im Kontext des Portfolios.

        Hier macht AI Sinn weil:
        - Fear & Greed alleine sagt nicht viel
        - Kombination mit Social Volume ist komplex
        - Portfolio-Kontext ist wichtig
        """
        prompt = f"""Analysiere die Markt-Stimmung:

SENTIMENT DATEN:
- Fear & Greed Index: {fear_greed}/100
- Social Volume (24h change): {social_volume}
- Trending Coins: {", ".join(trending_coins)}

MEIN PORTFOLIO:
{portfolio_positions}

Fragen:
1. Ist der Fear & Greed im historischen Kontext extrem?
2. Passt mein Portfolio zur aktuellen Stimmung?
3. Sollte ich Positionen anpassen?

Beachte die Contrarian-Regel: Extreme Fear kann Kaufgelegenheit sein.
"""
        result = self._call_api(prompt)
        return self._parse_signal(result)

    def explain_anomaly(
        self, asset: str, price_change_24h: float, volume_change_24h: float, recent_news: str = ""
    ) -> str:
        """
        Erklärt ungewöhnliche Preisbewegungen.

        Nützlich für:
        - "Warum ist SOL plötzlich +15%?"
        - "Ist dieser Dump fundamental oder Panik?"
        """
        prompt = f"""Ein Asset zeigt ungewöhnliche Bewegung:

Asset: {asset}
Preis-Änderung (24h): {price_change_24h:+.1f}%
Volumen-Änderung (24h): {volume_change_24h:+.1f}%
News: {recent_news if recent_news else "Keine bekannten News"}

Erkläre mögliche Gründe für diese Bewegung.
Ist das fundamental gerechtfertigt oder übertrieben?
Sollte man kaufen, verkaufen oder abwarten?
"""
        return self._call_api(prompt)

    def multi_factor_decision(
        self,
        math_signal: dict,  # Von Markowitz/Sharpe
        sentiment_signal: dict,  # Von Fear & Greed
        news_signal: dict | None,  # Von News-Analyse
        portfolio_state: dict,
    ) -> tuple[str, float, str]:
        """
        Kombiniert mehrere Signale zu einer finalen Entscheidung.

        Das ist wo AI wirklich hilft:
        - Mathematik sagt: "SOL ist optimal"
        - Sentiment sagt: "Extreme Greed, Vorsicht"
        - News sagt: "Solana hat Netzwerk-Probleme"

        → AI: "Reduziere SOL-Position trotz guter Sharpe Ratio"
        """
        prompt = f"""Kombiniere diese Signale zu einer Entscheidung:

MATHEMATISCHES SIGNAL (Markowitz/Sharpe):
{math_signal}

SENTIMENT SIGNAL (Fear & Greed, Social):
{sentiment_signal}

NEWS SIGNAL:
{news_signal if news_signal else "Keine relevanten News"}

AKTUELLES PORTFOLIO:
{portfolio_state}

Aufgabe:
1. Gewichte die Signale (Mathe ist Basis, Rest sind Filter)
2. Identifiziere Konflikte zwischen Signalen
3. Gib eine finale Empfehlung
4. Begründe warum du so gewichtest
"""
        result = self._call_api(prompt)
        signal = self._parse_signal(result)

        return (signal.action, signal.confidence, signal.reasoning)

    def _parse_signal(self, json_str: str) -> AISignal:
        """Parsed JSON-Response zu AISignal"""
        import json

        try:
            # Extrahiere JSON aus Response (falls Text drumherum)
            start = json_str.find("{")
            end = json_str.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(json_str[start:end])
            else:
                raise ValueError("No JSON found")

            return AISignal(
                direction=data.get("direction", "NEUTRAL"),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=data.get("reasoning", "Keine Begründung"),
                action=data.get("action", "HOLD"),
                affected_assets=data.get("affected_assets", []),
                risk_level=data.get("risk_level", "MEDIUM"),
            )
        except Exception as e:
            return AISignal(
                direction="NEUTRAL",
                confidence=0.0,
                reasoning=f"Parse-Fehler: {e!s}",
                action="HOLD",
                affected_assets=[],
                risk_level="HIGH",
            )


class HybridStrategy:
    """
    Kombiniert mathematische Modelle + AI.

    Architektur:
    ┌─────────────────────────────────────────────────┐
    │                ENTSCHEIDUNGS-PIPELINE            │
    ├─────────────────────────────────────────────────┤
    │                                                  │
    │  1. MATHEMATIK (Basis - immer aktiv)            │
    │     ├── Markowitz → Asset-Gewichtung            │
    │     ├── Sharpe Ratio → Rendite/Risiko           │
    │     └── Kelly → Positionsgröße                  │
    │              ↓                                   │
    │  2. AI-FILTER (optional - verbessert)           │
    │     ├── News-Check → "Gibt es Red Flags?"       │
    │     ├── Sentiment → "Ist Timing gut?"           │
    │     └── Anomalien → "Ist das normal?"           │
    │              ↓                                   │
    │  3. RISIKO-OVERRIDE (Sicherheit)                │
    │     ├── Max Drawdown Check                      │
    │     ├── Position Size Limits                    │
    │     └── Korrelations-Check                      │
    │              ↓                                   │
    │  4. FINALE ENTSCHEIDUNG                         │
    │                                                  │
    └─────────────────────────────────────────────────┘

    AI kann die mathematische Entscheidung:
    - BESTÄTIGEN (confidence boost)
    - WARNEN (reduzierte Positionsgröße)
    - BLOCKIEREN (bei Red Flags)

    AI kann NICHT:
    - Alleine entscheiden
    - Mathematik überstimmen ohne Grund
    - Preise vorhersagen
    """

    def __init__(self, use_ai: bool = True):
        self.use_ai = use_ai
        self.ai = AITradingEnhancer() if use_ai else None

    def make_decision(
        self, math_recommendation: dict, market_data: dict, news: list[dict] | None = None
    ) -> dict:
        """
        Finale Entscheidung mit optionalem AI-Enhancement.
        """
        result = {
            "base_decision": math_recommendation,
            "ai_enhanced": False,
            "final_action": math_recommendation.get("action", "HOLD"),
            "confidence": math_recommendation.get("confidence", 0.5),
            "reasoning": math_recommendation.get("reasoning", ""),
        }

        if not self.use_ai or not self.ai:
            return result

        # AI-Enhancement
        result["ai_enhanced"] = True

        # 1. News-Check (wenn News vorhanden)
        if news:
            news_signal = self.ai.analyze_news(news)
            if news_signal.risk_level == "HIGH" and news_signal.direction == "BEARISH":
                # Red Flag: Reduziere oder blockiere
                result["final_action"] = (
                    "REDUCE" if result["final_action"] == "BUY" else result["final_action"]
                )
                result["confidence"] *= 0.5
                result["reasoning"] += f"\n⚠️ AI-News-Warnung: {news_signal.reasoning}"

        # 2. Sentiment-Context
        sentiment_signal = self.ai.analyze_sentiment_context(
            fear_greed=market_data.get("fear_greed", 50),
            social_volume=market_data.get("social_volume", {}),
            trending_coins=market_data.get("trending", []),
            portfolio_positions=market_data.get("positions", {}),
        )

        # Contrarian-Logik
        fg = market_data.get("fear_greed", 50)
        if fg < 25 and result["final_action"] == "BUY":
            # Extreme Fear + Buy = Gutes Timing
            result["confidence"] *= 1.2
            result["reasoning"] += "\n✅ AI: Extreme Fear ist historisch guter Einstieg"
        elif fg > 75 and result["final_action"] == "BUY":
            # Extreme Greed + Buy = Schlechtes Timing
            result["confidence"] *= 0.7
            result["reasoning"] += "\n⚠️ AI: Extreme Greed, vorsichtig mit neuen Positionen"

        result["ai_reasoning"] = sentiment_signal.reasoning

        return result
