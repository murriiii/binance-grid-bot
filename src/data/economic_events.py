"""
Economic Events Tracker
Makro- und mikroökonomische Ereignisse die Krypto beeinflussen

Wichtige Events:
- Fed/EZB Zinsentscheidungen
- CPI (Inflation)
- Arbeitsmarktdaten (NFP)
- Krypto-spezifische Regulierung
- Bitcoin ETF Flows
- Große Token Unlocks
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.api.http_client import HTTPClientError, get_http_client
from src.core.config import get_config

logger = logging.getLogger("trading_bot")


@dataclass
class EconomicEvent:
    """Ein wirtschaftliches Ereignis"""

    date: datetime
    name: str
    country: str
    impact: str  # HIGH, MEDIUM, LOW
    category: str  # FOMC, CPI, NFP, CRYPTO, GEOPOLITICAL
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None

    def is_upcoming(self, hours: int = 24) -> bool:
        """Ist das Event in den nächsten X Stunden?"""
        return datetime.now() < self.date < datetime.now() + timedelta(hours=hours)

    def crypto_impact_analysis(self) -> str:
        """Wie beeinflusst das Event Krypto?"""
        analyses = {
            "FOMC": """
                Fed Zinsentscheidung:
                - Zinserhöhung → BEARISH (Liquidität sinkt, Dollar stärker)
                - Zinssenkung → BULLISH (Mehr Liquidität, Risk-On)
                - Hawkish Ton → BEARISH
                - Dovish Ton → BULLISH

                Typische Reaktion: BTC ±3-8% am Tag der Entscheidung
            """,
            "CPI": """
                Inflationsdaten (CPI):
                - Höher als erwartet → BEARISH (Fed bleibt hawkish)
                - Niedriger als erwartet → BULLISH (Fed könnte lockern)

                Typische Reaktion: BTC ±2-5% bei Überraschungen
            """,
            "NFP": """
                Arbeitsmarktdaten:
                - Starker Arbeitsmarkt → Gemischt (gut für Wirtschaft, aber Fed bleibt streng)
                - Schwacher Arbeitsmarkt → Kurzfristig bearish, dann bullish (Fed lockert)
            """,
            "CRYPTO": """
                Krypto-spezifisch:
                - ETF Zuflüsse → BULLISH
                - ETF Abflüsse → BEARISH
                - Positive Regulierung → BULLISH
                - Negative Regulierung → BEARISH
                - Große Unlocks → Kurzfristig BEARISH (Verkaufsdruck)
            """,
        }
        return analyses.get(self.category, "Keine spezifische Analyse verfügbar")


class EconomicCalendar:
    """
    Holt wirtschaftliche Events von verschiedenen Quellen.

    Kostenlose Quellen:
    - ForexFactory (scraping)
    - Investing.com Economic Calendar
    - CoinGecko Events (Krypto-spezifisch)
    """

    # Wichtige Events die wir tracken
    HIGH_IMPACT_EVENTS = [
        "FOMC",
        "Fed Interest Rate Decision",
        "CPI",
        "Core CPI",
        "Non-Farm Payrolls",
        "NFP",
        "ECB Interest Rate",
        "GDP",
        "PCE",
        "Unemployment Rate",
    ]

    CRYPTO_EVENTS = [
        "Bitcoin ETF",
        "Ethereum ETF",
        "SEC",
        "Token Unlock",
        "Halving",
    ]

    def __init__(self):
        self.http = get_http_client()
        self.config = get_config()
        self.cached_events: list[EconomicEvent] = []
        self.last_fetch: datetime = None

    def fetch_upcoming_events(self, days: int = 7) -> list[EconomicEvent]:
        """
        Holt anstehende wirtschaftliche Events.
        Kombiniert mehrere kostenlose Quellen.
        """
        events = []

        # 1. Versuche Investing.com Calendar API
        investing_events = self._fetch_from_investing_com(days)
        events.extend(investing_events)

        # 2. Füge bekannte wiederkehrende Events hinzu (FOMC Termine etc.)
        recurring = self._get_recurring_events(days)
        events.extend(recurring)

        # 3. Cache aktualisieren
        self.cached_events = events
        self.last_fetch = datetime.now()

        return events

    def _fetch_from_investing_com(self, days: int = 7) -> list[EconomicEvent]:
        """
        Holt Events von Investing.com.
        Kostenloser Endpoint, Rate-Limited.
        """
        events = []

        try:
            # TradingView hat einen (inoffiziellen) API Endpoint
            end_date = datetime.now() + timedelta(days=days)

            data = self.http.get(
                self.config.api.economic_calendar_url,
                params={
                    "from": datetime.now().strftime("%Y-%m-%dT00:00:00.000Z"),
                    "to": end_date.strftime("%Y-%m-%dT23:59:59.000Z"),
                    "countries": "US,EU,GB,JP,CN",
                    "importance": "2,3",  # Medium und High
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                api_type="default",
            )

            for item in data.get("result", []):
                try:
                    # Parse Event
                    importance = item.get("importance", 0)
                    impact = "HIGH" if importance >= 3 else "MEDIUM" if importance >= 2 else "LOW"

                    # Kategorisieren
                    title = item.get("title", "").upper()
                    category = self._categorize_event(title)

                    event = EconomicEvent(
                        date=datetime.fromisoformat(item.get("date", "").replace("Z", "+00:00")),
                        name=item.get("title", "Unknown"),
                        country=item.get("country", "US"),
                        impact=impact,
                        category=category,
                        previous=str(item.get("previous", "")),
                        forecast=str(item.get("forecast", "")),
                        actual=str(item.get("actual", "")),
                    )
                    events.append(event)
                except Exception:
                    continue

        except HTTPClientError as e:
            logger.warning(f"Economic Events Error: {e}")

        return events

    def _categorize_event(self, title: str) -> str:
        """Kategorisiert ein Event basierend auf dem Titel"""
        title_upper = title.upper()

        if any(x in title_upper for x in ["FOMC", "FED", "FEDERAL RESERVE", "INTEREST RATE"]):
            return "FOMC"
        elif any(x in title_upper for x in ["CPI", "CONSUMER PRICE", "INFLATION"]):
            return "CPI"
        elif any(x in title_upper for x in ["NFP", "NON-FARM", "NONFARM", "PAYROLL", "EMPLOYMENT"]):
            return "NFP"
        elif any(x in title_upper for x in ["GDP", "GROSS DOMESTIC"]):
            return "GDP"
        elif any(x in title_upper for x in ["ECB", "EUROPEAN CENTRAL"]):
            return "ECB"
        elif any(x in title_upper for x in ["ETF", "SEC", "BITCOIN", "CRYPTO"]):
            return "CRYPTO"
        else:
            return "OTHER"

    def _get_recurring_events(self, days: int = 7) -> list[EconomicEvent]:
        """
        Gibt bekannte wiederkehrende Events zurück.
        FOMC Meetings sind im Voraus bekannt.
        """
        events = []
        now = datetime.now()
        end_date = now + timedelta(days=days)

        # FOMC Meeting Termine 2024-2025 (fest terminiert)
        fomc_dates = [
            # 2025
            datetime(2025, 1, 29, 19, 0),
            datetime(2025, 3, 19, 19, 0),
            datetime(2025, 5, 7, 19, 0),
            datetime(2025, 6, 18, 19, 0),
            datetime(2025, 7, 30, 19, 0),
            datetime(2025, 9, 17, 19, 0),
            datetime(2025, 11, 5, 19, 0),
            datetime(2025, 12, 17, 19, 0),
            # 2026
            datetime(2026, 1, 28, 19, 0),
            datetime(2026, 3, 18, 19, 0),
            datetime(2026, 5, 6, 19, 0),
            datetime(2026, 6, 17, 19, 0),
        ]

        for fomc_date in fomc_dates:
            if now <= fomc_date <= end_date:
                events.append(
                    EconomicEvent(
                        date=fomc_date,
                        name="FOMC Meeting - Interest Rate Decision",
                        country="US",
                        impact="HIGH",
                        category="FOMC",
                    )
                )

        # CPI Release (typischerweise ~10.-15. jeden Monats, 8:30 EST)
        # Vereinfacht: Prüfe ob wir nahe dem 12. des Monats sind
        for month_offset in range(2):
            potential_cpi = datetime(
                now.year if now.month + month_offset <= 12 else now.year + 1,
                (now.month + month_offset - 1) % 12 + 1,
                12,
                13,
                30,  # 8:30 EST = 13:30 UTC
            )
            if now <= potential_cpi <= end_date:
                events.append(
                    EconomicEvent(
                        date=potential_cpi,
                        name="CPI (Consumer Price Index)",
                        country="US",
                        impact="HIGH",
                        category="CPI",
                    )
                )

        return events

    def get_upcoming_high_impact(self, hours: int = 48) -> list[EconomicEvent]:
        """Gibt nur High-Impact Events der nächsten X Stunden zurück"""
        return [e for e in self.cached_events if e.impact == "HIGH" and e.is_upcoming(hours)]

    def should_trade_today(self) -> tuple[bool, str]:
        """
        Entscheidet ob heute ein guter Tag zum Traden ist.

        Regel: Bei High-Impact Events vorsichtig sein.

        Returns:
            (should_trade, reason)
        """
        upcoming = self.get_upcoming_high_impact(hours=24)

        if not upcoming:
            return True, "Keine High-Impact Events in den nächsten 24h"

        event_names = [e.name for e in upcoming]

        # FOMC ist besonders wichtig
        if any("FOMC" in e or "Fed" in e for e in event_names):
            return False, f"⚠️ FOMC heute - erhöhte Volatilität erwartet. Events: {event_names}"

        # CPI auch wichtig
        if any("CPI" in e for e in event_names):
            return False, f"⚠️ CPI Release heute - warte auf Daten. Events: {event_names}"

        return True, f"High-Impact Events heute: {event_names} - mit Vorsicht handeln"


class CryptoSpecificEvents:
    """
    Krypto-spezifische Events die den Markt beeinflussen.
    """

    def get_token_unlocks(self) -> list[dict]:
        """
        Holt anstehende Token Unlocks.

        Unlock = Tokens werden freigegeben (oft Verkaufsdruck)

        Quelle: token.unlocks.app oder ähnliche
        """
        # TODO: Implementiere API-Call zu Token Unlocks Service
        return []

    def get_etf_flows(self) -> dict:
        """
        Bitcoin/Ethereum ETF Zu-/Abflüsse.

        Wichtig für institutionelles Sentiment.
        """
        # TODO: Implementiere Fetching von ETF Flow Daten
        # Quellen: BitMEX Research, The Block, etc.
        return {"btc_etf_flow_24h": 0, "eth_etf_flow_24h": 0, "trend": "NEUTRAL"}

    def get_upcoming_crypto_events(self) -> list[dict]:
        """
        Krypto-spezifische Events (Upgrades, Forks, etc.)
        """
        # TODO: CoinGecko oder CoinMarketCal API
        return []


class MacroAnalyzer:
    """
    Kombiniert alle makroökonomischen Daten für Trading-Entscheidungen.
    """

    def __init__(self):
        self.calendar = EconomicCalendar()
        self.crypto_events = CryptoSpecificEvents()

    def get_macro_context(self) -> dict:
        """
        Erstellt einen Makro-Kontext für die AI.

        Wird in den DeepSeek-Prompt eingebaut.
        """
        should_trade, reason = self.calendar.should_trade_today()
        etf_flows = self.crypto_events.get_etf_flows()

        return {
            "should_trade": should_trade,
            "reason": reason,
            "etf_flows": etf_flows,
            "upcoming_events": self.calendar.get_upcoming_high_impact(48),
            "timestamp": datetime.now().isoformat(),
        }

    def generate_macro_prompt(self) -> str:
        """
        Generiert einen Prompt-Abschnitt für makroökonomischen Kontext.
        """
        context = self.get_macro_context()

        prompt = f"""
