"""Main Bot Logic - Production Ready"""

import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.api.binance_client import BinanceClient
from src.api.http_client import HTTPClientError, get_http_client
from src.core.order_manager import OrderManagerMixin
from src.core.risk_guard import RiskGuardMixin
from src.core.state_manager import StateManagerMixin
from src.strategies.grid_strategy import GridStrategy


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


class GridBot(RiskGuardMixin, OrderManagerMixin, StateManagerMixin):
    """Grid Trading Bot mit robustem Error-Handling"""

    # Konfiguration für Fehlerbehandlung
    MAX_CONSECUTIVE_ERRORS = 5
    INITIAL_BACKOFF_SECONDS = 30
    MAX_BACKOFF_SECONDS = 300

    def __init__(self, config: dict, client: BinanceClient | None = None):
        self.config = config
        self.client = client or BinanceClient(testnet=config.get("testnet", True))
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

        # Optional: Memory System
        self.memory = None
        self._init_memory()

        # Optional: Stop-Loss Manager
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
            self.symbol_info = self.client.get_symbol_info(self.symbol)
            if not self.symbol_info:
                logger.error(f"Symbol {self.symbol} nicht gefunden")
                return False

            logger.info(f"Min Notional: {self.symbol_info['min_notional']} USDT")
            logger.info(
                f"Min Qty: {self.symbol_info['min_qty']}, Step: {self.symbol_info['step_size']}"
            )

            available_usdt = self.client.get_account_balance("USDT")
            required_usdt = self.config["investment"] * 1.02

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

            current_price = self.client.get_current_price(self.symbol)
            if not current_price:
                logger.error("Konnte Preis nicht abrufen")
                return False

            logger.info(f"Aktueller Preis: {current_price}")

            grid_range = self.config.get("grid_range_percent", 5) / 100
            lower = current_price * (1 - grid_range)
            upper = current_price * (1 + grid_range)

            self.strategy = GridStrategy(
                lower_price=lower,
                upper_price=upper,
                num_grids=self.config.get("num_grids", 3),
                total_investment=self.config["investment"],
                symbol_info=self.symbol_info,
            )

            self.strategy.print_grid()

            if len(self.strategy.levels) < 2:
                logger.error("Zu wenige gültige Grid-Levels. Investment zu klein.")
                return False

            if self.config["investment"] < self.symbol_info["min_notional"]:
                logger.error(
                    f"Investment ({self.config['investment']}) ist kleiner als "
                    f"Minimum ({self.symbol_info['min_notional']})"
                )
                return False

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

    def tick(self) -> bool:
        """Execute one iteration of the main loop.

        Returns:
            True if the bot should continue, False if it should stop.
        """
        self.check_orders()
        self.save_state()

        current_price = self.client.get_current_price(self.symbol)
        if current_price:
            if self._check_circuit_breaker(current_price):
                return False

            self._check_stop_losses(current_price)

            balance_usdt = self.client.get_account_balance("USDT")
            logger.info(
                f"USDT: {balance_usdt:.2f} | "
                f"{self.symbol}: {current_price:.2f} | "
                f"Orders: {len(self.active_orders)}"
            )

        if self.stop_loss_manager:
            portfolio_value = self.client.get_account_balance("USDT")
            should_stop, reason = self.stop_loss_manager.check_portfolio_drawdown(portfolio_value)
            if should_stop:
                self._emergency_stop(reason)
                return False

        self.consecutive_errors = 0
        return True

    def run(self):
        """Haupt-Loop mit robustem Error-Handling"""
        if not self.initialize():
            logger.error("Initialisierung fehlgeschlagen - Bot wird nicht gestartet")
            return

        self.running = True

        if not self.load_state():
            self.place_initial_orders()

        self._process_pending_followups()

        logger.info("Bot gestartet - Drücke Ctrl+C zum Stoppen")
        self.telegram.send("🤖 Trading Bot gestartet")

        try:
            while self.running:
                try:
                    if not self.tick():
                        break

                    time.sleep(30)

                except KeyboardInterrupt:
                    raise

                except Exception as e:
                    self.consecutive_errors += 1
                    self.last_error_time = datetime.now()

                    logger.error(
                        f"Fehler im Main-Loop "
                        f"({self.consecutive_errors}/{self.MAX_CONSECUTIVE_ERRORS}): {e}"
                    )

                    if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        self._emergency_stop(f"Zu viele aufeinanderfolgende Fehler: {e}")
                        break

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
