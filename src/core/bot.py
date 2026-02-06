"""Main Bot Logic - Production Ready"""

import logging
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.api.binance_client import BinanceClient
from src.core.order_manager import OrderManagerMixin
from src.core.risk_guard import RiskGuardMixin
from src.core.state_manager import StateManagerMixin
from src.strategies.grid_strategy import GridStrategy
from src.utils.heartbeat import touch_heartbeat


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
    """Thin wrapper that delegates to the TelegramService singleton.

    Keeps the same ``send(message, urgent=False)`` API used by GridBot
    and HybridOrchestrator so callers don't need to change.
    """

    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service is None:
            try:
                from src.notifications.telegram_service import get_telegram

                self._service = get_telegram()
            except Exception:
                pass
        return self._service

    @property
    def enabled(self) -> bool:
        svc = self._get_service()
        return svc.enabled if svc else False

    def send(self, message: str, urgent: bool = False):
        """Sendet eine Telegram-Nachricht"""
        svc = self._get_service()
        if not svc:
            return
        if urgent:
            svc.send_urgent(message)
        else:
            svc.send(message)


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

        # State file für Persistenz (Hybrid-Modus nutzt pro-Symbol State Files)
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        state_file_name = config.get("state_file", "bot_state.json")
        self.state_file = config_dir / state_file_name

        # Telegram Notifier
        self.telegram = TelegramNotifier()

        # Error tracking
        self.consecutive_errors = 0
        self.last_error_time: datetime | None = None

        # Circuit breaker: track last known price
        self._last_known_price: float = 0.0
        self._consecutive_price_failures: int = 0

        # Downtime-fill-recovery: queued follow-up actions from load_state()
        self._pending_followups: list[dict] = []

        # Daily drawdown reset tracking
        self._last_drawdown_reset_date: str = ""

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

            # Initialize circuit breaker with current price
            self._last_known_price = current_price

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
            self._consecutive_price_failures = 0

            if self._check_circuit_breaker(current_price):
                return False

            self._check_stop_losses(current_price)

            balance_usdt = self.client.get_account_balance("USDT")
            logger.info(
                f"USDT: {balance_usdt:.2f} | "
                f"{self.symbol}: {current_price:.2f} | "
                f"Orders: {len(self.active_orders)}"
            )
        else:
            self._consecutive_price_failures += 1
            logger.warning(f"Price unavailable ({self._consecutive_price_failures} consecutive)")
            if self._consecutive_price_failures >= 3:
                self._emergency_stop("Price unavailable for 3 consecutive ticks")
                return False

        # Portfolio drawdown check — skip in hybrid/cohort mode where
        # multiple bots share one account (each bot would see the others'
        # locked USDT as a "loss"). HybridOrchestrator has its own stop-losses.
        if self.stop_loss_manager and not self.config.get("skip_portfolio_drawdown"):
            portfolio_value = self.client.get_account_balance("USDT")

            # Reset daily drawdown baseline at start of new day
            today = datetime.now().strftime("%Y-%m-%d")
            if today != self._last_drawdown_reset_date and portfolio_value > 0:
                self.stop_loss_manager.reset_daily(portfolio_value)
                self._last_drawdown_reset_date = today
                logger.info(f"Daily drawdown reset: baseline ${portfolio_value:.2f}")

            should_stop, reason = self.stop_loss_manager.check_portfolio_drawdown(portfolio_value)
            if should_stop:
                self._emergency_stop(reason)
                return False

        self.consecutive_errors = 0

        # Heartbeat for Docker health check
        touch_heartbeat()

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
        self.save_state()
        self.telegram.send("🛑 Trading Bot gestoppt")
        logger.info("Bot gestoppt")

    def stop(self):
        """Stoppt den Bot"""
        self.running = False
