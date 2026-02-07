"""Paper Trading Client — Drop-in replacement for BinanceClient.

Uses real Binance mainnet prices (public API, no key needed) with simulated
order matching. Provides the same 13-method interface as BinanceClient so it
can be used as a transparent substitute in the CohortOrchestrator pipeline.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger("trading_bot")

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
BINANCE_TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"

TAKER_FEE_RATE = 0.001  # 0.1%


@dataclass
class PaperOrder:
    """Simulated order with Binance-compatible dict output."""

    order_id: int
    symbol: str
    side: str  # BUY or SELL
    order_type: str  # LIMIT or MARKET
    quantity: float
    price: float
    status: str = "NEW"  # NEW, FILLED, CANCELED
    executed_qty: float = 0.0
    created_at: float = field(default_factory=time.time)
    filled_at: float | None = None

    def to_dict(self) -> dict:
        """Return Binance-compatible order dict."""
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "origQty": str(self.quantity),
            "executedQty": str(self.executed_qty),
            "price": str(self.price),
            "status": self.status,
            "time": int(self.created_at * 1000),
            "updateTime": int((self.filled_at or self.created_at) * 1000),
            "timeInForce": "GTC",
            "isWorking": self.status == "NEW",
        }


class PaperBinanceClient:
    """Simulated Binance client using real mainnet prices.

    All prices come from the public Binance API (no API key needed).
    Orders are matched locally: BUY fills when price <= limit,
    SELL fills when price >= limit.

    Attributes:
        testnet: Always False (we use real mainnet prices).
        client: Self-reference for reporting compatibility
                (code that does client.client.X still works).
    """

    def __init__(
        self,
        initial_usdt: float = 6000.0,
        state_dir: str = "config",
        cohort_name: str = "paper",
    ):
        self.testnet = False
        self.client = self  # Reporting compatibility: client.client.get_open_orders()

        self._next_order_id = 1
        self._orders: dict[int, PaperOrder] = {}  # order_id -> PaperOrder
        self._balances: dict[str, float] = {"USDT": initial_usdt}
        self._reserved: dict[str, float] = {}  # asset -> reserved amount

        self._state_file = Path(state_dir) / f"paper_portfolio_{cohort_name}.json"
        self._symbol_info_cache: dict[str, dict] = {}
        self._price_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
        self._price_cache_ttl = 5.0  # seconds

        self._load_state()

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Same interface as BinanceClient
    # ═══════════════════════════════════════════════════════════════

    def get_current_price(self, symbol: str) -> float:
        """Fetch real mainnet price and match pending orders."""
        price = self._fetch_mainnet_price(symbol)
        if price:
            self._match_pending_orders(symbol, price)
        return price

    def get_account_balance(self, asset: str = "USDT") -> float:
        """Return simulated balance (available, not reserved)."""
        total = self._balances.get(asset, 0.0)
        reserved = self._reserved.get(asset, 0.0)
        return max(0.0, total - reserved)

    def get_symbol_info(self, symbol: str) -> dict:
        """Fetch real symbol info from mainnet (public, no key)."""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        from src.api.http_client import get_http_client

        try:
            http = get_http_client()
            data = http.get(
                BINANCE_EXCHANGE_INFO_URL,
                params={"symbol": symbol},
                api_type="binance",
            )
            symbols = data.get("symbols", [])
            if not symbols:
                return {}

            info = symbols[0]
            # Extract filter values
            result = {
                "symbol": symbol,
                "status": info.get("status"),
                "baseAsset": info.get("baseAsset"),
                "quoteAsset": info.get("quoteAsset"),
            }

            for f in info.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    result["min_qty"] = float(f["minQty"])
                    result["step_size"] = float(f["stepSize"])
                elif f["filterType"] == "NOTIONAL" or f["filterType"] == "MIN_NOTIONAL":
                    result["min_notional"] = float(f.get("minNotional", 0))

            self._symbol_info_cache[symbol] = result
            return result

        except Exception as e:
            logger.error(f"Paper: Failed to fetch symbol info for {symbol}: {e}")
            return {}

    def place_limit_buy(
        self, symbol: str, quantity: float | Decimal, price: float | Decimal
    ) -> dict:
        """Create a limit buy order, reserve USDT."""
        qty = float(quantity)
        px = float(price)
        cost = qty * px

        available = self.get_account_balance("USDT")
        if cost > available + 0.01:  # Small tolerance for rounding
            return {"success": False, "error": "Insufficient USDT balance"}

        order = self._create_order(symbol, "BUY", "LIMIT", qty, px)
        self._reserved["USDT"] = self._reserved.get("USDT", 0.0) + cost

        # Check for immediate fill
        current = self._fetch_mainnet_price(symbol)
        if current and current <= px:
            self._fill_order(order, current)

        self._save_state()
        logger.info(f"Paper: Limit BUY {qty} {symbol} @ {px}")
        return {"success": True, "order": order.to_dict()}

    def place_limit_sell(
        self, symbol: str, quantity: float | Decimal, price: float | Decimal
    ) -> dict:
        """Create a limit sell order, reserve base asset."""
        qty = float(quantity)
        px = float(price)
        base = symbol.replace("USDT", "")

        available = self.get_account_balance(base)
        if qty > available + 1e-8:
            return {"success": False, "error": f"Insufficient {base} balance"}

        order = self._create_order(symbol, "SELL", "LIMIT", qty, px)
        self._reserved[base] = self._reserved.get(base, 0.0) + qty

        # Check for immediate fill
        current = self._fetch_mainnet_price(symbol)
        if current and current >= px:
            self._fill_order(order, current)

        self._save_state()
        logger.info(f"Paper: Limit SELL {qty} {symbol} @ {px}")
        return {"success": True, "order": order.to_dict()}

    def get_open_orders(self, symbol: str) -> list:
        """Return open (NEW) orders for a symbol."""
        return [
            o.to_dict() for o in self._orders.values() if o.symbol == symbol and o.status == "NEW"
        ]

    def get_order_status(self, symbol: str, order_id: int) -> dict | None:
        """Return order status dict."""
        order = self._orders.get(order_id)
        if order and order.symbol == symbol:
            return order.to_dict()
        return None

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an order and release reserved funds."""
        order = self._orders.get(order_id)
        if not order or order.symbol != symbol:
            return {"success": False, "error": "Order not found"}

        if order.status != "NEW":
            return {"success": False, "error": f"Cannot cancel {order.status} order"}

        order.status = "CANCELED"

        # Release reserved funds
        if order.side == "BUY":
            cost = order.quantity * order.price
            self._reserved["USDT"] = max(0, self._reserved.get("USDT", 0) - cost)
        else:
            base = symbol.replace("USDT", "")
            self._reserved[base] = max(0, self._reserved.get(base, 0) - order.quantity)

        self._save_state()
        logger.info(f"Paper: Canceled order {order_id}")
        return {"success": True, "result": order.to_dict()}

    def get_all_orders(self, symbol: str, limit: int = 100) -> list:
        """Return all orders for a symbol (filled, canceled, new)."""
        orders = [o.to_dict() for o in self._orders.values() if o.symbol == symbol]
        orders.sort(key=lambda x: x["time"], reverse=True)
        return orders[:limit]

    def place_market_buy(self, symbol: str, quote_qty: float | Decimal) -> dict:
        """Immediate buy at current market price."""
        quote = float(quote_qty)
        available = self.get_account_balance("USDT")
        if quote > available + 0.01:
            return {"success": False, "error": "Insufficient USDT balance"}

        price = self._fetch_mainnet_price(symbol)
        if not price:
            return {"success": False, "error": "Cannot fetch price"}

        qty = quote / price
        order = self._create_order(symbol, "BUY", "MARKET", qty, price)
        self._fill_order(order, price)
        self._save_state()
        logger.info(f"Paper: Market BUY ${quote:.2f} of {symbol} @ {price}")
        return {"success": True, "order": order.to_dict()}

    def place_market_sell(self, symbol: str, quantity: float | Decimal) -> dict:
        """Immediate sell at current market price."""
        qty = float(quantity)
        base = symbol.replace("USDT", "")
        available = self.get_account_balance(base)
        if qty > available + 1e-8:
            return {"success": False, "error": f"Insufficient {base} balance"}

        price = self._fetch_mainnet_price(symbol)
        if not price:
            return {"success": False, "error": "Cannot fetch price"}

        order = self._create_order(symbol, "SELL", "MARKET", qty, price)
        self._fill_order(order, price)
        self._save_state()
        logger.info(f"Paper: Market SELL {qty} {symbol} @ {price}")
        return {"success": True, "order": order.to_dict()}

    def get_24h_ticker(self, symbol: str) -> dict:
        """Fetch real 24h ticker from mainnet."""
        from src.api.http_client import get_http_client

        try:
            http = get_http_client()
            ticker = http.get(
                BINANCE_TICKER_24H_URL,
                params={"symbol": symbol},
                api_type="binance",
            )
            return {
                "price_change": float(ticker.get("priceChange", 0)),
                "price_change_percent": float(ticker.get("priceChangePercent", 0)),
                "volume": float(ticker.get("volume", 0)),
                "quote_volume": float(ticker.get("quoteVolume", 0)),
                "high": float(ticker.get("highPrice", 0)),
                "low": float(ticker.get("lowPrice", 0)),
            }
        except Exception as e:
            logger.error(f"Paper: 24h ticker error: {e}")
            return {}

    def get_rate_limit_status(self) -> str:
        """Paper trading has no rate limits."""
        return "Paper mode (no limits)"

    # ═══════════════════════════════════════════════════════════════
    # EXTRA — Not in BinanceClient interface
    # ═══════════════════════════════════════════════════════════════

    def get_portfolio_summary(self) -> dict:
        """Calculate total portfolio value across all assets."""
        total = self._balances.get("USDT", 0.0)
        positions = {}

        for asset, qty in self._balances.items():
            if asset == "USDT" or qty <= 0:
                continue
            symbol = f"{asset}USDT"
            price = self._fetch_mainnet_price(symbol)
            if price:
                value = qty * price
                total += value
                positions[asset] = {"qty": qty, "price": price, "value": value}

        return {
            "total_value_usd": total,
            "usdt_balance": self._balances.get("USDT", 0.0),
            "positions": positions,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL
    # ═══════════════════════════════════════════════════════════════

    def _fetch_mainnet_price(self, symbol: str) -> float:
        """Fetch price from Binance mainnet (cached for 5 seconds)."""
        cached = self._price_cache.get(symbol)
        if cached and time.time() - cached[1] < self._price_cache_ttl:
            return cached[0]

        from src.api.http_client import get_http_client

        try:
            http = get_http_client()
            data = http.get(
                BINANCE_PRICE_URL,
                params={"symbol": symbol},
                api_type="binance",
            )
            price = float(data["price"])
            self._price_cache[symbol] = (price, time.time())
            return price
        except Exception as e:
            logger.error(f"Paper: Price fetch failed for {symbol}: {e}")
            return 0.0

    def _create_order(
        self, symbol: str, side: str, order_type: str, qty: float, price: float
    ) -> PaperOrder:
        """Create a new order and register it."""
        order = PaperOrder(
            order_id=self._next_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty,
            price=price,
        )
        self._orders[order.order_id] = order
        self._next_order_id += 1
        return order

    def _fill_order(self, order: PaperOrder, fill_price: float) -> None:
        """Execute an order fill: update balances and fees."""
        order.status = "FILLED"
        order.executed_qty = order.quantity
        order.filled_at = time.time()

        base = order.symbol.replace("USDT", "")
        fee = order.quantity * fill_price * TAKER_FEE_RATE

        if order.side == "BUY":
            cost = order.quantity * order.price  # Reserved at limit price
            actual_cost = order.quantity * fill_price + fee

            # Release reservation and deduct actual cost
            self._reserved["USDT"] = max(0, self._reserved.get("USDT", 0) - cost)
            self._balances["USDT"] = self._balances.get("USDT", 0) - actual_cost

            # Credit base asset (minus fee in base terms)
            received = order.quantity * (1 - TAKER_FEE_RATE)
            self._balances[base] = self._balances.get(base, 0) + received

        else:  # SELL
            # Release reserved base asset
            self._reserved[base] = max(0, self._reserved.get(base, 0) - order.quantity)
            self._balances[base] = self._balances.get(base, 0) - order.quantity

            # Credit USDT (minus fee)
            proceeds = order.quantity * fill_price - fee
            self._balances["USDT"] = self._balances.get("USDT", 0) + proceeds

    def _match_pending_orders(self, symbol: str, current_price: float) -> None:
        """Check all NEW orders for this symbol against current price."""
        for order in list(self._orders.values()):
            if order.symbol != symbol or order.status != "NEW":
                continue

            if order.side == "BUY" and current_price <= order.price:
                self._fill_order(order, current_price)
                logger.info(f"Paper: BUY filled {order.quantity} {symbol} @ {current_price}")
            elif order.side == "SELL" and current_price >= order.price:
                self._fill_order(order, current_price)
                logger.info(f"Paper: SELL filled {order.quantity} {symbol} @ {current_price}")

        self._save_state()

    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def _save_state(self) -> None:
        """Persist portfolio state atomically."""
        state = {
            "balances": self._balances,
            "reserved": self._reserved,
            "next_order_id": self._next_order_id,
            "orders": {
                str(oid): {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "order_type": o.order_type,
                    "quantity": o.quantity,
                    "price": o.price,
                    "status": o.status,
                    "executed_qty": o.executed_qty,
                    "created_at": o.created_at,
                    "filled_at": o.filled_at,
                }
                for oid, o in self._orders.items()
            },
        }

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            temp = self._state_file.with_suffix(".tmp")
            with open(temp, "w") as f:
                json.dump(state, f, indent=2)
            temp.replace(self._state_file)
        except Exception as e:
            logger.error(f"Paper: Failed to save state: {e}")

    def _load_state(self) -> None:
        """Load portfolio state from disk."""
        if not self._state_file.exists():
            return

        try:
            with open(self._state_file) as f:
                state = json.load(f)

            self._balances = state.get("balances", self._balances)
            self._reserved = state.get("reserved", {})
            self._next_order_id = state.get("next_order_id", 1)

            for _oid, odata in state.get("orders", {}).items():
                order = PaperOrder(
                    order_id=odata["order_id"],
                    symbol=odata["symbol"],
                    side=odata["side"],
                    order_type=odata["order_type"],
                    quantity=odata["quantity"],
                    price=odata["price"],
                    status=odata["status"],
                    executed_qty=odata.get("executed_qty", 0),
                    created_at=odata.get("created_at", 0),
                    filled_at=odata.get("filled_at"),
                )
                self._orders[order.order_id] = order

            logger.info(
                f"Paper: Loaded state — USDT: {self._balances.get('USDT', 0):.2f}, "
                f"{len(self._orders)} orders"
            )

        except Exception as e:
            logger.error(f"Paper: Failed to load state: {e}")
