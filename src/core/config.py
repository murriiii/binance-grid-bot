"""
Zentrale Konfiguration für Trading Bot
Enthält alle Einstellungen die vorher hardcoded waren.
"""

import logging
import os
from dataclasses import dataclass, field

from src.core.hybrid_config import HybridConfig

logger = logging.getLogger("trading_bot")


# ═══════════════════════════════════════════════════════════════
# API KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class APIConfig:
    """Konfiguration für externe APIs"""

    # Timeouts (Sekunden)
    timeout_default: int = 10
    timeout_deepseek: int = 30
    timeout_blockchain: int = 15
    timeout_telegram: int = 10
    timeout_binance: int = 10

    # Retry-Einstellungen
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0

    # Rate Limits
    binance_requests_per_minute: int = 1000  # Sicherheits-Buffer (1200 erlaubt)

    # API URLs (für einfache Änderung)
    fear_greed_url: str = "https://api.alternative.me/fng/"
    deepseek_url: str = "https://api.deepseek.com/v1/chat/completions"
    coingecko_url: str = "https://api.coingecko.com/api/v3"
    blockchain_url: str = "https://blockchain.info/unconfirmed-transactions?format=json"
    economic_calendar_url: str = "https://economic-calendar.tradingview.com/events"
    binance_api_url: str = "https://api.binance.com/api/v3"

    @classmethod
    def from_env(cls) -> "APIConfig":
        return cls(
            timeout_default=int(os.getenv("API_TIMEOUT_DEFAULT", 10)),
            timeout_deepseek=int(os.getenv("API_TIMEOUT_DEEPSEEK", 30)),
            max_retries=int(os.getenv("API_MAX_RETRIES", 3)),
        )


