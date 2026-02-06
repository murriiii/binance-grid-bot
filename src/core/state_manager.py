"""State persistence mixin for GridBot."""

import json
import logging
from datetime import datetime

from src.strategies.grid_strategy import TAKER_FEE_RATE

logger = logging.getLogger("trading_bot")


class StateManagerMixin:
    """Mixin providing state persistence methods for GridBot.

    Expects the host class to have: active_orders, symbol, config, state_file,
    client, stop_loss_manager, memory, telegram, _pending_followups,
    _save_trade_to_memory(), _create_stop_loss().
    """

    def save_state(self):
        """Speichert Bot-State für Neustart - mit Error-Handling"""
        try:
            serializable_orders = {str(k): v for k, v in self.active_orders.items()}

            state = {
                "timestamp": datetime.now().isoformat(),
                "symbol": self.symbol,
                "active_orders": serializable_orders,
                "config": {
                    "symbol": self.config.get("symbol"),
                    "investment": self.config.get("investment"),
                    "num_grids": self.config.get("num_grids"),
                    "grid_range_percent": self.config.get("grid_range_percent"),
                    "testnet": self.config.get("testnet"),
                },
            }

            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            temp_file.replace(self.state_file)

        except Exception as e:
            logger.exception(f"Fehler beim Speichern des States: {e}")

    def load_state(self) -> bool:
        """Lädt und validiert vorherigen State - mit Binance-Verifizierung"""
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file) as f:
                state = json.load(f)

            saved_config = state.get("config", {})
            if saved_config.get("symbol") != self.config.get("symbol"):
                logger.warning("Symbol hat sich geändert - cancele alte Orders und starte frisch")
                self._cancel_orphaned_orders(saved_config.get("symbol"))
                return False

            if saved_config.get("investment") != self.config.get("investment"):
                logger.warning(
                    "Investment hat sich geändert - cancele alte Orders und starte frisch"
                )
                self._cancel_orphaned_orders(self.config.get("symbol"))
                return False

            loaded_orders = state.get("active_orders", {})
            validated_orders = {}

            for order_id_str, order_info in loaded_orders.items():
                try:
                    order_id = int(order_id_str)

                    binance_status = self.client.get_order_status(self.symbol, order_id)

                    if not binance_status:
                        logger.warning(f"Order {order_id} nicht bei Binance gefunden")
                        continue

                    status = binance_status.get("status", "")
                    executed_qty = float(binance_status.get("executedQty", 0))

                    if status == "NEW":
                        validated_orders[order_id] = order_info
                        logger.info(f"Order {order_id} validiert: noch offen")

                    elif status == "FILLED":
                        filled_price = float(
                            binance_status.get("price", order_info.get("price", 0))
                        )
                        filled_qty = (
                            executed_qty
                            if executed_qty > 0
                            else float(order_info.get("quantity", 0))
                        )
                        fee_usd = filled_price * filled_qty * float(TAKER_FEE_RATE)

                        logger.info(
                            f"Order {order_id} während Downtime gefüllt: "
                            f"{order_info.get('type')} @ {filled_price} x {filled_qty}"
                        )
                        self._save_trade_to_memory(order_info, filled_price, filled_qty, fee_usd)

                        if order_info.get("type") == "BUY" and self.stop_loss_manager:
                            fee_adjusted_qty = filled_qty * (1 - float(TAKER_FEE_RATE))
                            self._create_stop_loss(filled_price, fee_adjusted_qty)

                        self._pending_followups.append(
                            {
                                "type": order_info.get("type"),
                                "price": filled_price,
                                "quantity": filled_qty,
                            }
                        )

                        self.telegram.send(
                            f"🔄 Downtime-Fill erkannt\n"
                            f"Typ: {order_info.get('type')}\n"
                            f"Preis: {filled_price:.2f}\n"
                            f"Menge: {filled_qty}"
                        )

                    elif status == "CANCELED" and executed_qty > 0:
                        filled_price = float(
                            binance_status.get("price", order_info.get("price", 0))
                        )
                        fee_usd = filled_price * executed_qty * float(TAKER_FEE_RATE)

                        logger.info(
                            f"Order {order_id} canceled mit Partial Fill während Downtime: "
                            f"{executed_qty} of {order_info.get('quantity')}"
                        )
                        self._save_trade_to_memory(order_info, filled_price, executed_qty, fee_usd)

                        if order_info.get("type") == "BUY" and self.stop_loss_manager:
                            fee_adjusted_qty = executed_qty * (1 - float(TAKER_FEE_RATE))
                            self._create_stop_loss(filled_price, fee_adjusted_qty)

                    elif status == "PARTIALLY_FILLED":
                        logger.info(f"Order {order_id} teilweise gefüllt ({executed_qty})")
                        order_info["executed_qty"] = executed_qty
                        validated_orders[order_id] = order_info

                    else:
                        logger.info(f"Order {order_id} Status: {status} - wird entfernt")

                except Exception as e:
                    logger.warning(f"Konnte Order {order_id_str} nicht validieren: {e}")

            self.active_orders = validated_orders
            logger.info(
                f"State geladen: {len(validated_orders)}/{len(loaded_orders)} Orders validiert"
            )

            return len(validated_orders) > 0

        except json.JSONDecodeError as e:
            logger.error(f"State-Datei korrupt (ungültiges JSON): {e} - starte frisch")
            self.active_orders = {}
            return False

        except Exception as e:
            logger.exception(f"Fehler beim Laden des States: {e}")
            self.active_orders = {}
            return False

    def _cancel_orphaned_orders(self, symbol: str | None) -> None:
        """Cancel all open orders for a symbol to prevent orphaned orders."""
        if not symbol:
            return
        try:
            open_orders = self.client.get_open_orders(symbol)
            if not open_orders:
                return
            for order in open_orders:
                order_id = order.get("orderId")
                if order_id:
                    self.client.cancel_order(symbol, order_id)
                    logger.info(f"Orphaned Order {order_id} für {symbol} gecancelt")
            logger.info(f"{len(open_orders)} orphaned Orders für {symbol} gecancelt")
        except Exception as e:
            logger.warning(f"Fehler beim Canceln orphaned Orders für {symbol}: {e}")
