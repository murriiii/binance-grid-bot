"""Main Bot Logic - Production Ready"""

import json
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.api.binance_client import BinanceClient
from src.api.http_client import HTTPClientError, get_http_client
from src.strategies.grid_strategy import TAKER_FEE_RATE, GridStrategy


# Logging Setup mit Rotation
def setup_logging():
    """Konfiguriert strukturiertes Logging mit Rotation"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.INFO)

    # Rotating File Handler (10MB, 5 Backups)
    file_handler = RotatingFileHandler(
        log_dir / "bot.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s")
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


class TelegramNotifier:
    """Sendet Benachrichtigungen via Telegram"""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)

    def send(self, message: str, urgent: bool = False):
        """Sendet eine Telegram-Nachricht"""
        if not self.enabled:
            return

        prefix = "🚨 URGENT: " if urgent else ""
        try:
            http = get_http_client()
            http.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": f"{prefix}{message}", "parse_mode": "HTML"},
                api_type="telegram",
            )
        except HTTPClientError as e:
            logger.warning(f"Telegram notification failed: {e}")


class GridBot:
    """Grid Trading Bot mit robustem Error-Handling"""

    # Konfiguration für Fehlerbehandlung
    MAX_CONSECUTIVE_ERRORS = 5
    INITIAL_BACKOFF_SECONDS = 30
    MAX_BACKOFF_SECONDS = 300
    CIRCUIT_BREAKER_PCT = 10.0  # Emergency stop bei >10% Drop pro Check-Zyklus

    def __init__(self, config: dict):
        self.config = config
        self.client = BinanceClient(testnet=config.get("testnet", True))
        self.symbol = config["symbol"]
        self.running = False
        self.strategy = None
        self.active_orders: dict[int, dict[str, Any]] = {}
        self.symbol_info: dict | None = None

        # State file für Persistenz
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        self.state_file = config_dir / "bot_state.json"

        # Telegram Notifier
        self.telegram = TelegramNotifier()

        # Error tracking
        self.consecutive_errors = 0
        self.last_error_time: datetime | None = None

        # Circuit breaker: track last known price
        self._last_known_price: float = 0.0

        # Downtime-fill-recovery: queued follow-up actions from load_state()
        self._pending_followups: list[dict] = []

        # Optional: Memory System (wird in Phase 2 aktiviert)
        self.memory = None
        self._init_memory()

        # Optional: Stop-Loss Manager (wird in Phase 2 aktiviert)
        self.stop_loss_manager = None
        self._init_stop_loss()

        # Optional: Risk modules
        self.cvar_sizer = None
        self.allocation_constraints = None
        self._init_risk_modules()

    def _init_memory(self):
        """Initialisiert das Memory-System wenn verfügbar"""
        try:
            from src.data.memory import TradingMemory

            self.memory = TradingMemory()
            logger.info("Memory-System initialisiert")
        except Exception as e:
            logger.warning(f"Memory-System nicht verfügbar: {e}")
            self.memory = None

    def _init_stop_loss(self):
        """Initialisiert den Stop-Loss Manager mit DB-Persistenz wenn verfügbar"""
        try:
            from src.risk.stop_loss import StopLossManager

            # Versuche DB-Manager zu holen für Stop-Persistenz
            db_manager = None
            try:
                from src.data.database import DatabaseManager

                db_manager = DatabaseManager.get_instance()
                if db_manager and not db_manager._pool:
                    db_manager = None
            except Exception:
                pass

            self.stop_loss_manager = StopLossManager(db_manager=db_manager, telegram_bot=None)
            if db_manager:
                logger.info("Stop-Loss Manager initialisiert (mit DB-Persistenz)")
            else:
                logger.info("Stop-Loss Manager initialisiert (ohne DB)")
        except Exception as e:
            logger.warning(f"Stop-Loss Manager nicht verfügbar: {e}")
            self.stop_loss_manager = None

    def _init_risk_modules(self):
        """Initialisiert CVaR Position Sizer und Allocation Constraints"""
        try:
            from src.risk.cvar_sizing import CVaRPositionSizer

            self.cvar_sizer = CVaRPositionSizer.get_instance()
            logger.info("CVaR Position Sizer initialisiert")
        except Exception as e:
            logger.warning(f"CVaR Position Sizer nicht verfügbar: {e}")
            self.cvar_sizer = None

        try:
            from src.portfolio.constraints import AllocationConstraints

            self.allocation_constraints = AllocationConstraints()
            logger.info("Allocation Constraints initialisiert")
        except Exception as e:
            logger.warning(f"Allocation Constraints nicht verfügbar: {e}")
            self.allocation_constraints = None

    def _validate_order_risk(self, side: str, quantity: float, price: float) -> tuple[bool, str]:
        """
        Validiert eine Order gegen Risk-Checks bevor sie platziert wird.

        Returns:
            (allowed, reason) - False + reason wenn Order abgelehnt
        """
        order_value = quantity * price

        # 1. Portfolio drawdown check
        if self.stop_loss_manager and self.stop_loss_manager.portfolio_stopped:
            return False, "Portfolio drawdown limit reached - all trading halted"

        # 2. CVaR position sizing check
        if self.cvar_sizer and side == "BUY":
            try:
                portfolio_value = self.client.get_account_balance("USDT")
                if portfolio_value > 0:
                    sizing = self.cvar_sizer.calculate_position_size(
                        symbol=self.symbol,
                        portfolio_value=portfolio_value,
                        signal_confidence=0.5,
                    )
                    if order_value > sizing.max_position:
                        return (
                            False,
                            f"Order ${order_value:.2f} exceeds CVaR max position "
                            f"${sizing.max_position:.2f}",
                        )
            except Exception as e:
                logger.warning(f"CVaR check failed (allowing order): {e}")

        # 3. Allocation constraints check
        if self.allocation_constraints and side == "BUY":
            try:
                portfolio_value = self.client.get_account_balance("USDT")
                if portfolio_value > 0:
                    # Calculate current invested amount from active orders
                    current_invested = sum(
                        o["quantity"] * o["price"]
                        for o in self.active_orders.values()
                        if o["type"] == "BUY"
                    )
                    available = self.allocation_constraints.get_available_capital(
                        total_capital=portfolio_value + current_invested,
                        current_invested=current_invested,
                    )
                    if order_value > available:
                        return (
                            False,
                            f"Order ${order_value:.2f} exceeds available capital "
                            f"${available:.2f} (cash reserve enforced)",
                        )
            except Exception as e:
                logger.warning(f"Allocation check failed (allowing order): {e}")

        return True, ""

    def _check_circuit_breaker(self, current_price: float) -> bool:
        """
        Emergency stop bei Flash-Crash (>10% Drop seit letztem Check).

        Returns:
            True wenn Circuit Breaker ausgelöst wurde
        """
        if self._last_known_price <= 0:
            self._last_known_price = current_price
            return False

        if current_price <= 0:
            return False

        drop_pct = (self._last_known_price - current_price) / self._last_known_price * 100

        if drop_pct >= self.CIRCUIT_BREAKER_PCT:
            self._emergency_stop(
                f"Circuit Breaker: {self.symbol} dropped {drop_pct:.1f}% "
                f"({self._last_known_price:.2f} → {current_price:.2f})"
            )
            return True

        self._last_known_price = current_price
        return False

    def _get_current_fear_greed(self) -> int:
        """Holt den aktuellen Fear & Greed Index"""
        try:
            http = get_http_client()
            data = http.get("https://api.alternative.me/fng/")
            return int(data["data"][0]["value"])
        except HTTPClientError as e:
            logger.warning(f"Fear & Greed API error: {e}")
        return 50  # Neutral als Fallback

    def _emergency_stop(self, reason: str):
        """Notfall-Stop mit Benachrichtigung"""
        logger.critical(f"EMERGENCY STOP: {reason}")
        self.telegram.send(f"🛑 BOT EMERGENCY STOP\n\nGrund: {reason}", urgent=True)
        self.running = False
        self.save_state()

    def _calculate_backoff(self) -> float:
        """Berechnet exponentiellen Backoff"""
        backoff = self.INITIAL_BACKOFF_SECONDS * (2 ** (self.consecutive_errors - 1))
        return min(backoff, self.MAX_BACKOFF_SECONDS)

    def initialize(self) -> bool:
        """Bot initialisieren mit Balance-Check"""
        logger.info(f"Initialisiere Bot für {self.symbol}")

        try:
            # Symbol-Info holen
            self.symbol_info = self.client.get_symbol_info(self.symbol)
            if not self.symbol_info:
                logger.error(f"Symbol {self.symbol} nicht gefunden")
                return False

            logger.info(f"Min Notional: {self.symbol_info['min_notional']} USDT")
            logger.info(
                f"Min Qty: {self.symbol_info['min_qty']}, Step: {self.symbol_info['step_size']}"
            )

            # Account Balance Check (Phase 1.5)
            available_usdt = self.client.get_account_balance("USDT")
            required_usdt = self.config["investment"] * 1.02  # 2% Buffer für Fees

            if available_usdt < required_usdt:
                logger.error(
                    f"Unzureichendes Guthaben: {available_usdt:.2f} USDT verfügbar, "
                    f"benötigt: {required_usdt:.2f} USDT"
                )
                self.telegram.send(
                    f"❌ Bot konnte nicht starten\n"
                    f"Guthaben: {available_usdt:.2f} USDT\n"
                    f"Benötigt: {required_usdt:.2f} USDT",
                    urgent=True,
                )
                return False

            logger.info(f"Balance Check OK: {available_usdt:.2f} USDT verfügbar")

            # Aktuellen Preis holen
            current_price = self.client.get_current_price(self.symbol)
            if not current_price:
                logger.error("Konnte Preis nicht abrufen")
                return False

            logger.info(f"Aktueller Preis: {current_price}")

            # Grid-Bereich: ±5% vom aktuellen Preis (für kleine Investments)
            grid_range = self.config.get("grid_range_percent", 5) / 100
            lower = current_price * (1 - grid_range)
            upper = current_price * (1 + grid_range)

            # Strategy erstellen
            self.strategy = GridStrategy(
                lower_price=lower,
                upper_price=upper,
                num_grids=self.config.get("num_grids", 3),
                total_investment=self.config["investment"],
                symbol_info=self.symbol_info,
            )

            self.strategy.print_grid()

            # Prüfe ob genug gültige Grid-Levels
            if len(self.strategy.levels) < 2:
                logger.error("Zu wenige gültige Grid-Levels. Investment zu klein.")
                return False

            # Check ob Investment reicht
            if self.config["investment"] < self.symbol_info["min_notional"]:
                logger.error(
                    f"Investment ({self.config['investment']}) ist kleiner als "
                    f"Minimum ({self.symbol_info['min_notional']})"
                )
                return False

            # Erfolgreiche Initialisierung
            self.telegram.send(
                f"✅ Bot initialisiert\n"
                f"Symbol: {self.symbol}\n"
                f"Investment: {self.config['investment']} USDT\n"
                f"Grid-Bereich: {lower:.2f} - {upper:.2f}\n"
                f"Grid-Levels: {len(self.strategy.levels)}"
            )

            return True

        except Exception as e:
            logger.exception(f"Initialisierung fehlgeschlagen: {e}")
            return False

    def place_initial_orders(self):
        """Platziert die initialen Grid-Orders"""
        try:
            current_price = self.client.get_current_price(self.symbol)
            orders = self.strategy.get_initial_orders(current_price)

            placed_count = 0
            failed_count = 0

            logger.info(f"Platziere {len(orders['buy_orders'])} Buy-Orders")

            for order in orders["buy_orders"]:
                notional = order["quantity"] * order["price"]

                if notional < self.symbol_info["min_notional"]:
                    logger.warning(
                        f"Order zu klein (Notional: {notional:.2f}): {order['price']} x {order['quantity']}"
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

            # Prüfe welche Orders gefüllt wurden
            for order_id, order_info in list(self.active_orders.items()):
                if order_id not in open_order_ids:
                    # Order ist nicht mehr offen - prüfe Status
                    order_status = self.client.get_order_status(self.symbol, order_id)

                    if not order_status:
                        logger.warning(f"Konnte Status für Order {order_id} nicht abrufen")
                        continue

                    status = order_status.get("status", "")
                    executed_qty = float(order_status.get("executedQty", 0))

                    # --- Status-specific handling ---

                    if status == "PARTIALLY_FILLED":
                        # Still alive on Binance but disappeared from open_orders
                        # (race condition between API calls). Keep tracking.
                        logger.info(
                            f"Order {order_id} partially filled "
                            f"({executed_qty}/{order_info['quantity']}) - weiter tracken"
                        )
                        order_info["executed_qty"] = executed_qty
                        continue

                    if status == "CANCELED" and executed_qty > 0:
                        # Canceled with partial fill -> process the filled portion
                        logger.info(
                            f"Order {order_id} canceled with partial fill: "
                            f"{executed_qty} of {order_info['quantity']}"
                        )
                        self._process_partial_fill(order_id, order_info, order_status)
                        continue

                    if status in ("CANCELED", "EXPIRED", "REJECTED", "PENDING_CANCEL"):
                        # Clean removal - nothing was filled
                        logger.info(f"Order {order_id} Status: {status} - wird entfernt")
                        del self.active_orders[order_id]
                        continue

                    if status != "FILLED":
                        # Unknown status - log and keep for safety
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

                    # Telegram Benachrichtigung
                    emoji = "🟢" if order_info["type"] == "BUY" else "🔴"
                    self.telegram.send(
                        f"{emoji} Order gefüllt\n"
                        f"Typ: {order_info['type']}\n"
                        f"Preis: {filled_price:.2f}\n"
                        f"Menge: {filled_qty}"
                    )

                    # Fee berechnen (0.1% Binance taker fee)
                    fee_usd = filled_price * filled_qty * float(TAKER_FEE_RATE)

                    # Trade in Memory speichern (Phase 2.1)
                    self._save_trade_to_memory(order_info, filled_price, filled_qty, fee_usd)

                    # Stop-Loss erstellen für BUY Orders (Phase 2.2)
                    if order_info["type"] == "BUY" and self.stop_loss_manager:
                        self._create_stop_loss(filled_price, filled_qty)

                    # Nächste Aktion bestimmen
                    if order_info["type"] == "BUY":
                        action = self.strategy.on_buy_filled(filled_price)
                    else:
                        action = self.strategy.on_sell_filled(filled_price)

                    # Prüfe ob Aktion gültig ist
                    action_type = action.get("action", "NONE")

                    if action_type == "NONE":
                        logger.info(f"Keine Folge-Aktion für {order_info['type']} @ {filled_price}")
                        del self.active_orders[order_id]
                        continue

                    # RACE CONDITION FIX: Neue Order ERST platzieren
                    new_order_placed = False
                    new_order_id = None

                    if action_type == "PLACE_SELL":
                        # Risk validation for follow-up SELL
                        allowed, reason = self._validate_order_risk(
                            "SELL", float(action["quantity"]), float(action["price"])
                        )
                        if not allowed:
                            logger.warning(f"Follow-up SELL blocked by risk check: {reason}")
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
                                    f"Sell Order platziert: {action['price']:.2f} x {action['quantity']}"
                                )
                            else:
                                logger.error(f"Sell Order fehlgeschlagen: {result.get('error')}")

                    elif action_type == "PLACE_BUY":
                        # Risk validation for follow-up BUY
                        allowed, reason = self._validate_order_risk(
                            "BUY", float(action["quantity"]), float(action["price"])
                        )
                        if not allowed:
                            logger.warning(f"Follow-up BUY blocked by risk check: {reason}")
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
                                    f"Buy Order platziert: {action['price']:.2f} x {action['quantity']}"
                                )
                            else:
                                logger.error(f"Buy Order fehlgeschlagen: {result.get('error')}")

                    # NUR löschen wenn neue Order erfolgreich ODER keine Aktion nötig
                    if new_order_placed or action_type == "NONE":
                        del self.active_orders[order_id]
                    else:
                        # Neue Order fehlgeschlagen - alte Order behalten zur Nachverfolgung
                        logger.warning(f"Folge-Order fehlgeschlagen, behalte alte Order {order_id}")
                        self.active_orders[order_id]["failed_followup"] = True
                        self.active_orders[order_id]["intended_action"] = action

        except Exception as e:
            logger.exception(f"Fehler in check_orders: {e}")
            raise  # Re-raise für Error-Handling im Main-Loop

    def _process_partial_fill(self, order_id: int, order_info: dict, order_status: dict):
        """
        Verarbeitet eine teilweise gefüllte und dann stornierte Order.

        - Speichert den gefüllten Teil als Trade
        - Erstellt Stop-Loss für BUY-Partial-Fills
        - Entfernt die Order aus active_orders
        - Platziert KEINE Follow-up-Order (Grid-Level bleibt für nächsten Zyklus)
        """
        filled_price = float(order_status.get("price", order_info["price"]))
        filled_qty = float(order_status.get("executedQty", 0))

        if filled_qty <= 0:
            del self.active_orders[order_id]
            return

        # Fee berechnen
        fee_usd = filled_price * filled_qty * float(TAKER_FEE_RATE)

        logger.info(
            f"Partial fill verarbeitet: {order_info['type']} "
            f"@ {filled_price:.2f} x {filled_qty} (fee: ${fee_usd:.4f})"
        )

        # Telegram Benachrichtigung
        self.telegram.send(
            f"⚠️ Partial Fill\n"
            f"Typ: {order_info['type']}\n"
            f"Preis: {filled_price:.2f}\n"
            f"Menge: {filled_qty} / {order_info['quantity']}\n"
            f"Status: Canceled nach Partial Fill"
        )

        # Trade in Memory speichern
        self._save_trade_to_memory(order_info, filled_price, filled_qty, fee_usd)

        # Stop-Loss für BUY Partial Fills
        if order_info["type"] == "BUY" and self.stop_loss_manager:
            self._create_stop_loss(filled_price, filled_qty)

        # Order entfernen
        del self.active_orders[order_id]

    def _save_trade_to_memory(
        self, order_info: dict, price: float, quantity: float, fee_usd: float = 0.0
    ):
        """Speichert einen Trade im Memory-System"""
        if not self.memory:
            return

        try:
            from src.data.memory import TradeRecord

            # Hole Marktkontext
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
                symbol_24h_change=0.0,  # TODO: Implementieren
                market_trend="NEUTRAL",
                math_signal="GRID",
                ai_signal="N/A",
                reasoning=f"Grid order filled at {price} (fee: ${fee_usd:.4f})",
            )

            trade_id = self.memory.save_trade(trade_record)
            logger.info(f"Trade in Memory gespeichert: ID {trade_id} (fee: ${fee_usd:.4f})")

        except Exception as e:
            logger.warning(f"Konnte Trade nicht in Memory speichern: {e}")

    def _create_stop_loss(self, entry_price: float, quantity: float):
        """Erstellt einen Stop-Loss für eine Position"""
        if not self.stop_loss_manager:
            return

        try:
            from src.risk.stop_loss import StopType

            # Standard: 5% Trailing Stop
            stop = self.stop_loss_manager.create_stop(
                symbol=self.symbol,
                entry_price=entry_price,
                quantity=quantity,
                stop_type=StopType.TRAILING,
                stop_percentage=5.0,
            )
            logger.info(f"Stop-Loss erstellt: {stop.current_stop_price:.2f} (Trailing 5%)")

        except Exception as e:
            logger.warning(f"Konnte Stop-Loss nicht erstellen: {e}")

    def _check_stop_losses(self, current_price: float):
        """Prüft und aktualisiert Stop-Losses"""
        if not self.stop_loss_manager:
            return

        try:
            triggered = self.stop_loss_manager.update_all(prices={self.symbol: current_price})

            for stop in triggered:
                logger.warning(f"STOP-LOSS TRIGGERED: {stop.symbol} @ {current_price}")
                self.telegram.send(
                    f"🛑 STOP-LOSS TRIGGERED\n"
                    f"Symbol: {stop.symbol}\n"
                    f"Preis: {current_price:.2f}\n"
                    f"Menge: {stop.quantity}",
                    urgent=True,
                )

                # Market-Sell ausführen
                result = self.client.place_market_sell(stop.symbol, stop.quantity)
                if result["success"]:
                    logger.info(f"Stop-Loss Market-Sell ausgeführt: {stop.quantity} {stop.symbol}")
                    fee_usd = current_price * stop.quantity * float(TAKER_FEE_RATE)
                    self._save_trade_to_memory(
                        {"type": "SELL"},
                        current_price,
                        stop.quantity,
                        fee_usd,
                    )
                else:
                    logger.error(f"Stop-Loss Market-Sell fehlgeschlagen: {result.get('error')}")
                    self.telegram.send(
                        f"⚠️ Stop-Loss SELL fehlgeschlagen!\n"
                        f"Symbol: {stop.symbol}\n"
                        f"Error: {result.get('error')}",
                        urgent=True,
                    )

        except Exception as e:
            logger.warning(f"Stop-Loss Check Fehler: {e}")

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

                # Risk validation before placing follow-up
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

    def save_state(self):
        """Speichert Bot-State für Neustart - mit Error-Handling"""
        try:
            # Konvertiere order_ids zu strings für JSON
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

            # Atomares Schreiben mit temp file
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

            # Config-Änderungen erkennen
            saved_config = state.get("config", {})
            if saved_config.get("symbol") != self.config.get("symbol"):
                logger.warning("Symbol hat sich geändert - starte frisch")
                return False

            if saved_config.get("investment") != self.config.get("investment"):
                logger.warning("Investment hat sich geändert - starte frisch")
                return False

            # Orders validieren
            loaded_orders = state.get("active_orders", {})
            validated_orders = {}

            for order_id_str, order_info in loaded_orders.items():
                try:
                    order_id = int(order_id_str)

                    # Prüfe Order-Status bei Binance
                    binance_status = self.client.get_order_status(self.symbol, order_id)

                    if not binance_status:
                        logger.warning(f"Order {order_id} nicht bei Binance gefunden")
                        continue

                    status = binance_status.get("status", "")
                    executed_qty = float(binance_status.get("executedQty", 0))

                    if status == "NEW":  # Noch offen
                        validated_orders[order_id] = order_info
                        logger.info(f"Order {order_id} validiert: noch offen")

                    elif status == "FILLED":
                        # Downtime-Fill-Recovery: Trade speichern + Follow-up queuen
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
                            self._create_stop_loss(filled_price, filled_qty)

                        # Queue follow-up for after load_state() completes
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
                        # Partial fill during downtime
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
                            self._create_stop_loss(filled_price, executed_qty)

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

        except Exception as e:
            logger.exception(f"Fehler beim Laden des States: {e}")
            return False

    def run(self):
        """Haupt-Loop mit robustem Error-Handling"""
        if not self.initialize():
            logger.error("Initialisierung fehlgeschlagen - Bot wird nicht gestartet")
            return

        self.running = True

        # Lade vorherigen State oder platziere neue Orders
        if not self.load_state():
            self.place_initial_orders()

        # Verarbeite Follow-ups von Downtime-Fills
        self._process_pending_followups()

        logger.info("Bot gestartet - Drücke Ctrl+C zum Stoppen")
        self.telegram.send("🤖 Trading Bot gestartet")

        try:
            while self.running:
                try:
                    # Hauptoperationen
                    self.check_orders()
                    self.save_state()

                    # Status und Stop-Loss Check
                    current_price = self.client.get_current_price(self.symbol)
                    if current_price:
                        # Circuit breaker: emergency stop on flash crash
                        if self._check_circuit_breaker(current_price):
                            break

                        self._check_stop_losses(current_price)

                        balance_usdt = self.client.get_account_balance("USDT")
                        logger.info(
                            f"USDT: {balance_usdt:.2f} | "
                            f"{self.symbol}: {current_price:.2f} | "
                            f"Orders: {len(self.active_orders)}"
                        )

                    # Portfolio Drawdown Check
                    if self.stop_loss_manager:
                        portfolio_value = self.client.get_account_balance("USDT")
                        should_stop, reason = self.stop_loss_manager.check_portfolio_drawdown(
                            portfolio_value
                        )
                        if should_stop:
                            self._emergency_stop(reason)
                            break

                    # Reset error counter on success
                    self.consecutive_errors = 0

                    time.sleep(30)  # Alle 30 Sekunden prüfen

                except KeyboardInterrupt:
                    raise  # Weitergeben an äußeren Handler

                except Exception as e:
                    self.consecutive_errors += 1
                    self.last_error_time = datetime.now()

                    logger.error(
                        f"Fehler im Main-Loop ({self.consecutive_errors}/{self.MAX_CONSECUTIVE_ERRORS}): {e}"
                    )

                    if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        self._emergency_stop(f"Zu viele aufeinanderfolgende Fehler: {e}")
                        break

                    # Exponential Backoff
                    backoff = self._calculate_backoff()
                    logger.info(f"Warte {backoff:.0f} Sekunden vor erneutem Versuch...")
                    time.sleep(backoff)

        except KeyboardInterrupt:
            logger.info("Bot wird gestoppt (Ctrl+C)...")
            self.save_state()

        self.running = False
        self.telegram.send("🛑 Trading Bot gestoppt")
        logger.info("Bot gestoppt")

    def stop(self):
        """Stoppt den Bot"""
        self.running = False
