"""Binance API Client Wrapper - mit Rate Limiting und Decimal-Formatierung"""

import logging
import os
import time
from collections import deque
from decimal import Decimal
from threading import Lock

from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trading_bot")


def format_decimal(value: float | Decimal | str) -> str:
    """Format a number for Binance API - no scientific notation, no excess trailing zeros."""
    d = Decimal(str(value))
    result = format(d, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


class RateLimiter:
    """
    Thread-safe Rate Limiter für API-Calls.
    Binance erlaubt 1200 requests/min für Spot API.
    """

    def __init__(self, max_requests: int = 1200, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = deque()
        self.lock = Lock()

    def acquire(self):
        """Wartet wenn nötig, um Rate Limit einzuhalten"""
        with self.lock:
            now = time.time()

            # Entferne alte Requests außerhalb des Fensters
            while self.requests and self.requests[0] < now - self.window:
                self.requests.popleft()

            # Wenn Limit erreicht, warte
            if len(self.requests) >= self.max_requests:
                sleep_time = self.requests[0] + self.window - now
                if sleep_time > 0:
                    logger.warning(f"Rate limit erreicht, warte {sleep_time:.1f}s")
                    time.sleep(sleep_time)

            self.requests.append(time.time())

    def get_usage(self) -> tuple:
        """Gibt aktuelle Nutzung zurück (current, max)"""
        with self.lock:
            now = time.time()
            # Entferne alte
            while self.requests and self.requests[0] < now - self.window:
                self.requests.popleft()
            return len(self.requests), self.max_requests


class BinanceClient:
    """Binance API Client mit Rate Limiting und Retry-Logik"""

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.rate_limiter = RateLimiter(
            max_requests=1000, window_seconds=60
        )  # 1000 von 1200 zur Sicherheit

        if testnet:
            self.api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            self.api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
            self.client = Client(self.api_key, self.api_secret, testnet=True)
            logger.info("Binance Client initialisiert (TESTNET)")
        else:
            self.api_key = os.getenv("BINANCE_API_KEY")
            self.api_secret = os.getenv("BINANCE_API_SECRET")
            self.client = Client(self.api_key, self.api_secret)
            logger.info("Binance Client initialisiert (LIVE)")

    def _rate_limited_call(self, func, *args, **kwargs):
        """Wrapper für rate-limited API Calls"""
        self.rate_limiter.acquire()
        return func(*args, **kwargs)

    def _retry_call(self, func, *args, retries: int = 3, **kwargs):
        """API Call mit Retry-Logik"""
        last_error = None

        for attempt in range(retries):
            try:
                self.rate_limiter.acquire()
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                last_error = e

                # Rate Limit Error - länger warten
                # -1003: Too many requests, -1015: Too many orders, HTTP 429
                if e.code in (-1003, -1015) or e.status_code == 429:
                    wait_time = 60 * (attempt + 1)
                    logger.warning(
                        f"Rate limit hit, warte {wait_time}s (Versuch {attempt + 1}/{retries})"
                    )
                    time.sleep(wait_time)
                # Server Fehler (5xx) - kurz warten und retry
                elif str(e.code).startswith("5"):
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        f"Server error, warte {wait_time}s (Versuch {attempt + 1}/{retries})"
                    )
                    time.sleep(wait_time)
                else:
                    # Andere Fehler - nicht retry-fähig
                    raise

        raise last_error

    def get_account_balance(self, asset: str = "USDT") -> float:
        """Gibt das verfügbare Guthaben für ein Asset zurück"""
        try:
            account = self._retry_call(self.client.get_account)
            for balance in account["balances"]:
                if balance["asset"] == asset:
                    return float(balance["free"])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"API Error (get_balance): {e}")
            return 0.0

    def get_current_price(self, symbol: str) -> float:
        """Aktueller Preis eines Trading-Pairs"""
        try:
            ticker = self._rate_limited_call(self.client.get_symbol_ticker, symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"API Error (get_price): {e}")
            return 0.0

    def get_symbol_info(self, symbol: str) -> dict:
        """Holt Informationen zu Mindestmengen etc."""
        try:
            info = self._rate_limited_call(self.client.get_symbol_info, symbol)
            if not info:
                logger.error(f"Symbol {symbol} nicht gefunden")
                return None

            filters = {f["filterType"]: f for f in info["filters"]}

            price_filter = filters.get("PRICE_FILTER", {})

            return {
                "min_qty": float(filters["LOT_SIZE"]["minQty"]),
                "max_qty": float(filters["LOT_SIZE"]["maxQty"]),
                "step_size": float(filters["LOT_SIZE"]["stepSize"]),
                "tick_size": float(price_filter.get("tickSize", "0.01")),
                "min_notional": float(
                    filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", 10)
                ),
            }
        except BinanceAPIException as e:
            logger.error(f"API Error (get_symbol_info): {e}")
            return None

    def place_market_buy(self, symbol: str, quote_qty: float | Decimal) -> dict:
        """Market Buy mit Quote-Währung (z.B. USDT)"""
        try:
            order = self._retry_call(
                self.client.order_market_buy,
                symbol=symbol,
                quoteOrderQty=format_decimal(quote_qty),
            )
            logger.info(f"Market BUY: {symbol} für {quote_qty} USDT")
            return {"success": True, "order": order}
        except BinanceAPIException as e:
            logger.error(f"Market BUY fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def place_market_sell(self, symbol: str, quantity: float | Decimal) -> dict:
        """Market Sell mit Menge"""
        try:
            order = self._retry_call(
                self.client.order_market_sell,
                symbol=symbol,
                quantity=format_decimal(quantity),
            )
            logger.info(f"Market SELL: {quantity} {symbol}")
            return {"success": True, "order": order}
        except BinanceAPIException as e:
            logger.error(f"Market SELL fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def place_limit_buy(
        self, symbol: str, quantity: float | Decimal, price: float | Decimal
    ) -> dict:
        """Limit Buy Order"""
        try:
            order = self._retry_call(
                self.client.order_limit_buy,
                symbol=symbol,
                quantity=format_decimal(quantity),
                price=format_decimal(price),
            )
            logger.info(f"Limit BUY: {quantity} {symbol} @ {price}")
            return {"success": True, "order": order}
        except BinanceAPIException as e:
            logger.error(f"Limit BUY fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def place_limit_sell(
        self, symbol: str, quantity: float | Decimal, price: float | Decimal
    ) -> dict:
        """Limit Sell Order"""
        try:
            order = self._retry_call(
                self.client.order_limit_sell,
                symbol=symbol,
                quantity=format_decimal(quantity),
                price=format_decimal(price),
            )
            logger.info(f"Limit SELL: {quantity} {symbol} @ {price}")
            return {"success": True, "order": order}
        except BinanceAPIException as e:
            logger.error(f"Limit SELL fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def get_open_orders(self, symbol: str) -> list:
        """Alle offenen Orders für ein Symbol"""
        try:
            return self._rate_limited_call(self.client.get_open_orders, symbol=symbol)
        except BinanceAPIException as e:
            logger.error(f"API Error (get_open_orders): {e}")
            return []

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Order stornieren"""
        try:
            result = self._retry_call(self.client.cancel_order, symbol=symbol, orderId=order_id)
            logger.info(f"Order {order_id} storniert")
            return {"success": True, "result": result}
        except BinanceAPIException as e:
            logger.error(f"Cancel Order fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def get_order_status(self, symbol: str, order_id: int) -> dict:
        """
        Holt den Status einer spezifischen Order.
        Returns dict mit 'status', 'executedQty', 'price' etc. oder None bei Fehler.
        """
        try:
            order = self._rate_limited_call(self.client.get_order, symbol=symbol, orderId=order_id)
            return order
        except BinanceAPIException as e:
            logger.warning(f"Order Status Error: {e}")
            return None

    def get_all_orders(self, symbol: str, limit: int = 100) -> list:
        """Alle Orders für ein Symbol (inkl. gefüllte und cancelled)"""
        try:
            return self._rate_limited_call(self.client.get_all_orders, symbol=symbol, limit=limit)
        except BinanceAPIException as e:
            logger.error(f"Get All Orders Error: {e}")
            return []

    def get_24h_ticker(self, symbol: str) -> dict:
        """24h Ticker Statistiken"""
        try:
            ticker = self._rate_limited_call(self.client.get_ticker, symbol=symbol)
            return {
                "price_change": float(ticker["priceChange"]),
                "price_change_percent": float(ticker["priceChangePercent"]),
                "high": float(ticker["highPrice"]),
                "low": float(ticker["lowPrice"]),
                "volume": float(ticker["volume"]),
                "quote_volume": float(ticker["quoteVolume"]),
            }
        except BinanceAPIException as e:
            logger.error(f"API Error (get_24h_ticker): {e}")
            return None

    def get_rate_limit_status(self) -> str:
        """Gibt den aktuellen Rate Limit Status zurück"""
        current, max_requests = self.rate_limiter.get_usage()
        percent = (current / max_requests) * 100
        return f"{current}/{max_requests} ({percent:.1f}%)"