=== MAKROÖKONOMISCHER KONTEXT ===

📅 Trading-Empfehlung heute: {"✅ JA" if context["should_trade"] else "⚠️ VORSICHT"}
Grund: {context["reason"]}

📊 ETF Flows (24h):
- Bitcoin ETF: {context["etf_flows"].get("btc_etf_flow_24h", "N/A")} Mio USD
- Ethereum ETF: {context["etf_flows"].get("eth_etf_flow_24h", "N/A")} Mio USD
- Trend: {context["etf_flows"].get("trend", "N/A")}

📆 Anstehende High-Impact Events:
"""
        for event in context["upcoming_events"][:5]:
            prompt += f"- {event.date.strftime('%Y-%m-%d %H:%M')}: {event.name} ({event.country})\n"

        if not context["upcoming_events"]:
            prompt += "- Keine High-Impact Events in den nächsten 48h\n"

        prompt += """
HANDLUNGSEMPFEHLUNG:
- Bei FOMC/CPI: Positionen VOR dem Event reduzieren oder hedgen
- Bei positiven ETF Flows: Bias bullish
- Bei negativen ETF Flows: Bias bearish
"""
        return prompt


# Für später: Economic Calendar API Integration
# Beispiel mit Trading Economics (kostenpflichtig aber gut):
#
# class TradingEconomicsAPI:
#     BASE_URL = "https://api.tradingeconomics.com"
#
#     def __init__(self, api_key: str):
#         self.api_key = api_key
#
#     def get_calendar(self, country: str = 'united states', days: int = 7):
#         response = requests.get(
#             f"{self.BASE_URL}/calendar/country/{country}",
#             params={'c': self.api_key, 'd1': ..., 'd2': ...}
#         )
#         return response.json()
