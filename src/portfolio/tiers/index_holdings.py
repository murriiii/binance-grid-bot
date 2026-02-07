"""Index Holdings Tier - ETF-style buy-and-hold of top cryptocurrencies."""

import logging
from dataclasses import dataclass, field

from psycopg2.extras import RealDictCursor

logger = logging.getLogger("trading_bot")

# Stablecoins and wrapped tokens to exclude from index
EXCLUDED_SYMBOLS = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "FDUSD",
    "WBTC",
    "WETH",
    "STETH",
    "WBETH",
}


@dataclass
class IndexHolding:
    """A single index position."""

    symbol: str
    target_weight_pct: float
    current_weight_pct: float = 0.0
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    market_cap_rank: int = 0
    trailing_stop_price: float = 0.0
    highest_price: float = 0.0

    @property
    def value_usd(self) -> float:
        return self.quantity * self.current_price if self.current_price > 0 else 0.0

    @property
    def pnl_pct(self) -> float:
        if self.avg_entry_price > 0:
            return ((self.current_price - self.avg_entry_price) / self.avg_entry_price) * 100
        return 0.0


@dataclass
class IndexStatus:
    """Current state of the index holdings tier."""

    total_value_usd: float
    target_value_usd: float
    holding_count: int
    holdings: list[IndexHolding] = field(default_factory=list)
    needs_rebalance: bool = False
    last_rebalance_days_ago: int | None = None


