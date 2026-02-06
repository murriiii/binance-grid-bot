"""Order lifecycle mixin for GridBot."""

import logging
from datetime import datetime, timedelta

from src.api.http_client import HTTPClientError, get_http_client
from src.strategies.grid_strategy import TAKER_FEE_RATE

logger = logging.getLogger("trading_bot")

# Follow-up retry config
MAX_FOLLOWUP_RETRIES = 5
FOLLOWUP_BACKOFF_MINUTES = [2, 5, 15, 30, 60]


class OrderManagerMixin:
    """Mixin providing order management methods for GridBot.

    Expects the host class to have: client, symbol, strategy, symbol_info,
    active_orders, memory, stop_loss_manager, telegram, _pending_followups,
    _validate_order_risk(), _create_stop_loss().
    """

    def place_initial_orders(self):
        """Platziert die initialen Grid-Orders"""
        try:
            current_price = self.client.get_current_price(self.symbol)
            if not current_price or current_price <= 0:
                logger.error(f"Cannot place initial orders: invalid price ({current_price})")
                return
            orders = self.strategy.get_initial_orders(current_price)

            placed_count = 0
            failed_count = 0

            logger.info(f"Platziere {len(orders['buy_orders'])} Buy-Orders")

            for order in orders["buy_orders"]:
                notional = order["quantity"] * order["price"]

                if notional < self.symbol_info["min_notional"]:
                    logger.warning(
                        f"Order zu klein (Notional: {notional:.2f}): "
                        f"{order['price']} x {order['quantity']}"
                    )
                    continue

                if order["quantity"] < self.symbol_info["min_qty"]:
                    logger.warning(
                        f"Quantity zu klein ({order['quantity']} < {self.symbol_info['min_qty']})"
                    )
                    continue

                # Risk validation
                allowed, reason = self._validate_order_risk(
                    "BUY", float(order["quantity"]), float(order["price"])
                )
                if not allowed:
                    logger.warning(f"Order blocked by risk check: {reason}")
                    failed_count += 1
                    continue

                result = self.client.place_limit_buy(self.symbol, order["quantity"], order["price"])

                if result["success"]:
                    order_id = result["order"]["orderId"]
                    self.active_orders[order_id] = {
                        "type": "BUY",
                        "price": order["price"],
                        "quantity": order["quantity"],
                        "created_at": datetime.now().isoformat(),
                    }
                    logger.info(f"Buy Order platziert: {order['price']:.2f} x {order['quantity']}")
                    placed_count += 1
                else:
                    logger.warning(f"Order fehlgeschlagen: {result.get('error', 'Unknown error')}")
                    failed_count += 1

            logger.info(
                f"Orders platziert: {placed_count} erfolgreich, {failed_count} fehlgeschlagen"
            )

            if placed_count > 0:
                self.telegram.send(f"📊 {placed_count} Grid-Orders platziert")

        except Exception as e:
            logger.exception(f"Fehler beim Platzieren der Orders: {e}")

    def check_orders(self):
        """Prüft Status der Orders und reagiert auf Fills - mit Race Condition Fix"""
        try:
            open_orders = self.client.get_open_orders(self.symbol)
            open_order_ids = {o["orderId"] for o in open_orders}

            for order_id, order_info in list(self.active_orders.items()):
                # Handle failed follow-up retries separately
                if order_info.get("failed_followup"):
                    self._retry_failed_followup(order_id, order_info)
                    continue

                if order_id not in open_order_ids:
                    order_status = self.client.get_order_status(self.symbol, order_id)

                    if not order_status:
                        logger.warning(f"Konnte Status für Order {order_id} nicht abrufen")
                        continue

                    status = order_status.get("status", "")
                    executed_qty = float(order_status.get("executedQty", 0))

                    if status == "PARTIALLY_FILLED":
                        logger.info(
                            f"Order {order_id} partially filled "
                            f"({executed_qty}/{order_info['quantity']}) - weiter tracken"
                        )
                        order_info["executed_qty"] = executed_qty
                        continue

                    if status == "CANCELED" and executed_qty > 0:
                        logger.info(
                            f"Order {order_id} canceled with partial fill: "
                            f"{executed_qty} of {order_info['quantity']}"
                        )
                        self._process_partial_fill(order_id, order_info, order_status)
                        continue

                    if status in ("CANCELED", "EXPIRED", "REJECTED", "PENDING_CANCEL"):
                        logger.info(f"Order {order_id} Status: {status} - wird entfernt")
                        del self.active_orders[order_id]
                        continue

                    if status != "FILLED":
                        logger.warning(
                            f"Order {order_id} unbekannter Status: {status} - wird entfernt"
                        )
                        del self.active_orders[order_id]
                        continue

                    # Order wurde vollständig gefüllt!
                    filled_price = float(order_status.get("price", order_info["price"]))
                    filled_qty = executed_qty if executed_qty > 0 else float(order_info["quantity"])

                    logger.info(
                        f"Order gefüllt: {order_info['type']} @ {filled_price} x {filled_qty}"
                    )

                    emoji = "🟢" if order_info["type"] == "BUY" else "🔴"
                    self.telegram.send(
                        f"{emoji} Order gefüllt\n"
                        f"Typ: {order_info['type']}\n"
                        f"Preis: {filled_price:.2f}\n"
                        f"Menge: {filled_qty}"
                    )

                    fee_usd = filled_price * filled_qty * float(TAKER_FEE_RATE)
                    trade_id = self._save_trade_to_memory(
                        order_info, filled_price, filled_qty, fee_usd
                    )

                    # Track trade pair
                    if self._trade_pair_tracker:
                        if order_info["type"] == "BUY":
                            self._trade_pair_tracker.open_pair(
                                self.symbol, trade_id, filled_price, filled_qty, fee_usd
                            )
                        else:
                            self._trade_pair_tracker.close_pair(
                                self.symbol, trade_id, filled_price, filled_qty, fee_usd
                            )

                    if order_info["type"] == "BUY" and self.stop_loss_manager:
                        fee_adjusted_qty = filled_qty * (1 - float(TAKER_FEE_RATE))
                        self._create_stop_loss(filled_price, fee_adjusted_qty)

                    if order_info["type"] == "BUY":
                        action = self.strategy.on_buy_filled(filled_price)
                    else:
                        action = self.strategy.on_sell_filled(filled_price)

                    action_type = action.get("action", "NONE")

                    if action_type == "NONE":
                        logger.info(f"Keine Folge-Aktion für {order_info['type']} @ {filled_price}")
                        del self.active_orders[order_id]
                        continue

                    new_order_placed = False
                    new_order_id = None

                    if action_type == "PLACE_SELL":
                        allowed, reason = self._validate_order_risk(
                            "SELL", float(action["quantity"]), float(action["price"])
                        )
                        if not allowed:
                            logger.warning(f"Follow-up SELL blocked by risk check: {reason}")
                            self.telegram.send(
                                f"Follow-up SELL blocked\nSymbol: {self.symbol}\nReason: {reason}"
                            )
                        else:
                            result = self.client.place_limit_sell(
                                self.symbol, action["quantity"], action["price"]
                            )
                            if result["success"]:
                                new_order_id = result["order"]["orderId"]
                                self.active_orders[new_order_id] = {
                                    "type": "SELL",
                                    "price": action["price"],
                                    "quantity": action["quantity"],
                                    "created_at": datetime.now().isoformat(),
                                }
                                new_order_placed = True
                                logger.info(
                                    f"Sell Order platziert: "
                                    f"{action['price']:.2f} x {action['quantity']}"
                                )
                            else:
                                logger.error(f"Sell Order fehlgeschlagen: {result.get('error')}")

                    elif action_type == "PLACE_BUY":
                        allowed, reason = self._validate_order_risk(
                            "BUY", float(action["quantity"]), float(action["price"])
                        )
                        if not allowed:
                            logger.warning(f"Follow-up BUY blocked by risk check: {reason}")
                            self.telegram.send(
                                f"Follow-up BUY blocked\nSymbol: {self.symbol}\nReason: {reason}"
                            )
                        else:
                            result = self.client.place_limit_buy(
                                self.symbol, action["quantity"], action["price"]
                            )
                            if result["success"]:
                                new_order_id = result["order"]["orderId"]
                                self.active_orders[new_order_id] = {
                                    "type": "BUY",
                                    "price": action["price"],
                                    "quantity": action["quantity"],
                                    "created_at": datetime.now().isoformat(),
                                }
                                new_order_placed = True
                                logger.info(
                                    f"Buy Order platziert: "
                                    f"{action['price']:.2f} x {action['quantity']}"
                                )
                            else:
                                logger.error(f"Buy Order fehlgeschlagen: {result.get('error')}")

                    if new_order_placed or action_type == "NONE":
                        del self.active_orders[order_id]
                    else:
                        retry_count = order_info.get("retry_count", 0)
                        backoff_idx = min(retry_count, len(FOLLOWUP_BACKOFF_MINUTES) - 1)
                        next_retry = datetime.now() + timedelta(
                            minutes=FOLLOWUP_BACKOFF_MINUTES[backoff_idx]
                        )
                        logger.warning(
                            f"Folge-Order fehlgeschlagen (Versuch {retry_count + 1}/"
                            f"{MAX_FOLLOWUP_RETRIES}), nächster Retry: {next_retry:%H:%M}"
                        )
                        self.active_orders[order_id]["failed_followup"] = True
                        self.active_orders[order_id]["intended_action"] = action
                        self.active_orders[order_id]["retry_count"] = retry_count + 1
                        self.active_orders[order_id]["next_retry_after"] = next_retry.isoformat()

        except Exception as e:
            logger.exception(f"Fehler in check_orders: {e}")
            raise

    def _process_partial_fill(self, order_id: int, order_info: dict, order_status: dict):
        """
        Verarbeitet eine teilweise gefüllte und dann stornierte Order.

        - Speichert den gefüllten Teil als Trade
        - Erstellt Stop-Loss für BUY-Partial-Fills
        - Entfernt die Order aus active_orders
        - Platziert KEINE Follow-up-Order
        """
        filled_price = float(order_status.get("price", order_info["price"]))
        filled_qty = float(order_status.get("executedQty", 0))

        if filled_qty <= 0:
            del self.active_orders[order_id]
            return

        fee_usd = filled_price * filled_qty * float(TAKER_FEE_RATE)

        logger.info(
            f"Partial fill verarbeitet: {order_info['type']} "
            f"@ {filled_price:.2f} x {filled_qty} (fee: ${fee_usd:.4f})"
        )

        self.telegram.send(
            f"⚠️ Partial Fill\n"
            f"Typ: {order_info['type']}\n"
            f"Preis: {filled_price:.2f}\n"
            f"Menge: {filled_qty} / {order_info['quantity']}\n"
            f"Status: Canceled nach Partial Fill"
        )

        trade_id = self._save_trade_to_memory(order_info, filled_price, filled_qty, fee_usd)

        # Track trade pair for partial fills
        if self._trade_pair_tracker and order_info["type"] == "BUY":
            self._trade_pair_tracker.open_pair(
                self.symbol, trade_id, filled_price, filled_qty, fee_usd
            )

        if order_info["type"] == "BUY" and self.stop_loss_manager:
            fee_adjusted_qty = filled_qty * (1 - float(TAKER_FEE_RATE))
            self._create_stop_loss(filled_price, fee_adjusted_qty)

        del self.active_orders[order_id]

    def _retry_failed_followup(self, order_id: int, order_info: dict):
        """Retry a failed follow-up order with exponential backoff."""
        retry_count = order_info.get("retry_count", 0)
        next_retry_str = order_info.get("next_retry_after")

        # Check if max retries exceeded
        if retry_count >= MAX_FOLLOWUP_RETRIES:
            logger.critical(
                f"Follow-up für Order {order_id} nach {retry_count} Versuchen aufgegeben"
            )
            self.telegram.send(
                f"🚨 CRITICAL: Follow-up aufgegeben\n"
                f"Order: {order_id}\n"
                f"Typ: {order_info.get('type')}\n"
                f"Preis: {order_info.get('price')}\n"
                f"Versuche: {retry_count}/{MAX_FOLLOWUP_RETRIES}",
                urgent=True,
            )
            del self.active_orders[order_id]
            return

        # Check backoff timer
        if next_retry_str:
            next_retry = datetime.fromisoformat(next_retry_str)
            if datetime.now() < next_retry:
                return  # Not yet time to retry

        action = order_info.get("intended_action", {})
        action_type = action.get("action", "NONE")
        if action_type == "NONE":
            del self.active_orders[order_id]
            return

        logger.info(
            f"Retry Follow-up für Order {order_id} "
            f"(Versuch {retry_count + 1}/{MAX_FOLLOWUP_RETRIES})"
        )

        result = {"success": False}
        side = "SELL" if action_type == "PLACE_SELL" else "BUY"

        allowed, reason = self._validate_order_risk(
            side, float(action["quantity"]), float(action["price"])
        )
        if not allowed:
            logger.warning(f"Follow-up retry blocked by risk check: {reason}")
        elif action_type == "PLACE_SELL":
            result = self.client.place_limit_sell(self.symbol, action["quantity"], action["price"])
        elif action_type == "PLACE_BUY":
            result = self.client.place_limit_buy(self.symbol, action["quantity"], action["price"])

        if result["success"]:
            new_order_id = result["order"]["orderId"]
            self.active_orders[new_order_id] = {
                "type": side,
                "price": action["price"],
                "quantity": action["quantity"],
                "created_at": datetime.now().isoformat(),
            }
            del self.active_orders[order_id]
            logger.info(f"Follow-up retry erfolgreich: {side} @ {action['price']}")
        else:
            backoff_idx = min(retry_count, len(FOLLOWUP_BACKOFF_MINUTES) - 1)
            next_retry = datetime.now() + timedelta(minutes=FOLLOWUP_BACKOFF_MINUTES[backoff_idx])
            self.active_orders[order_id]["retry_count"] = retry_count + 1
            self.active_orders[order_id]["next_retry_after"] = next_retry.isoformat()
            logger.warning(f"Follow-up retry fehlgeschlagen, nächster Versuch: {next_retry:%H:%M}")

    def _save_trade_to_memory(
        self, order_info: dict, price: float, quantity: float, fee_usd: float = 0.0
    ) -> int | None:
        """Speichert einen Trade im Memory-System.  Returns trade_id or None."""
        if not self.memory:
            return None

        try:
            from src.data.memory import TradeRecord

            fear_greed = self._get_current_fear_greed()
            btc_price = (
                self.client.get_current_price("BTCUSDT") if self.symbol != "BTCUSDT" else price
            )

            trade_record = TradeRecord(
                timestamp=datetime.now(),
                action=order_info["type"],
                symbol=self.symbol,
                price=price,
                quantity=quantity,
                value_usd=price * quantity,
                fear_greed=fear_greed,
                btc_price=btc_price,
                symbol_24h_change=0.0,
                market_trend="NEUTRAL",
                math_signal="GRID",
                ai_signal="N/A",
                reasoning=f"Grid order filled at {price} (fee: ${fee_usd:.4f})",
                fee_usd=fee_usd,
            )

            trade_id = self.memory.save_trade(trade_record)
            logger.info(f"Trade in Memory gespeichert: ID {trade_id} (fee: ${fee_usd:.4f})")

            # Store signal breakdown for this trade
            if trade_id and trade_id > 0:
                try:
                    from src.analysis.signal_analyzer import SignalAnalyzer

                    analyzer = SignalAnalyzer.get_instance()
                    signals = analyzer.compute_all_signals(
                        {"fear_greed": fear_greed, "price": price}
                    )
                    analyzer.store_signals(
                        trade_id=str(trade_id),
                        cohort_id=self.config.get("cohort_id"),
                        signals=signals,
                    )
                except Exception:
                    pass  # Non-critical, graceful degradation

            return trade_id if trade_id and trade_id > 0 else None

        except Exception as e:
            logger.warning(f"Konnte Trade nicht in Memory speichern: {e}")
            return None

    def _get_current_fear_greed(self) -> int:
        """Holt den aktuellen Fear & Greed Index"""
        try:
            http = get_http_client()
            data = http.get("https://api.alternative.me/fng/")
            return int(data["data"][0]["value"])
        except HTTPClientError as e:
            logger.warning(f"Fear & Greed API error: {e}")
        return 50

    def _process_pending_followups(self):
        """
        Verarbeitet Follow-up-Orders von während der Downtime gefüllten Orders.

        Wird nach load_state() aufgerufen, wenn self.strategy verfügbar ist.
        """
        if not self._pending_followups or not self.strategy:
            return

        logger.info(f"Verarbeite {len(self._pending_followups)} Downtime-Fills")

        for fill in self._pending_followups:
            try:
                if fill["type"] == "BUY":
                    action = self.strategy.on_buy_filled(fill["price"])
                else:
                    action = self.strategy.on_sell_filled(fill["price"])

                action_type = action.get("action", "NONE")
                if action_type == "NONE":
                    logger.info(
                        f"Keine Folge-Aktion für Downtime-Fill {fill['type']} @ {fill['price']}"
                    )
                    continue

                side = "SELL" if action_type == "PLACE_SELL" else "BUY"
                allowed, reason = self._validate_order_risk(
                    side, float(action["quantity"]), float(action["price"])
                )
                if not allowed:
                    logger.warning(f"Downtime follow-up blocked by risk check: {reason}")
                    continue

                if action_type == "PLACE_SELL":
                    result = self.client.place_limit_sell(
                        self.symbol, action["quantity"], action["price"]
                    )
                else:
                    result = self.client.place_limit_buy(
                        self.symbol, action["quantity"], action["price"]
                    )

                if result["success"]:
                    order_id = result["order"]["orderId"]
                    self.active_orders[order_id] = {
                        "type": side,
                        "price": action["price"],
                        "quantity": action["quantity"],
                        "created_at": datetime.now().isoformat(),
                    }
                    logger.info(
                        f"Downtime follow-up {side} platziert: "
                        f"{action['price']} x {action['quantity']}"
                    )
                else:
                    logger.error(f"Downtime follow-up fehlgeschlagen: {result.get('error')}")

            except Exception as e:
                logger.warning(f"Fehler bei Downtime follow-up: {e}")

        self._pending_followups.clear()
