"""
Watchlist Manager für Multi-Coin Trading.

Verwaltet das Coin-Universum:
- Lädt Coins aus der watchlist Tabelle
- Aktualisiert Marktdaten (Preise, Volumen) von Binance
- Aktiviert/Deaktiviert Coins basierend auf Liquidität
- Cached Binance Symbol-Infos
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trading_bot")

# PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.warning("psycopg2 nicht installiert - pip install psycopg2-binary")


@dataclass
class WatchlistCoin:
    """Ein Coin aus der Watchlist mit allen relevanten Daten."""

    id: str
    symbol: str
    base_asset: str
    category: str
    tier: int

    # Limits
    min_position_usd: Decimal
    max_position_usd: Decimal
    max_allocation_pct: Decimal

    # Trading Parameter
    default_grid_range_pct: Decimal | None
    min_volume_24h_usd: Decimal

    # Status
    is_active: bool
    is_tradeable: bool

    # Performance (optional, kann None sein)
    total_trades: int
    win_rate: Decimal | None
    avg_return_pct: Decimal | None
    sharpe_ratio: Decimal | None

    # Aktuelle Marktdaten
    last_price: Decimal | None
    last_volume_24h: Decimal | None
    updated_at: datetime | None

    # Binance Symbol Info (gecached)
    min_qty: Decimal | None = None
    step_size: Decimal | None = None
    min_notional: Decimal | None = None


class WatchlistManager:
    """
    Verwaltet die Watchlist für Multi-Coin Trading.

    Features:
    - Singleton Pattern
    - Lädt alle aktiven Coins aus der DB
    - Aktualisiert Preise/Volumen von Binance
    - Filtert Coins nach Liquidität
    - Cached Binance Symbol-Infos

    Usage:
        manager = WatchlistManager.get_instance()
        coins = manager.get_active_coins()
        manager.update_market_data()
    """

    _instance: WatchlistManager | None = None

    def __init__(self):
        self.conn = None
        self._symbol_cache: dict[str, dict] = {}
        self._cache_expiry: dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=30)
        self._coins: dict[str, WatchlistCoin] = {}
        self._last_full_update: datetime | None = None
        self.connect()

    @classmethod
    def get_instance(cls) -> WatchlistManager:
        """Singleton-Instanz."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset für Tests."""
        if cls._instance is not None:
            if cls._instance.conn:
                cls._instance.conn.close()
            cls._instance = None

    def connect(self) -> bool:
        """Verbindet zur PostgreSQL Datenbank."""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - WatchlistManager deaktiviert")
            return False

        try:
            self.conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", 5432),
                database=os.getenv("POSTGRES_DB", "trading_bot"),
                user=os.getenv("POSTGRES_USER", "trading"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
            )
            logger.info("WatchlistManager: PostgreSQL verbunden")
            return True
        except Exception as e:
            logger.error(f"WatchlistManager: PostgreSQL Fehler: {e}")
            self.conn = None
            return False

    def load_watchlist(self) -> list[WatchlistCoin]:
        """Lädt alle aktiven Coins aus der Datenbank."""
        if not self.conn:
            logger.warning("WatchlistManager: Keine DB-Verbindung")
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        id, symbol, base_asset, category, tier,
                        min_position_usd, max_position_usd, max_allocation_pct,
                        default_grid_range_pct, min_volume_24h_usd,
                        is_active, is_tradeable,
                        total_trades, win_rate, avg_return_pct, sharpe_ratio,
                        last_price, last_volume_24h, updated_at
                    FROM watchlist
                    WHERE is_active = TRUE
                    ORDER BY tier ASC, category ASC, symbol ASC
                """)
                rows = cur.fetchall()

                self._coins = {}
                for row in rows:
                    coin = WatchlistCoin(
                        id=str(row["id"]),
                        symbol=row["symbol"],
                        base_asset=row["base_asset"],
                        category=row["category"],
                        tier=row["tier"],
                        min_position_usd=row["min_position_usd"],
                        max_position_usd=row["max_position_usd"],
                        max_allocation_pct=row["max_allocation_pct"],
                        default_grid_range_pct=row["default_grid_range_pct"],
                        min_volume_24h_usd=row["min_volume_24h_usd"],
                        is_active=row["is_active"],
                        is_tradeable=row["is_tradeable"],
                        total_trades=row["total_trades"] or 0,
                        win_rate=row["win_rate"],
                        avg_return_pct=row["avg_return_pct"],
                        sharpe_ratio=row["sharpe_ratio"],
                        last_price=row["last_price"],
                        last_volume_24h=row["last_volume_24h"],
                        updated_at=row["updated_at"],
                    )
                    self._coins[coin.symbol] = coin

                logger.info(f"WatchlistManager: {len(self._coins)} Coins geladen")
                return list(self._coins.values())

        except Exception as e:
            logger.error(f"WatchlistManager: Fehler beim Laden: {e}")
            return []

    def get_active_coins(self, reload: bool = False) -> list[WatchlistCoin]:
        """Gibt alle aktiven Coins zurück."""
        if not self._coins or reload:
            self.load_watchlist()
        return list(self._coins.values())

    def get_tradeable_coins(self) -> list[WatchlistCoin]:
        """Gibt nur tradeable Coins zurück (aktiv + genug Liquidität)."""
        return [c for c in self.get_active_coins() if c.is_tradeable]

    def get_coins_by_category(self, category: str) -> list[WatchlistCoin]:
        """Filtert Coins nach Kategorie."""
        return [c for c in self.get_active_coins() if c.category == category]

    def get_coins_by_tier(self, tier: int) -> list[WatchlistCoin]:
        """Filtert Coins nach Tier."""
        return [c for c in self.get_active_coins() if c.tier == tier]

    def get_coin(self, symbol: str) -> WatchlistCoin | None:
        """Holt einen einzelnen Coin."""
        if not self._coins:
            self.load_watchlist()
        return self._coins.get(symbol)

    def update_market_data(self, binance_client=None) -> int:
        """
        Aktualisiert Preise und Volumen für alle Coins.

        Args:
            binance_client: Optionaler BinanceClient, sonst wird einer erstellt

        Returns:
            Anzahl erfolgreich aktualisierter Coins
        """
        if not self.conn:
            return 0

        if binance_client is None:
            try:
                from src.api.binance_client import BinanceClient

                binance_client = BinanceClient()
            except Exception as e:
                logger.error(f"WatchlistManager: BinanceClient nicht verfügbar: {e}")
                return 0

        updated = 0
        coins = self.get_active_coins()

        for coin in coins:
            try:
                ticker = binance_client.get_24h_ticker(coin.symbol)
                if ticker:
                    self._update_coin_market_data(
                        symbol=coin.symbol,
                        price=ticker.get("high"),
                        volume_24h=ticker.get("quote_volume"),
                    )
                    updated += 1
            except Exception as e:
                logger.debug(f"WatchlistManager: Fehler bei {coin.symbol}: {e}")

        self._last_full_update = datetime.now()
        logger.info(f"WatchlistManager: {updated}/{len(coins)} Coins aktualisiert")
        return updated

    def _update_coin_market_data(
        self,
        symbol: str,
        price: float,
        volume_24h: float,
    ) -> bool:
        """Aktualisiert Marktdaten eines Coins in der DB."""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE watchlist
                    SET last_price = %s,
                        last_volume_24h = %s,
                        updated_at = NOW()
                    WHERE symbol = %s
                    """,
                    (price, volume_24h, symbol),
                )
                self.conn.commit()

                # Update lokaler Cache
                if symbol in self._coins:
                    self._coins[symbol].last_price = Decimal(str(price))
                    self._coins[symbol].last_volume_24h = Decimal(str(volume_24h))
                    self._coins[symbol].updated_at = datetime.now()

                return True
        except Exception as e:
            logger.error(f"WatchlistManager: Update fehler für {symbol}: {e}")
            self.conn.rollback()
            return False

    def check_liquidity(self) -> list[str]:
        """
        Prüft Liquidität und deaktiviert Coins mit zu wenig Volumen.

        Returns:
            Liste der deaktivierten Symbols
        """
        if not self.conn:
            return []

        deactivated = []
        coins = self.get_active_coins()

        for coin in coins:
            if coin.last_volume_24h and coin.min_volume_24h_usd:
                if coin.last_volume_24h < coin.min_volume_24h_usd:
                    self._set_tradeable(coin.symbol, False)
                    deactivated.append(coin.symbol)
                    logger.warning(
                        f"WatchlistManager: {coin.symbol} deaktiviert "
                        f"(Volume {coin.last_volume_24h:,.0f} < {coin.min_volume_24h_usd:,.0f})"
                    )
                elif not coin.is_tradeable:
                    self._set_tradeable(coin.symbol, True)
                    logger.info(f"WatchlistManager: {coin.symbol} reaktiviert")

        return deactivated

    def _set_tradeable(self, symbol: str, tradeable: bool) -> bool:
        """Setzt den Tradeable-Status eines Coins."""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE watchlist SET is_tradeable = %s WHERE symbol = %s",
                    (tradeable, symbol),
                )
                self.conn.commit()

                if symbol in self._coins:
                    self._coins[symbol].is_tradeable = tradeable

                return True
        except Exception as e:
            logger.error(f"WatchlistManager: Tradeable update fehler: {e}")
            self.conn.rollback()
            return False

    def get_symbol_info(self, symbol: str, binance_client=None) -> dict | None:
        """
        Holt Binance Symbol-Info mit Caching.

        Returns:
            Dict mit min_qty, step_size, min_notional
        """
        # Check Cache
        if symbol in self._symbol_cache and datetime.now() < self._cache_expiry.get(
            symbol, datetime.min
        ):
            return self._symbol_cache[symbol]

        if binance_client is None:
            try:
                from src.api.binance_client import BinanceClient

                binance_client = BinanceClient()
            except Exception:
                return None

        info = binance_client.get_symbol_info(symbol)
        if info:
            self._symbol_cache[symbol] = info
            self._cache_expiry[symbol] = datetime.now() + self._cache_ttl

            # Update Coin-Objekt
            if symbol in self._coins:
                self._coins[symbol].min_qty = Decimal(str(info.get("min_qty", 0)))
                self._coins[symbol].step_size = Decimal(str(info.get("step_size", 0)))
                self._coins[symbol].min_notional = Decimal(str(info.get("min_notional", 0)))

        return info

    def update_coin_performance(
        self,
        symbol: str,
        total_trades: int,
        win_rate: float,
        avg_return_pct: float,
        sharpe_ratio: float | None = None,
    ) -> bool:
        """Aktualisiert Performance-Metriken eines Coins."""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE watchlist
                    SET total_trades = %s,
                        win_rate = %s,
                        avg_return_pct = %s,
                        sharpe_ratio = %s,
                        updated_at = NOW()
                    WHERE symbol = %s
                    """,
                    (total_trades, win_rate, avg_return_pct, sharpe_ratio, symbol),
                )
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"WatchlistManager: Performance update fehler: {e}")
            self.conn.rollback()
            return False

    def add_coin(
        self,
        symbol: str,
        base_asset: str,
        category: str,
        tier: int = 2,
        min_volume_24h_usd: float = 10_000_000,
    ) -> bool:
        """Fügt einen neuen Coin zur Watchlist hinzu."""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlist (symbol, base_asset, category, tier, min_volume_24h_usd)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        category = EXCLUDED.category,
                        tier = EXCLUDED.tier,
                        is_active = TRUE
                    """,
                    (symbol, base_asset, category, tier, min_volume_24h_usd),
                )
                self.conn.commit()
                logger.info(f"WatchlistManager: {symbol} hinzugefügt/aktualisiert")
                self.load_watchlist()  # Reload
                return True
        except Exception as e:
            logger.error(f"WatchlistManager: Add coin fehler: {e}")
            self.conn.rollback()
            return False

    def remove_coin(self, symbol: str, hard_delete: bool = False) -> bool:
        """
        Entfernt einen Coin aus der Watchlist.

        Args:
            symbol: Das Symbol
            hard_delete: True für echtes Löschen, False für Deaktivieren
        """
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                if hard_delete:
                    cur.execute("DELETE FROM watchlist WHERE symbol = %s", (symbol,))
                else:
                    cur.execute(
                        "UPDATE watchlist SET is_active = FALSE WHERE symbol = %s",
                        (symbol,),
                    )
                self.conn.commit()
                self._coins.pop(symbol, None)
                return True
        except Exception as e:
            logger.error(f"WatchlistManager: Remove coin fehler: {e}")
            self.conn.rollback()
            return False

    def get_stats(self) -> dict:
        """Gibt Statistiken über die Watchlist zurück."""
        coins = self.get_active_coins()

        categories = {}
        for coin in coins:
            categories[coin.category] = categories.get(coin.category, 0) + 1

        return {
            "total_coins": len(coins),
            "tradeable_coins": len([c for c in coins if c.is_tradeable]),
            "by_category": categories,
            "by_tier": {
                1: len([c for c in coins if c.tier == 1]),
                2: len([c for c in coins if c.tier == 2]),
                3: len([c for c in coins if c.tier == 3]),
            },
            "last_update": self._last_full_update,
        }


# Convenience-Funktion
def get_watchlist_manager() -> WatchlistManager:
    """Gibt die globale WatchlistManager-Instanz zurück."""
    return WatchlistManager.get_instance()
