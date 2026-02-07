"""Grid Trading Strategy - mit min_qty Validierung und Decimal-Präzision"""

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# Binance standard taker fee (0.1%). With BNB discount: 0.075%
TAKER_FEE_RATE = Decimal("0.001")

# D1: Round-trip fee = 2x taker fee (buy + sell)
ROUND_TRIP_FEE_RATE = TAKER_FEE_RATE * 2  # 0.2%

# D1: Minimum profitable spacing = round-trip fee + safety margin
MIN_PROFITABLE_SPACING_PCT = float(ROUND_TRIP_FEE_RATE) * 100 * 1.5  # 0.3%

logger = logging.getLogger("trading_bot")


def _to_decimal(value: float | int | str | Decimal) -> Decimal:
    """Convert to Decimal without float precision artifacts.

    Uses str(value) which gives the shortest correct representation.
    Decimal() handles scientific notation strings (e.g. '1e-05') natively.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass
class GridLevel:
    price: Decimal
    buy_order_id: int | None = None
    sell_order_id: int | None = None
    filled: bool = False
    quantity: Decimal = Decimal("0")
    valid: bool = True

    def __post_init__(self):
        if not isinstance(self.price, Decimal):
            self.price = _to_decimal(self.price)
        if not isinstance(self.quantity, Decimal):
            self.quantity = _to_decimal(self.quantity)


class GridStrategy:
    def __init__(
        self,
        lower_price: float | Decimal,
        upper_price: float | Decimal,
        num_grids: int,
        total_investment: float | Decimal,
        symbol_info: dict,
        fee_rate: float | Decimal | None = None,
    ):
        self.lower_price = _to_decimal(lower_price)
        self.upper_price = _to_decimal(upper_price)
        self.num_grids = num_grids
        self.total_investment = _to_decimal(total_investment)
        self.symbol_info = symbol_info
        self.fee_rate = _to_decimal(fee_rate) if fee_rate is not None else TAKER_FEE_RATE
        self._step_size = _to_decimal(symbol_info.get("step_size", "0.00001"))
        self.levels: list[GridLevel] = []
        self.skipped_levels = 0

        self._calculate_grid_levels()

    @classmethod
    def get_min_profitable_spacing(cls) -> float:
        """D1: Returns minimum profitable grid spacing in percent."""
        return MIN_PROFITABLE_SPACING_PCT

    def _calculate_grid_levels(self):
        """Berechnet die Grid-Ebenen mit min_qty und min_notional Validierung"""
        price_range = self.upper_price - self.lower_price
        grid_spacing = price_range / self.num_grids

        # D1: Fee-aware spacing check
        mid_price = (self.lower_price + self.upper_price) / 2
        spacing_pct = float(grid_spacing / mid_price) * 100 if mid_price > 0 else 0
        if spacing_pct < MIN_PROFITABLE_SPACING_PCT:
            logger.warning(
                f"Grid spacing {spacing_pct:.3f}% is below minimum profitable "
                f"spacing {MIN_PROFITABLE_SPACING_PCT:.3f}% (round-trip fees). "
                f"Trades may not cover fees."
            )

        investment_per_grid = self.total_investment / self.num_grids

        min_qty = _to_decimal(self.symbol_info.get("min_qty", 0))
        step_size = _to_decimal(self.symbol_info.get("step_size", "0.00001"))
        min_notional = _to_decimal(self.symbol_info.get("min_notional", 10))
        tick_size = _to_decimal(self.symbol_info.get("tick_size", "0.01"))

        for i in range(self.num_grids + 1):
            price = self.lower_price + (Decimal(i) * grid_spacing)
            quantity = investment_per_grid / price

            # Round quantity down to step_size (Decimal division prevents float drift)
            quantity = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size
            # Ensure no scientific notation in Decimal repr (e.g., 2E+6 → 2000000)
            quantity = Decimal(format(quantity, "f"))

            if quantity < min_qty:
                logger.warning(
                    f"Grid Level {i} übersprungen: Quantity {quantity} < min_qty {min_qty}"
                )
                self.skipped_levels += 1
                continue

            notional = quantity * price
            if notional < min_notional:
                logger.warning(
                    f"Grid Level {i} übersprungen: Notional {notional} < min_notional {min_notional}"
                )
                self.skipped_levels += 1
                continue

            # Round price down to tick_size
            rounded_price = (price / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size
            rounded_price = Decimal(format(rounded_price, "f"))

            self.levels.append(GridLevel(price=rounded_price, quantity=quantity, valid=True))

        if len(self.levels) < 2:
            logger.error(
                f"Nur {len(self.levels)} gültige Grid-Levels! "
                f"Investment möglicherweise zu klein oder Limits zu hoch."
            )

        logger.info(
            f"Grid berechnet: {len(self.levels)} gültige Levels, {self.skipped_levels} übersprungen"
        )

    def get_initial_orders(self, current_price: float | Decimal) -> dict:
        """
        Gibt initiale Orders zurück.
        Buy-Orders unter aktuellem Preis, Sell-Orders darüber.
        """
        current_price = _to_decimal(current_price)
        buy_orders = []
        sell_orders = []

        for level in self.levels:
            if level.price < current_price:
                buy_orders.append({"price": level.price, "quantity": level.quantity, "type": "BUY"})
            elif level.price > current_price:
                sell_orders.append(
                    {"price": level.price, "quantity": level.quantity, "type": "SELL"}
                )

        return {"buy_orders": buy_orders, "sell_orders": sell_orders}

    def _apply_buy_fee(self, quantity: Decimal) -> Decimal:
        """Reduce quantity by taker fee and round down to step_size.

        After a BUY fill, Binance deducts the fee from the received asset.
        E.g. BUY 0.001 BTC with 0.1% fee → you receive 0.000999 BTC.
        The SELL quantity must not exceed what you actually hold.
        """
        qty_after_fee = quantity * (Decimal("1") - self.fee_rate)
        rounded = (qty_after_fee / self._step_size).to_integral_value(
            rounding=ROUND_DOWN
        ) * self._step_size
        return Decimal(format(rounded, "f"))

    def on_buy_filled(self, price: float | Decimal) -> dict:
        """Wenn ein Buy gefüllt wurde, platziere Sell darüber (fee-adjusted)"""
        price = _to_decimal(price)
        for i, level in enumerate(self.levels):
            if level.price > 0 and abs(level.price - price) / level.price < Decimal("0.001"):
                level.filled = True
                if i + 1 < len(self.levels):
                    next_level = self.levels[i + 1]
                    sell_qty = self._apply_buy_fee(level.quantity)
                    return {
                        "action": "PLACE_SELL",
                        "price": next_level.price,
                        "quantity": sell_qty,
                        "fee_qty": level.quantity - sell_qty,
                    }
        return {"action": "NONE"}

    def on_sell_filled(self, price: float | Decimal) -> dict:
        """Wenn ein Sell gefüllt wurde, platziere Buy darunter"""
        price = _to_decimal(price)
        for i, level in enumerate(self.levels):
            if level.price > 0 and abs(level.price - price) / level.price < Decimal("0.001"):
                level.filled = False
                if i - 1 >= 0:
                    prev_level = self.levels[i - 1]
                    return {
                        "action": "PLACE_BUY",
                        "price": prev_level.price,
                        "quantity": prev_level.quantity,
                    }
        return {"action": "NONE"}

    def print_grid(self):
        """Debug: Zeigt das Grid an"""
        logger.info(f"{'=' * 50}")
        logger.info(f"Grid Strategy: {self.lower_price} - {self.upper_price}")
        logger.info(f"Levels: {self.num_grids}, Investment: {self.total_investment}")
        logger.info(f"{'=' * 50}")
        for level in reversed(self.levels):
            status = "●" if level.filled else "○"
            logger.info(f"  {status} {level.price:>10.2f} | Qty: {level.quantity:.8f}")
        logger.info(f"{'=' * 50}")