# ═══════════════════════════════════════════════════════════════
# BOT KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class BotConfig:
    """Hauptkonfiguration für den Trading Bot"""

    # Trading Pair
    symbol: str = "BTCUSDT"

    # Investment
    investment: float = 10.0

    # Grid Settings
    num_grids: int = 3
    grid_range_percent: float = 5.0

    # Mode
    testnet: bool = True

    # Risk Management
    risk_tolerance: str = "medium"  # low, medium, high
    max_daily_drawdown: float = 10.0  # Prozent
    enable_stop_loss: bool = True
    stop_loss_percent: float = 5.0

    # Error Handling (vorher hardcoded in bot.py)
    max_consecutive_errors: int = 5
    initial_backoff_seconds: int = 30
    max_backoff_seconds: int = 300

    # Features
    enable_ai: bool = False
    enable_memory: bool = True
    enable_whale_alerts: bool = True
    enable_economic_events: bool = True

    # Notification
    telegram_enabled: bool = True
    notification_level: str = "normal"  # minimal, normal, verbose
    learning_mode: bool = False  # Wenn True: nur 1x täglich Daily Summary

    def validate(self) -> tuple[bool, list[str]]:
        """Validiert alle Konfigurationswerte."""
        errors = []

        # Symbol Validierung
        if not self.symbol:
            errors.append("Symbol darf nicht leer sein")
        elif not self.symbol.endswith("USDT"):
            errors.append(f"Symbol '{self.symbol}' muss ein USDT-Pair sein (z.B. BTCUSDT)")
        elif len(self.symbol) < 5:
            errors.append(f"Ungültiges Symbol-Format: {self.symbol}")

        # Investment Validierung
        if self.investment <= 0:
            errors.append("Investment muss positiv sein")
        elif self.investment < 5:
            errors.append(f"Investment ({self.investment}) ist zu klein. Minimum: 5 USDT")
        elif self.investment > 100000:
            errors.append(
                f"Investment ({self.investment}) ist unrealistisch hoch. Maximum: 100,000 USDT"
            )

        # Grid Settings Validierung
        if self.num_grids < 2:
            errors.append(f"num_grids ({self.num_grids}) muss mindestens 2 sein")
        elif self.num_grids > 50:
            errors.append(f"num_grids ({self.num_grids}) ist zu hoch. Maximum: 50")

        if self.grid_range_percent < 1:
            errors.append(f"grid_range_percent ({self.grid_range_percent}) muss mindestens 1% sein")
        elif self.grid_range_percent > 30:
            errors.append(
                f"grid_range_percent ({self.grid_range_percent}) ist zu hoch. Maximum: 30%"
            )

        # Investment pro Grid prüfen
        investment_per_grid = self.investment / self.num_grids
        if investment_per_grid < 2:
            errors.append(
                f"Investment pro Grid ({investment_per_grid:.2f}) ist zu klein. "
                f"Erhöhe Investment oder reduziere num_grids."
            )

        # Risk Management Validierung
        if self.risk_tolerance not in ["low", "medium", "high"]:
            errors.append("risk_tolerance muss 'low', 'medium' oder 'high' sein")

        if self.max_daily_drawdown <= 0:
            errors.append("max_daily_drawdown muss positiv sein")
        elif self.max_daily_drawdown > 50:
            errors.append(
                f"max_daily_drawdown ({self.max_daily_drawdown}%) ist zu riskant. Maximum: 50%"
            )

        if self.stop_loss_percent <= 0:
            errors.append("stop_loss_percent muss positiv sein")
        elif self.stop_loss_percent > 20:
            errors.append(
                f"stop_loss_percent ({self.stop_loss_percent}%) ist zu hoch. Maximum: 20%"
            )

        # Notification Level Validierung
        if self.notification_level not in ["minimal", "normal", "verbose"]:
            errors.append("notification_level muss 'minimal', 'normal' oder 'verbose' sein")

        return len(errors) == 0, errors

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Erstellt Config aus Umgebungsvariablen"""
        return cls(
            symbol=os.getenv("TRADING_PAIR", "BTCUSDT"),
            investment=float(os.getenv("INVESTMENT_AMOUNT", 10)),
            num_grids=int(os.getenv("NUM_GRIDS", 3)),
            grid_range_percent=float(os.getenv("GRID_RANGE_PERCENT", 5)),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
            risk_tolerance=os.getenv("RISK_TOLERANCE", "medium"),
            max_daily_drawdown=float(os.getenv("MAX_DAILY_DRAWDOWN", 10)),
            enable_stop_loss=os.getenv("ENABLE_STOP_LOSS", "true").lower() == "true",
            stop_loss_percent=float(os.getenv("STOP_LOSS_PERCENT", 5)),
            max_consecutive_errors=int(os.getenv("MAX_CONSECUTIVE_ERRORS", 5)),
            initial_backoff_seconds=int(os.getenv("INITIAL_BACKOFF_SECONDS", 30)),
            max_backoff_seconds=int(os.getenv("MAX_BACKOFF_SECONDS", 300)),
            enable_ai=os.getenv("ENABLE_AI", "false").lower() == "true",
            enable_memory=os.getenv("ENABLE_MEMORY", "true").lower() == "true",
            enable_whale_alerts=os.getenv("ENABLE_WHALE_ALERTS", "true").lower() == "true",
            enable_economic_events=os.getenv("ENABLE_ECONOMIC_EVENTS", "true").lower() == "true",
            telegram_enabled=bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            notification_level=os.getenv("NOTIFICATION_LEVEL", "normal"),
            learning_mode=os.getenv("LEARNING_MODE", "false").lower() == "true",
        )

    def to_dict(self) -> dict:
        """Konvertiert Config zu Dictionary für den Bot"""
        return {
            "symbol": self.symbol,
            "investment": self.investment,
            "num_grids": self.num_grids,
            "grid_range_percent": self.grid_range_percent,
            "testnet": self.testnet,
            "risk_tolerance": self.risk_tolerance,
            "max_daily_drawdown": self.max_daily_drawdown,
            "enable_stop_loss": self.enable_stop_loss,
            "stop_loss_percent": self.stop_loss_percent,
            "enable_ai": self.enable_ai,
            "enable_memory": self.enable_memory,
        }

    def print_summary(self):
        """Gibt eine Zusammenfassung der Konfiguration aus"""
        mode = "TESTNET" if self.testnet else "LIVE"
        logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║                    BOT KONFIGURATION                         ║
╠══════════════════════════════════════════════════════════════╣
║  Modus:           {mode:<43}║
║  Symbol:          {self.symbol:<43}║
║  Investment:      {self.investment:<43.2f}║
║  Grid-Levels:     {self.num_grids:<43}║
║  Grid-Range:      ±{self.grid_range_percent:<42.1f}║
╠══════════════════════════════════════════════════════════════╣
║  RISIKO                                                      ║
║  Stop-Loss:       {f"{self.stop_loss_percent}%" if self.enable_stop_loss else "Deaktiviert":<43}║
║  Max Drawdown:    {self.max_daily_drawdown:<42.1f}%║
║  Risk Tolerance:  {self.risk_tolerance.upper():<43}║
╚══════════════════════════════════════════════════════════════╝
        """)


# ═══════════════════════════════════════════════════════════════
# WHALE ALERT KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class WhaleConfig:
    """Konfiguration für Whale Alert Tracking"""

    # Mindest-Werte für "Whale" Status (in USD)
    btc_threshold: float = 10_000_000  # $10M
    eth_threshold: float = 5_000_000  # $5M
    default_threshold: float = 1_000_000  # $1M für Altcoins

    # Minimum BTC-Transaktionsgröße für Tracking
    min_btc_amount: int = 100  # 100 BTC

    # Minimum für Telegram-Alert
    alert_threshold: float = 50_000_000  # $50M

    # Bekannte Exchange-Adressen (erweiterbar)
    exchange_addresses: dict[str, str] = field(
        default_factory=lambda: {
            "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h": "Binance",
            "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6": "Binance",
            "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97": "Bitfinex",
        }
    )


