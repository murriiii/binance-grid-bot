"""Grid Trading Strategy - mit min_qty Validierung"""
from dataclasses import dataclass
from typing import List
import math
import logging

logger = logging.getLogger('trading_bot')


@dataclass
class GridLevel:
    price: float
    buy_order_id: int = None
    sell_order_id: int = None
    filled: bool = False
    quantity: float = 0.0
    valid: bool = True  # NEU: Flag für gültige Levels


class GridStrategy:
    def __init__(
        self,
        lower_price: float,
        upper_price: float,
        num_grids: int,
        total_investment: float,
        symbol_info: dict
    ):
        self.lower_price = lower_price
        self.upper_price = upper_price
        self.num_grids = num_grids
        self.total_investment = total_investment
        self.symbol_info = symbol_info
        self.levels: List[GridLevel] = []
        self.skipped_levels = 0  # Zählt ungültige Levels

        self._calculate_grid_levels()

    def _calculate_grid_levels(self):
        """Berechnet die Grid-Ebenen mit min_qty und min_notional Validierung"""
        price_range = self.upper_price - self.lower_price
        grid_spacing = price_range / self.num_grids

        # Investment pro Grid-Ebene
        investment_per_grid = self.total_investment / self.num_grids

        # Symbol-Limits
        min_qty = self.symbol_info.get('min_qty', 0)
        step_size = self.symbol_info.get('step_size', 0.00001)
        min_notional = self.symbol_info.get('min_notional', 10)

        for i in range(self.num_grids + 1):
            price = self.lower_price + (i * grid_spacing)
            quantity = investment_per_grid / price

            # Auf step_size runden (abrunden)
            quantity = math.floor(quantity / step_size) * step_size

            # Validierung 1: min_qty Check
            if quantity < min_qty:
                logger.warning(
                    f"Grid Level {i} übersprungen: Quantity {quantity:.8f} < min_qty {min_qty}"
                )
                self.skipped_levels += 1
                continue

            # Validierung 2: min_notional Check
            notional = quantity * price
            if notional < min_notional:
                logger.warning(
                    f"Grid Level {i} übersprungen: Notional {notional:.2f} < min_notional {min_notional}"
                )
                self.skipped_levels += 1
                continue

            # Preis runden (2 Dezimalstellen für die meisten Pairs)
            price_precision = self._get_price_precision()
            rounded_price = round(price, price_precision)

            self.levels.append(GridLevel(
                price=rounded_price,
                quantity=quantity,
                valid=True
            ))

        # Warnung wenn zu wenige gültige Levels
        if len(self.levels) < 2:
            logger.error(
                f"Nur {len(self.levels)} gültige Grid-Levels! "
                f"Investment möglicherweise zu klein oder Limits zu hoch."
            )

        logger.info(
            f"Grid berechnet: {len(self.levels)} gültige Levels, "
            f"{self.skipped_levels} übersprungen"
        )

    def _get_price_precision(self) -> int:
        """Ermittelt die Preispräzision aus dem step_size"""
        # Für die meisten USDT-Pairs sind 2 Dezimalstellen üblich
        # TODO: Könnte aus PRICE_FILTER tickSize extrahiert werden
        return 2

    def get_initial_orders(self, current_price: float) -> dict:
        """
        Gibt initiale Orders zurück.
        Buy-Orders unter aktuellem Preis, Sell-Orders darüber.
        """
        buy_orders = []
        sell_orders = []

        for level in self.levels:
            if level.price < current_price:
                buy_orders.append({
                    'price': level.price,
                    'quantity': level.quantity,
                    'type': 'BUY'
                })
            elif level.price > current_price:
                sell_orders.append({
                    'price': level.price,
                    'quantity': level.quantity,
                    'type': 'SELL'
                })

        return {'buy_orders': buy_orders, 'sell_orders': sell_orders}

    def on_buy_filled(self, price: float) -> dict:
        """Wenn ein Buy gefüllt wurde, platziere Sell darüber"""
        for i, level in enumerate(self.levels):
            if abs(level.price - price) < 0.01:
                level.filled = True
                # Finde nächsthöhere Ebene für Sell
                if i + 1 < len(self.levels):
                    next_level = self.levels[i + 1]
                    return {
                        'action': 'PLACE_SELL',
                        'price': next_level.price,
                        'quantity': level.quantity
                    }
        return {'action': 'NONE'}

    def on_sell_filled(self, price: float) -> dict:
        """Wenn ein Sell gefüllt wurde, platziere Buy darunter"""
        for i, level in enumerate(self.levels):
            if abs(level.price - price) < 0.01:
                level.filled = False
                # Finde nächstniedrigere Ebene für Buy
                if i - 1 >= 0:
                    prev_level = self.levels[i - 1]
                    return {
                        'action': 'PLACE_BUY',
                        'price': prev_level.price,
                        'quantity': prev_level.quantity
                    }
        return {'action': 'NONE'}

    def print_grid(self):
        """Debug: Zeigt das Grid an"""
        logger.info(f"{'='*50}")
        logger.info(f"Grid Strategy: {self.lower_price} - {self.upper_price}")
        logger.info(f"Levels: {self.num_grids}, Investment: {self.total_investment}")
        logger.info(f"{'='*50}")
        for level in reversed(self.levels):
            status = "●" if level.filled else "○"
            logger.info(f"  {status} {level.price:>10.2f} | Qty: {level.quantity:.6f}")
        logger.info(f"{'='*50}")
