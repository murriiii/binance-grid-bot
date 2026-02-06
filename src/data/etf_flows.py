"""
ETF Flow Tracker - Verfolgt Bitcoin und Ethereum ETF Flows

Datenquellen:
- Farside Investors (kostenlos, daily)
- SoSoValue (API)
- BitMEX Research

ETF Flows sind wichtig weil:
- Zeigen institutionelles Interesse
- Inflows = Kaufdruck
- Outflows = Verkaufsdruck
- Korrelieren oft mit Preisbewegungen
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.debug("BeautifulSoup nicht installiert - pip install beautifulsoup4")

# HTTP Client
try:
    from src.api.http_client import get_http_client
except ImportError:
    get_http_client = None


@dataclass
class ETFFlowData:
    """ETF Flow Daten für einen Tag"""

    date: datetime

    # Bitcoin ETFs (Mio USD)
    btc_total_flow: float | None
    btc_cumulative_flow: float | None
    btc_aum: float | None  # Assets Under Management

    # Einzelne BTC ETFs
    gbtc_flow: float | None  # Grayscale
    ibit_flow: float | None  # BlackRock
    fbtc_flow: float | None  # Fidelity
    arkb_flow: float | None  # Ark/21Shares
    bitb_flow: float | None  # Bitwise

    # Ethereum ETFs
    eth_total_flow: float | None
    eth_cumulative_flow: float | None

    # Aggregierte Metriken
    flow_trend: str | None  # INFLOW, OUTFLOW, NEUTRAL
    seven_day_avg: float | None
    thirty_day_avg: float | None

    # Geschätzter Preisimpact
    estimated_price_impact_pct: float | None


class ETFFlowTracker(SingletonMixin):
    """
    Trackt ETF Flows für institutionelles Sentiment.

    Features:
    1. Scraped Farside Investors (täglich)
    2. Berechnet Flow-Trends
    3. Schätzt Preisimpact
    4. Speichert für historische Analyse
    """

    FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
    SOSOVALUE_API = "https://api.sosovalue.xyz/v1"

    def __init__(self):
        self.conn = None
        self.http = get_http_client() if get_http_client else None
        self._connect_db()

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("ETFFlowTracker: DB verbunden")
        except Exception as e:
            logger.error(f"ETFFlowTracker: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # DATA FETCHING
    # ═══════════════════════════════════════════════════════════════

    def fetch_daily_flows(self, date: datetime | None = None) -> ETFFlowData | None:
        """
        Hole ETF Flow Daten für ein Datum.

        Versucht mehrere Quellen:
        1. SoSoValue API
        2. Farside Scraping

        Returns None wenn keine Daten verfügbar.
        """
        if date is None:
            date = datetime.now()

        # Versuche zuerst API
        data = self._fetch_from_sosovalue(date)

        if data is None:
            # Fallback: Scraping
            data = self._scrape_farside(date)

        if data is None:
            logger.debug("ETF Flows: Keine Daten verfügbar (APIs nicht erreichbar)")

        return data

    def _fetch_from_sosovalue(self, date: datetime) -> ETFFlowData | None:
        """Hole Daten von SoSoValue API"""
        if not self.http:
            return None

        try:
            # SoSoValue public endpoint
            url = f"{self.SOSOVALUE_API}/etf/bitcoin/netflow"
            response = self.http.get(url, timeout=10)

            if response and "data" in response:
                # Parse response
                data = response["data"]
                latest = data[-1] if isinstance(data, list) else data

                return ETFFlowData(
                    date=date,
                    btc_total_flow=latest.get("totalNetflow"),
                    btc_cumulative_flow=latest.get("cumulativeNetflow"),
                    btc_aum=latest.get("totalAum"),
                    gbtc_flow=latest.get("gbtc"),
                    ibit_flow=latest.get("ibit"),
                    fbtc_flow=latest.get("fbtc"),
                    arkb_flow=latest.get("arkb"),
                    bitb_flow=latest.get("bitb"),
                    eth_total_flow=None,
                    eth_cumulative_flow=None,
                    flow_trend=self._determine_flow_trend(latest.get("totalNetflow")),
                    seven_day_avg=None,
                    thirty_day_avg=None,
                    estimated_price_impact_pct=self._estimate_price_impact(
                        latest.get("totalNetflow")
                    ),
                )

        except Exception as e:
            logger.debug(f"SoSoValue API Fehler: {e}")

        return None

    def _scrape_farside(self, date: datetime) -> ETFFlowData | None:
        """Scrape Farside Investors Website"""
        if not self.http or not BS4_AVAILABLE:
            return None

        try:
            # Hole HTML
            response = self.http.get(self.FARSIDE_URL, timeout=15)
            if not response:
                return None

            # Parse HTML (vereinfacht - echtes Scraping komplexer)
            soup = BeautifulSoup(response, "html.parser")
            table = soup.find("table")

            if not table:
                return None

            # Finde letzte Zeile mit Daten
            rows = table.find_all("tr")
            if len(rows) < 2:
                return None

            # Parse letzte Datenzeile
            last_row = rows[-1]
            cells = last_row.find_all("td")

            if len(cells) >= 10:
                return ETFFlowData(
                    date=date,
                    btc_total_flow=self._parse_flow_value(cells[-1].text),
                    btc_cumulative_flow=None,
                    btc_aum=None,
                    gbtc_flow=self._parse_flow_value(cells[1].text) if len(cells) > 1 else None,
                    ibit_flow=self._parse_flow_value(cells[2].text) if len(cells) > 2 else None,
                    fbtc_flow=self._parse_flow_value(cells[3].text) if len(cells) > 3 else None,
                    arkb_flow=self._parse_flow_value(cells[4].text) if len(cells) > 4 else None,
                    bitb_flow=self._parse_flow_value(cells[5].text) if len(cells) > 5 else None,
                    eth_total_flow=None,
                    eth_cumulative_flow=None,
                    flow_trend=None,
                    seven_day_avg=None,
                    thirty_day_avg=None,
                    estimated_price_impact_pct=None,
                )

        except Exception as e:
            logger.debug(f"Farside Scraping Fehler: {e}")

        return None

    def _parse_flow_value(self, text: str) -> float | None:
        """Parse Flow-Wert aus Text (z.B. '123.4' oder '-45.6')"""
        try:
            # Entferne Währungssymbole und Whitespace
            cleaned = re.sub(r"[^\d.\-]", "", text.strip())
            if cleaned:
                return float(cleaned)
        except (ValueError, TypeError):
            pass
        return None

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def _determine_flow_trend(self, flow: float | None) -> str:
        """Bestimme Flow-Trend"""
        if flow is None:
            return "NEUTRAL"

        if flow > 100:  # >$100M Inflow
            return "STRONG_INFLOW"
        elif flow > 0:
            return "INFLOW"
        elif flow > -100:
            return "OUTFLOW"
        else:
            return "STRONG_OUTFLOW"

    def _estimate_price_impact(self, flow_mio: float | None) -> float | None:
        """
        Schätze Preisimpact basierend auf Flow.

        Faustregel: $1B Inflow ≈ 3-5% Preisanstieg
        Das ist sehr vereinfacht - echte Korrelation ist komplexer.
        """
        if flow_mio is None:
            return None

        # $1000M = ~4% Impact (Mittelwert)
        impact_per_billion = 4.0
        impact = (flow_mio / 1000) * impact_per_billion

        return round(impact, 2)

    def get_flow_trend(self, days: int = 7) -> dict[str, Any]:
        """Analysiere Flow-Trend der letzten N Tage"""
        if not self.conn:
            return {"trend": "UNKNOWN", "avg_flow": 0, "total_flow": 0}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        AVG(btc_total_flow_usd) as avg_flow,
                        SUM(btc_total_flow_usd) as total_flow,
                        COUNT(*) as data_points
                    FROM etf_flows
                    WHERE date > NOW() - INTERVAL '%s days'
                """,
                    (days,),
                )

                row = cur.fetchone()
                if row and row["avg_flow"] is not None:
                    avg_flow = float(row["avg_flow"])
                    return {
                        "trend": self._determine_flow_trend(avg_flow),
                        "avg_flow": avg_flow,
                        "total_flow": float(row["total_flow"]) if row["total_flow"] else 0,
                        "data_points": row["data_points"],
                    }

        except Exception as e:
            logger.error(f"Flow Trend Fehler: {e}")

        return {"trend": "UNKNOWN", "avg_flow": 0, "total_flow": 0}

    def get_institutional_signal(self) -> tuple[float, str]:
        """
        Generiere Trading-Signal aus ETF Flows.

        Returns: (signal_strength, reasoning)
        signal_strength: -1 (bearish) bis +1 (bullish)
        """
        trend_7d = self.get_flow_trend(7)
        trend_30d = self.get_flow_trend(30)

        signal = 0.0
        reasons = []

        # 7-Tage Trend
        avg_7d = trend_7d.get("avg_flow", 0)
        if avg_7d > 200:
            signal += 0.5
            reasons.append(f"Strong 7d inflow: ${avg_7d:.0f}M avg")
        elif avg_7d > 0:
            signal += 0.2
            reasons.append(f"7d inflow: ${avg_7d:.0f}M avg")
        elif avg_7d > -200:
            signal -= 0.2
            reasons.append(f"7d outflow: ${avg_7d:.0f}M avg")
        else:
            signal -= 0.5
            reasons.append(f"Strong 7d outflow: ${avg_7d:.0f}M avg")

        # 30-Tage Trend für Kontext
        avg_30d = trend_30d.get("avg_flow", 0)
        if avg_30d > 100:
            signal += 0.3
            reasons.append("30d trend bullish")
        elif avg_30d < -100:
            signal -= 0.3
            reasons.append("30d trend bearish")

        # Normalisieren
        signal = max(-1.0, min(1.0, signal))

        return signal, " | ".join(reasons)

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_flow_data(self, data: ETFFlowData):
        """Speichere Flow-Daten in der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO etf_flows (
                        date, btc_total_flow_usd, btc_cumulative_flow,
                        gbtc_flow, ibit_flow, fbtc_flow, arkb_flow, bitb_flow,
                        eth_total_flow_usd, flow_trend, seven_day_avg
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        btc_total_flow_usd = EXCLUDED.btc_total_flow_usd,
                        btc_cumulative_flow = EXCLUDED.btc_cumulative_flow,
                        gbtc_flow = EXCLUDED.gbtc_flow,
                        ibit_flow = EXCLUDED.ibit_flow,
                        fbtc_flow = EXCLUDED.fbtc_flow,
                        flow_trend = EXCLUDED.flow_trend
                """,
                    (
                        data.date.date(),
                        data.btc_total_flow,
                        data.btc_cumulative_flow,
                        data.gbtc_flow,
                        data.ibit_flow,
                        data.fbtc_flow,
                        data.arkb_flow,
                        data.bitb_flow,
                        data.eth_total_flow,
                        data.flow_trend,
                        data.seven_day_avg,
                    ),
                )
                self.conn.commit()
                logger.info(f"ETF Flow für {data.date.date()} gespeichert: ${data.btc_total_flow}M")

        except Exception as e:
            logger.error(f"ETF Flow Speicherfehler: {e}")
            self.conn.rollback()

    def fetch_and_store_daily(self):
        """Hole und speichere heutige ETF Flows"""
        data = self.fetch_daily_flows()
        if data:
            self.store_flow_data(data)
            return data
        return None

    def get_latest_flow(self) -> ETFFlowData | None:
        """Hole neueste gespeicherte Flow-Daten"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM etf_flows
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()

                if row:
                    return ETFFlowData(
                        date=datetime.combine(row["date"], datetime.min.time()),
                        btc_total_flow=float(row["btc_total_flow_usd"])
                        if row["btc_total_flow_usd"]
                        else None,
                        btc_cumulative_flow=float(row["btc_cumulative_flow"])
                        if row["btc_cumulative_flow"]
                        else None,
                        btc_aum=None,
                        gbtc_flow=float(row["gbtc_flow"]) if row["gbtc_flow"] else None,
                        ibit_flow=float(row["ibit_flow"]) if row["ibit_flow"] else None,
                        fbtc_flow=float(row["fbtc_flow"]) if row["fbtc_flow"] else None,
                        arkb_flow=float(row["arkb_flow"]) if row["arkb_flow"] else None,
                        bitb_flow=float(row["bitb_flow"]) if row["bitb_flow"] else None,
                        eth_total_flow=float(row["eth_total_flow_usd"])
                        if row["eth_total_flow_usd"]
                        else None,
                        eth_cumulative_flow=None,
                        flow_trend=row["flow_trend"],
                        seven_day_avg=float(row["seven_day_avg"]) if row["seven_day_avg"] else None,
                        thirty_day_avg=None,
                        estimated_price_impact_pct=None,
                    )

        except Exception as e:
            logger.error(f"ETF Flow Abruf Fehler: {e}")

        return None

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