# ═══════════════════════════════════════════════════════════════
# SENTIMENT KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class SentimentConfig:
    """Konfiguration für Sentiment-Analyse"""

    # Fear & Greed Schwellwerte
    extreme_fear_threshold: int = 20
    fear_threshold: int = 40
    greed_threshold: int = 60
    extreme_greed_threshold: int = 80

    # Signal-Gewichtung
    weight_fear_greed: float = 0.4
    weight_social: float = 0.3
    weight_direct_sentiment: float = 0.3

    @classmethod
    def get_classification(cls, value: int) -> str:
        """Klassifiziert Fear & Greed Wert"""
        if value <= 20:
            return "Extreme Fear"
        elif value <= 40:
            return "Fear"
        elif value <= 60:
            return "Neutral"
        elif value <= 80:
            return "Greed"
        else:
            return "Extreme Greed"


# ═══════════════════════════════════════════════════════════════
# SCHEDULER KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class SchedulerConfig:
    """Konfiguration für den Scheduler"""

    # Zeitpunkte (Format: "HH:MM")
    daily_summary_time: str = "20:00"
    weekly_rebalance_day: str = "sunday"
    weekly_rebalance_time: str = "18:00"
    macro_check_time: str = "08:00"

    # Intervalle (Minuten)
    market_snapshot_interval: int = 60
    stop_loss_check_interval: int = 5
    sentiment_check_interval: int = 240  # 4 Stunden
    outcome_update_interval: int = 360  # 6 Stunden
    whale_check_interval: int = 60

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        return cls(
            daily_summary_time=os.getenv("DAILY_SUMMARY_TIME", "20:00"),
            weekly_rebalance_time=os.getenv("WEEKLY_REBALANCE_TIME", "18:00"),
            macro_check_time=os.getenv("MACRO_CHECK_TIME", "08:00"),
            market_snapshot_interval=int(os.getenv("MARKET_SNAPSHOT_INTERVAL", 60)),
            stop_loss_check_interval=int(os.getenv("STOP_LOSS_CHECK_INTERVAL", 5)),
        )


# ═══════════════════════════════════════════════════════════════
# DATABASE KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class DatabaseConfig:
    """Konfiguration für Datenbankverbindung"""

    host: str = "localhost"
    port: int = 5433
    database: str = "trading_bot"
    user: str = "trading"
    password: str = ""

    # Connection Pool
    min_connections: int = 1
    max_connections: int = 10

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        # Versuche DATABASE_URL zu parsen
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            # postgresql://user:pass@host:port/db
            import re

            match = re.match(r"postgresql://(\w+):([^@]+)@([^:]+):(\d+)/(\w+)", db_url)
            if match:
                return cls(
                    user=match.group(1),
                    password=match.group(2),
                    host=match.group(3),
                    port=int(match.group(4)),
                    database=match.group(5),
                )

        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5433)),
            database=os.getenv("POSTGRES_DB", "trading_bot"),
            user=os.getenv("POSTGRES_USER", "trading"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )

    def get_connection_string(self) -> str:
        """Gibt PostgreSQL Connection String zurück"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def url(self) -> str | None:
        """Alias für get_connection_string, aber gibt None zurück wenn Credentials fehlen"""
        if not self.password:
            db_url = os.getenv("DATABASE_URL")
            if db_url:
                return db_url
            return None
        return self.get_connection_string()


# ═══════════════════════════════════════════════════════════════
# GLOBALE KONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class AppConfig:
    """Hauptkonfiguration die alle Teilkonfigurationen enthält"""

    bot: BotConfig = field(default_factory=BotConfig)
    api: APIConfig = field(default_factory=APIConfig)
    whale: WhaleConfig = field(default_factory=WhaleConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    hybrid: HybridConfig = field(default_factory=HybridConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Lädt komplette Konfiguration aus Umgebungsvariablen"""
        return cls(
            bot=BotConfig.from_env(),
            api=APIConfig.from_env(),
            scheduler=SchedulerConfig.from_env(),
            database=DatabaseConfig.from_env(),
            hybrid=HybridConfig.from_env(),
        )


# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT VALIDATION
# ═══════════════════════════════════════════════════════════════


def validate_environment() -> tuple[bool, list[str]]:
    """Prüft ob alle notwendigen Umgebungsvariablen gesetzt sind."""
    warnings = []

    # Kritische Variablen
    if (
        not os.getenv("BINANCE_TESTNET_API_KEY")
        and os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    ):
        warnings.append("BINANCE_TESTNET_API_KEY nicht gesetzt - Bot kann nicht starten")

    if not os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_TESTNET", "true").lower() != "true":
        warnings.append("BINANCE_API_KEY nicht gesetzt - Bot kann nicht im LIVE-Modus starten")

    # Optionale aber empfohlene Variablen
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        warnings.append("TELEGRAM_BOT_TOKEN nicht gesetzt - Keine Benachrichtigungen")

    if not os.getenv("DEEPSEEK_API_KEY"):
        warnings.append("DEEPSEEK_API_KEY nicht gesetzt - AI-Features deaktiviert")

    if not os.getenv("POSTGRES_PASSWORD") and not os.getenv("DATABASE_URL"):
        warnings.append("Keine DB-Credentials gesetzt - Memory-System funktioniert nicht")

    return len([w for w in warnings if "nicht starten" in w]) == 0, warnings


# Singleton für globale Config
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Gibt die globale Konfiguration zurück"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config
