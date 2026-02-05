"""
Token Unlock Tracker - Verfolgt anstehende Token Unlocks

Token Unlocks sind wichtig weil:
- Supply Shock: Mehr Token im Umlauf
- Verkaufsdruck von Investoren/Team
- Oft Preisdruck in den Tagen vor/nach Unlock
- Größe des Unlocks korreliert mit Impact

Datenquellen:
- TokenUnlocks.app (API oder Scraping)
- CryptoRank
- Manuelle Events für große Unlocks
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

# HTTP Client
try:
    from src.api.http_client import get_http_client
except ImportError:
    get_http_client = None


@dataclass
class TokenUnlock:
    """Ein Token Unlock Event"""

    symbol: str
    unlock_date: datetime
    unlock_amount: float  # Token Anzahl
    unlock_value_usd: float  # Geschätzter USD Wert
    unlock_pct_of_supply: float  # % des Circulating Supply
    unlock_type: str  # CLIFF, LINEAR, INVESTOR, TEAM, FOUNDATION
    receiver: str  # investors, team, foundation, ecosystem, etc.

    # Impact Assessment
    expected_impact: str  # HIGH, MEDIUM, LOW
    historical_reaction: float | None  # Durchschnittliche % Reaktion bei ähnlichen Unlocks
    days_until_unlock: int

    # Nach dem Event (wenn verfügbar)
    actual_price_impact: float | None = None


# Bekannte große Unlock Events (manuell gepflegt)
MAJOR_UNLOCKS = [
    # Diese würden aus einer API kommen oder manuell gepflegt werden
    {
        "symbol": "ARB",
        "unlock_date": "2025-03-16",
        "unlock_pct": 2.65,
        "unlock_type": "INVESTOR",
        "receiver": "investors",
    },
    {
        "symbol": "OP",
        "unlock_date": "2025-02-28",
        "unlock_pct": 2.4,
        "unlock_type": "TEAM",
        "receiver": "core_contributors",
    },
    {
        "symbol": "APT",
        "unlock_date": "2025-04-12",
        "unlock_pct": 2.1,
        "unlock_type": "FOUNDATION",
        "receiver": "foundation",
    },
]


class TokenUnlockTracker:
    """
    Trackt Token Unlocks für Supply-basierte Signale.

    Features:
    1. Holt Unlock-Daten aus APIs/Scraping
    2. Berechnet erwarteten Impact
    3. Warnt vor großen Unlocks
    4. Speichert für historische Analyse
    """

    TOKEN_UNLOCKS_API = "https://api.tokenunlocks.app/v1"
    CRYPTORANK_API = "https://api.cryptorank.io/v1"

    _instance = None

    def __init__(self):
        self.conn = None
        self.http = get_http_client() if get_http_client else None
        self.api_key = os.getenv("TOKEN_UNLOCKS_API_KEY")
        self._connect_db()

    @classmethod
    def get_instance(cls) -> "TokenUnlockTracker":
        """Singleton Pattern"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset für Tests"""
        cls._instance = None

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("TokenUnlockTracker: DB verbunden")
        except Exception as e:
            logger.error(f"TokenUnlockTracker: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # DATA FETCHING
    # ═══════════════════════════════════════════════════════════════

    def get_upcoming_unlocks(
        self,
        days: int = 14,
        min_value_usd: float = 1_000_000,
    ) -> list[TokenUnlock]:
        """
        Hole anstehende Token Unlocks.

        Args:
            days: Zeitraum in Tagen
            min_value_usd: Minimum USD-Wert für Relevanz
        """
        # Versuche API
        unlocks = self._fetch_from_api(days)

        if not unlocks:
            # Fallback: Manuell kuratierte Liste bekannter Unlocks
            unlocks = self._get_manual_unlocks(days)

        # Filtere nach Mindest-Wert
        unlocks = [u for u in unlocks if u.unlock_value_usd >= min_value_usd]

        # Sortiere nach Datum
        unlocks.sort(key=lambda x: x.unlock_date)

        return unlocks

    def _fetch_from_api(self, days: int) -> list[TokenUnlock]:
        """Hole Daten von TokenUnlocks API"""
        if not self.http or not self.api_key:
            return []

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            url = f"{self.TOKEN_UNLOCKS_API}/unlocks"

            params = {
                "days": days,
                "limit": 100,
            }

            response = self.http.get(url, params=params, headers=headers, timeout=10)

            if response and "data" in response:
                unlocks = []
                for item in response["data"]:
                    unlock = TokenUnlock(
                        symbol=item.get("symbol", "").upper(),
                        unlock_date=datetime.fromisoformat(item.get("unlockDate")),
                        unlock_amount=float(item.get("amount", 0)),
                        unlock_value_usd=float(item.get("valueUsd", 0)),
                        unlock_pct_of_supply=float(item.get("percentOfSupply", 0)),
                        unlock_type=item.get("type", "UNKNOWN").upper(),
                        receiver=item.get("receiver", "unknown"),
                        expected_impact=self._assess_impact(
                            float(item.get("percentOfSupply", 0)),
                            float(item.get("valueUsd", 0)),
                        ),
                        historical_reaction=item.get("avgHistoricalReaction"),
                        days_until_unlock=(
                            datetime.fromisoformat(item.get("unlockDate")) - datetime.now()
                        ).days,
                    )
                    unlocks.append(unlock)

                return unlocks

        except Exception as e:
            logger.debug(f"TokenUnlocks API Fehler: {e}")

        return []

    def _get_manual_unlocks(self, days: int) -> list[TokenUnlock]:
        """Manuell kuratierte Unlock-Liste aus MAJOR_UNLOCKS Konstante"""
        unlocks = []
        now = datetime.now()
        cutoff = now + timedelta(days=days)

        # Manuelle Events parsen
        for event in MAJOR_UNLOCKS:
            try:
                unlock_date = datetime.strptime(event["unlock_date"], "%Y-%m-%d")
                if now <= unlock_date <= cutoff:
                    # Schätze USD-Wert (vereinfacht)
                    estimated_value = self._estimate_unlock_value(
                        event["symbol"],
                        event["unlock_pct"],
                    )

                    unlocks.append(
                        TokenUnlock(
                            symbol=event["symbol"],
                            unlock_date=unlock_date,
                            unlock_amount=0,  # Unbekannt
                            unlock_value_usd=estimated_value,
                            unlock_pct_of_supply=event["unlock_pct"],
                            unlock_type=event["unlock_type"],
                            receiver=event["receiver"],
                            expected_impact=self._assess_impact(
                                event["unlock_pct"],
                                estimated_value,
                            ),
                            historical_reaction=None,
                            days_until_unlock=(unlock_date - now).days,
                        )
                    )
            except Exception as e:
                logger.debug(f"Manual unlock parse error: {e}")

        if not unlocks:
            logger.debug("Token Unlocks: Keine Daten verfügbar (APIs nicht erreichbar)")

        return unlocks

    def _estimate_unlock_value(self, symbol: str, pct_of_supply: float) -> float:
        """Schätze USD-Wert eines Unlocks"""
        # Vereinfachte Market Caps (würde aus API kommen)
        market_caps = {
            "SOL": 80_000_000_000,
            "AVAX": 15_000_000_000,
            "ARB": 3_000_000_000,
            "OP": 2_000_000_000,
            "APT": 4_000_000_000,
            "SUI": 3_000_000_000,
        }

        mcap = market_caps.get(symbol.upper(), 1_000_000_000)
        return (pct_of_supply / 100) * mcap

    # ═══════════════════════════════════════════════════════════════
    # IMPACT ASSESSMENT
    # ═══════════════════════════════════════════════════════════════

    def _assess_impact(self, pct_of_supply: float, value_usd: float) -> str:
        """
        Bewerte erwarteten Impact eines Unlocks.

        Kriterien:
        - >5% Supply oder >$100M = HIGH
        - 2-5% Supply oder $20M-100M = MEDIUM
        - <2% Supply und <$20M = LOW
        """
        if pct_of_supply > 5.0 or value_usd > 100_000_000:
            return "HIGH"
        elif pct_of_supply > 2.0 or value_usd > 20_000_000:
            return "MEDIUM"
        else:
            return "LOW"

    def get_symbol_unlocks(self, symbol: str, days: int = 30) -> list[TokenUnlock]:
        """Hole Unlocks für ein spezifisches Symbol"""
        all_unlocks = self.get_upcoming_unlocks(days, min_value_usd=0)
        return [u for u in all_unlocks if u.symbol.upper() == symbol.upper()]

    def get_unlock_signal(self, symbol: str) -> tuple[float, str]:
        """
        Generiere Trading-Signal basierend auf Unlocks.

        Returns: (signal_strength, reasoning)
        signal_strength: -1 (bearish) bis +1 (bullish)
        """
        unlocks = self.get_symbol_unlocks(symbol, days=14)

        if not unlocks:
            return 0.0, "No upcoming unlocks"

        signal = 0.0
        reasons = []

        for unlock in unlocks:
            # Je näher und je größer, desto bearisher
            days_factor = max(0, 14 - unlock.days_until_unlock) / 14

            if unlock.expected_impact == "HIGH":
                signal -= 0.5 * days_factor
                reasons.append(f"HIGH impact unlock in {unlock.days_until_unlock}d")
            elif unlock.expected_impact == "MEDIUM":
                signal -= 0.3 * days_factor
                reasons.append(f"MEDIUM impact unlock in {unlock.days_until_unlock}d")
            else:
                signal -= 0.1 * days_factor

        # Normalisieren
        signal = max(-1.0, min(0.0, signal))  # Unlocks sind immer bearish oder neutral

        return signal, " | ".join(reasons) if reasons else "Minor unlocks only"

    def get_significant_unlocks(
        self,
        days: int = 7,
        min_pct: float = 2.0,
    ) -> list[TokenUnlock]:
        """Hole nur signifikante Unlocks (>2% Supply)"""
        all_unlocks = self.get_upcoming_unlocks(days)
        return [u for u in all_unlocks if u.unlock_pct_of_supply >= min_pct]

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_unlock(self, unlock: TokenUnlock):
        """Speichere Unlock in der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO token_unlocks (
                        symbol, unlock_date, unlock_amount, unlock_value_usd,
                        unlock_pct_of_supply, unlock_type, expected_impact
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """,
                    (
                        unlock.symbol,
                        unlock.unlock_date,
                        unlock.unlock_amount,
                        unlock.unlock_value_usd,
                        unlock.unlock_pct_of_supply,
                        unlock.unlock_type,
                        unlock.expected_impact,
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.error(f"Token Unlock Speicherfehler: {e}")
            self.conn.rollback()

    def update_actual_impact(self, symbol: str, unlock_date: datetime, actual_impact: float):
        """Update tatsächlichen Impact nach Unlock"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE token_unlocks
                    SET actual_price_impact = %s
                    WHERE symbol = %s AND DATE(unlock_date) = DATE(%s)
                """,
                    (actual_impact, symbol, unlock_date),
                )
                self.conn.commit()

        except Exception as e:
            logger.error(f"Token Unlock Update Fehler: {e}")
            self.conn.rollback()

    def fetch_and_store_upcoming(self, days: int = 30):
        """Hole und speichere alle anstehenden Unlocks"""
        unlocks = self.get_upcoming_unlocks(days, min_value_usd=1_000_000)

        for unlock in unlocks:
            self.store_unlock(unlock)

        logger.info(f"TokenUnlockTracker: {len(unlocks)} Unlocks gespeichert")
        return unlocks

    def get_stored_unlocks(self, days: int = 14) -> list[dict[str, Any]]:
        """Hole gespeicherte Unlocks aus DB"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM token_unlocks
                    WHERE unlock_date BETWEEN NOW() AND NOW() + INTERVAL '%s days'
                    ORDER BY unlock_date
                """,
                    (days,),
                )
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Token Unlock Abruf Fehler: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