class IndexHoldingsTier:
    """ETF-style buy-and-hold tier with top cryptocurrencies.

    - Composition: Top 20 by market cap (stablecoins excluded)
    - Rebalance: Quarterly (every 90 days)
    - Trailing stops: 15% per position
    - Max single position: 30%
    - Min position size: $10 (Binance min_notional)
    """

    REBALANCE_INTERVAL_DAYS = 90
    TRAILING_STOP_PCT = 15.0
    MAX_SINGLE_POSITION_PCT = 30.0
    MIN_POSITION_USD = 10.0
    TOP_N = 20

    def __init__(self, client, conn=None, target_pct: float = 65.0):
        self.client = client
        self.conn = conn
        self.target_pct = target_pct
        self._holdings: dict[str, IndexHolding] = {}

    def load_holdings(self) -> dict[str, IndexHolding]:
        """Load current holdings from DB."""
        if not self.conn:
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT symbol, target_weight_pct, current_weight_pct,
                           quantity, avg_entry_price, current_price,
                           trailing_stop_price, highest_price, market_cap_rank
                    FROM index_holdings
                    WHERE is_active = TRUE
                """)
                for row in cur.fetchall():
                    self._holdings[row["symbol"]] = IndexHolding(
                        symbol=row["symbol"],
                        target_weight_pct=float(row["target_weight_pct"] or 0),
                        current_weight_pct=float(row["current_weight_pct"] or 0),
                        quantity=float(row["quantity"] or 0),
                        avg_entry_price=float(row["avg_entry_price"] or 0),
                        current_price=float(row["current_price"] or 0),
                        market_cap_rank=row["market_cap_rank"] or 0,
                        trailing_stop_price=float(row["trailing_stop_price"] or 0),
                        highest_price=float(row["highest_price"] or 0),
                    )
        except Exception as e:
            logger.error(f"Failed to load index holdings: {e}")

        return self._holdings

    def get_top20_composition(self) -> list[dict]:
        """Fetch top 20 crypto by market cap from CoinGecko.

        Returns list of {"symbol": "BTC", "weight_pct": 35.2, "rank": 1}
        """
        try:
            from src.data.market_cap import get_top_coins_by_market_cap

            coins = get_top_coins_by_market_cap(self.TOP_N)

            # Filter excluded and cap at MAX_SINGLE_POSITION_PCT
            filtered = [c for c in coins if c["symbol"].upper() not in EXCLUDED_SYMBOLS]

            # Recalculate weights after filtering + cap
            total_mcap = sum(c["market_cap"] for c in filtered)
            if total_mcap <= 0:
                return []

            result = []
            for c in filtered:
                weight = (c["market_cap"] / total_mcap) * 100
                weight = min(weight, self.MAX_SINGLE_POSITION_PCT)
                result.append(
                    {
                        "symbol": c["symbol"].upper() + "USDT",
                        "weight_pct": weight,
                        "rank": c["rank"],
                    }
                )

            # Normalize weights to sum to 100
            total_weight = sum(r["weight_pct"] for r in result)
            if total_weight > 0:
                for r in result:
                    r["weight_pct"] = (r["weight_pct"] / total_weight) * 100

            return result

        except Exception as e:
            logger.error(f"Failed to fetch top 20 composition: {e}")
            return []

    def calculate_rebalance_orders(
        self, target_composition: list[dict], available_capital: float
    ) -> list[dict]:
        """Calculate buy/sell orders needed to match target composition.

        Returns list of {"symbol": str, "action": "BUY"|"SELL", "amount_usd": float}
        """
        orders = []

        # Current holdings by symbol
        current = {s: h.value_usd for s, h in self._holdings.items()}

        for target in target_composition:
            symbol = target["symbol"]
            target_usd = available_capital * (target["weight_pct"] / 100)
            current_usd = current.get(symbol, 0)
            diff = target_usd - current_usd

            if abs(diff) < self.MIN_POSITION_USD:
                continue

            if diff > 0:
                orders.append({"symbol": symbol, "action": "BUY", "amount_usd": diff})
            elif diff < 0:
                orders.append({"symbol": symbol, "action": "SELL", "amount_usd": abs(diff)})

        # Sell positions not in target
        target_symbols = {t["symbol"] for t in target_composition}
        for symbol, holding in self._holdings.items():
            if symbol not in target_symbols and holding.value_usd > self.MIN_POSITION_USD:
                orders.append(
                    {
                        "symbol": symbol,
                        "action": "SELL",
                        "amount_usd": holding.value_usd,
                    }
                )

        return orders

    def update_trailing_stops(self) -> list[str]:
        """Update trailing stops and return symbols that triggered.

        For each holding: if current_price > highest_price, update highest
        and trailing stop. If current_price <= trailing_stop, return as triggered.
        """
        triggered = []

        for symbol, holding in self._holdings.items():
            if holding.quantity <= 0 or holding.current_price <= 0:
                continue

            # Update highest price
            if holding.current_price > holding.highest_price:
                holding.highest_price = holding.current_price
                holding.trailing_stop_price = holding.current_price * (
                    1 - self.TRAILING_STOP_PCT / 100
                )

            # Check trigger
            if (
                holding.trailing_stop_price > 0
                and holding.current_price <= holding.trailing_stop_price
            ):
                triggered.append(symbol)

        return triggered

    def save_holdings(self):
        """Persist current holdings to DB."""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                for symbol, h in self._holdings.items():
                    cur.execute(
                        """
                        INSERT INTO index_holdings
                            (symbol, target_weight_pct, current_weight_pct,
                             quantity, avg_entry_price, current_price,
                             trailing_stop_price, highest_price, market_cap_rank)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol) DO UPDATE SET
                            target_weight_pct = EXCLUDED.target_weight_pct,
                            current_weight_pct = EXCLUDED.current_weight_pct,
                            quantity = EXCLUDED.quantity,
                            current_price = EXCLUDED.current_price,
                            trailing_stop_price = EXCLUDED.trailing_stop_price,
                            highest_price = EXCLUDED.highest_price,
                            market_cap_rank = EXCLUDED.market_cap_rank,
                            updated_at = NOW()
                        """,
                        (
                            symbol,
                            h.target_weight_pct,
                            h.current_weight_pct,
                            h.quantity,
                            h.avg_entry_price,
                            h.current_price,
                            h.trailing_stop_price,
                            h.highest_price,
                            h.market_cap_rank,
                        ),
                    )
                self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save index holdings: {e}")

    def get_status(self, total_portfolio_value: float) -> IndexStatus:
        """Return current index tier status."""
        total_value = sum(h.value_usd for h in self._holdings.values())
        target_value = total_portfolio_value * (self.target_pct / 100)

        return IndexStatus(
            total_value_usd=total_value,
            target_value_usd=target_value,
            holding_count=len([h for h in self._holdings.values() if h.quantity > 0]),
            holdings=list(self._holdings.values()),
        )

    def get_total_value(self) -> float:
        """Return total value of all index holdings."""
        return sum(h.value_usd for h in self._holdings.values())
