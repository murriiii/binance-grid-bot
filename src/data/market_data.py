"""
Zentraler Market Data Provider.
Konsolidiert alle Marktdaten-Abfragen mit Caching.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.api.http_client import HTTPClientError, cached, get_http_client
from src.core.config import get_config
from src.utils.singleton import SingletonMixin

logger = logging.getLogger("trading_bot")


@dataclass
class FearGreedData:
    """Fear & Greed Index Daten"""

    value: int
    classification: str
    timestamp: datetime


@dataclass
class PriceData:
    """Preisdaten für ein Symbol"""

    symbol: str
    price: float
    change_24h: float
    volume_24h: float
    timestamp: datetime


class MarketDataProvider(SingletonMixin):
    """
    Zentraler Provider für alle Marktdaten.

    Features:
    - Einheitliche API für Fear & Greed, Preise, etc.
    - Automatisches Caching (5 Minuten TTL)
    - Fehlerbehandlung mit Fallbacks
    - Statistiken

    Usage:
        market = MarketDataProvider.get_instance()
        fg = market.get_fear_greed()
        price = market.get_price("BTCUSDT")
    """

    def __init__(self):
        self.http = get_http_client()
        self.config = get_config()

        # Cache für Preise (in-memory, kurze TTL)
        self._price_cache: dict[str, tuple] = {}
        self._cache_ttl = 60  # 1 Minute für Preise

    @cached(ttl_seconds=300)  # 5 Minuten Cache
    def get_fear_greed(self) -> FearGreedData:
        """
        Holt den aktuellen Fear & Greed Index.

        Returns:
            FearGreedData mit value (0-100), classification und timestamp
        """
        try:
            data = self.http.get(self.config.api.fear_greed_url, api_type="default")

            fg_data = data["data"][0]
            value = int(fg_data["value"])

            return FearGreedData(
                value=value,
                classification=self._classify_fear_greed(value),
                timestamp=datetime.now(),
            )

        except HTTPClientError as e:
            logger.warning(f"Fear & Greed API error: {e}")
            return FearGreedData(value=50, classification="Neutral", timestamp=datetime.now())

    def _classify_fear_greed(self, value: int) -> str:
        """Klassifiziert Fear & Greed Wert"""
        cfg = self.config.sentiment
        if value <= cfg.extreme_fear_threshold:
            return "Extreme Fear"
        elif value <= cfg.fear_threshold:
            return "Fear"
        elif value <= cfg.greed_threshold:
            return "Neutral"
        elif value <= cfg.extreme_greed_threshold:
            return "Greed"
        else:
            return "Extreme Greed"

    def get_price(self, symbol: str) -> float:
        """
        Holt aktuellen Preis für ein Symbol.

        Args:
            symbol: Trading-Pair (z.B. "BTCUSDT")

        Returns:
            Aktueller Preis als float, 0.0 bei Fehler
        """
        # Cache prüfen
        if symbol in self._price_cache:
            price, timestamp = self._price_cache[symbol]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                return price

        try:
            data = self.http.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol},
                api_type="binance",
            )

            price = float(data["price"])

            # Cache aktualisieren
            self._price_cache[symbol] = (price, datetime.now())

            return price

        except HTTPClientError as e:
            logger.warning(f"Price API error for {symbol}: {e}")
            return 0.0

    @cached(ttl_seconds=300)
    def get_24h_ticker(self, symbol: str) -> PriceData | None:
        """
        Holt 24h Ticker-Daten.

        Returns:
            PriceData mit price, change_24h, volume_24h
        """
        try:
            data = self.http.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": symbol},
                api_type="binance",
            )

            return PriceData(
                symbol=symbol,
                price=float(data["lastPrice"]),
                change_24h=float(data["priceChangePercent"]),
                volume_24h=float(data["quoteVolume"]),
                timestamp=datetime.now(),
            )

        except HTTPClientError as e:
            logger.warning(f"24h Ticker API error for {symbol}: {e}")
            return None

    @cached(ttl_seconds=600)  # 10 Minuten Cache
    def get_trending_coins(self, limit: int = 10) -> list[dict]:
        """
        Holt Trending Coins von CoinGecko.

        Returns:
            Liste von Coins mit name, symbol, market_cap_rank
        """
        try:
            data = self.http.get(
                f"{self.config.api.coingecko_url}/search/trending", api_type="default"
            )

            trending = []
            for item in data.get("coins", [])[:limit]:
                coin = item.get("item", {})
                trending.append(
                    {
                        "name": coin.get("name", ""),
                        "symbol": coin.get("symbol", "").upper(),
                        "rank": coin.get("market_cap_rank", 0),
                        "price_btc": coin.get("price_btc", 0),
                    }
                )

            return trending

        except HTTPClientError as e:
            logger.warning(f"Trending API error: {e}")
            return []

    @cached(ttl_seconds=300)
    def get_btc_dominance(self) -> float:
        """Holt Bitcoin Dominance"""
        try:
            data = self.http.get(f"{self.config.api.coingecko_url}/global", api_type="default")

            return data.get("data", {}).get("market_cap_percentage", {}).get("btc", 0.0)

        except HTTPClientError as e:
            logger.warning(f"BTC Dominance API error: {e}")
            return 0.0

    @cached(ttl_seconds=300)
    def get_total_market_cap(self) -> float:
        """Holt Total Market Cap in USD"""
        try:
            data = self.http.get(f"{self.config.api.coingecko_url}/global", api_type="default")

            return data.get("data", {}).get("total_market_cap", {}).get("usd", 0.0)

        except HTTPClientError as e:
            logger.warning(f"Market Cap API error: {e}")
            return 0.0

    def get_market_overview(self) -> dict:
        """
        Holt kompletten Marktüberblick.

        Returns:
            Dict mit fear_greed, btc_price, trending, market_cap, etc.
        """
        fear_greed = self.get_fear_greed()
        btc_ticker = self.get_24h_ticker("BTCUSDT")
        eth_ticker = self.get_24h_ticker("ETHUSDT")
        trending = self.get_trending_coins(5)

        return {
            "timestamp": datetime.now().isoformat(),
            "fear_greed": {"value": fear_greed.value, "classification": fear_greed.classification},
            "btc": {
                "price": btc_ticker.price if btc_ticker else 0,
                "change_24h": btc_ticker.change_24h if btc_ticker else 0,
                "dominance": self.get_btc_dominance(),
            },
            "eth": {
                "price": eth_ticker.price if eth_ticker else 0,
                "change_24h": eth_ticker.change_24h if eth_ticker else 0,
            },
            "trending": trending,
            "total_market_cap": self.get_total_market_cap(),
        }

    def get_funding_rate(self, symbol: str) -> float | None:
        """D5: Get current funding rate from Binance Futures (public endpoint).

        Funding rate interpretation:
        - Rate > 0.05%: bearish signal (longs pay shorts, market overheated)
        - Rate < -0.05%: bullish signal (shorts pay longs, market oversold)
        - Rate between -0.05% and 0.05%: neutral

        Returns funding rate as a decimal (e.g. 0.0001 = 0.01%), or None on error.
        """
        cache_key = f"funding_{symbol}"
        now = datetime.now()
        if cache_key in self._price_cache:
            cached_time, cached_val = self._price_cache[cache_key]
            if now - cached_time < timedelta(minutes=5):
                return cached_val

        try:
            data = self.http.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": symbol.upper(), "limit": 1},
                timeout=10,
            )
            if data and len(data) > 0:
                rate = float(data[0].get("fundingRate", 0))
                self._price_cache[cache_key] = (now, rate)
                return rate
        except HTTPClientError as e:
            logger.debug(f"Funding rate fetch failed for {symbol}: {e}")
        except Exception as e:
            logger.debug(f"Funding rate error for {symbol}: {e}")

        return None

    def clear_cache(self):
        """Leert alle Caches"""
        self._price_cache.clear()
        # Cached decorators haben eigene clear Methoden
        if hasattr(self.get_fear_greed, "clear_cache"):
            self.get_fear_greed.clear_cache()
        logger.info("Market data cache cleared")


# Convenience-Funktion
def get_market_data() -> MarketDataProvider:
    """Gibt die globale MarketDataProvider-Instanz zurück"""
    return MarketDataProvider.get_instance()
