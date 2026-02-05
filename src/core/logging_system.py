"""
Structured Logging System for Trading Bot
==========================================

Provides comprehensive logging for long-term analysis:
- Error tracking with context
- Trade decisions with reasoning
- Performance metrics
- System health

Logs are designed to be analyzed by Claude Code for weekly optimization.
"""

import json
import logging
import sys
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class LogCategory(Enum):
    """Log categories for filtering and analysis."""

    ERROR = "error"
    TRADE = "trade"
    DECISION = "decision"
    PERFORMANCE = "performance"
    SYSTEM = "system"
    PLAYBOOK = "playbook"
    API = "api"


# Singleton instance
_trading_logger = None


class TradingLogger:
    """
    Centralized logging for trading bot analysis.

    All logs are JSON-formatted for easy parsing and analysis.
    Logs are rotated to prevent disk space issues.
    """

    LOG_DIR = Path("logs")
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
    BACKUP_COUNT = 10  # Keep 10 backup files

    def __init__(self):
        """Initialize the logging system."""
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Create separate loggers for each category
        self.loggers: dict[str, logging.Logger] = {}

        # Configure root logger
        self._configure_root_logger()

        # Create category-specific loggers
        for category in LogCategory:
            self._create_category_logger(category)

        # Also log to combined file
        self._create_combined_logger()

    def _configure_root_logger(self):
        """Configure the root logger."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def _create_category_logger(self, category: LogCategory):
        """Create a logger for a specific category."""
        logger = logging.getLogger(f"trading.{category.value}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # File handler with rotation
        log_file = self.LOG_DIR / f"{category.value}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.MAX_BYTES,
            backupCount=self.BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self._get_json_formatter())

        # Console handler for errors
        if category == LogCategory.ERROR:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.ERROR)
            console_handler.setFormatter(logging.Formatter("%(asctime)s - ERROR - %(message)s"))
            logger.addHandler(console_handler)

        logger.addHandler(file_handler)
        self.loggers[category.value] = logger

    def _create_combined_logger(self):
        """Create a combined logger for all events."""
        logger = logging.getLogger("trading.combined")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        log_file = self.LOG_DIR / "combined.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.MAX_BYTES * 2,  # 20 MB for combined
            backupCount=self.BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self._get_json_formatter())
        logger.addHandler(file_handler)
        self.loggers["combined"] = logger

    def _get_json_formatter(self) -> logging.Formatter:
        """Get JSON formatter for structured logs."""

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record.levelname,
                    "category": getattr(record, "category", "unknown"),
                    "message": record.getMessage(),
                }

                # Add extra fields if present
                if hasattr(record, "extra_data"):
                    log_data["data"] = record.extra_data

                return json.dumps(log_data, default=str)

        return JsonFormatter()

    def _log(
        self,
        category: LogCategory,
        level: int,
        message: str,
        data: dict[str, Any] | None = None,
    ):
        """Internal logging method."""
        logger = self.loggers.get(category.value)
        combined = self.loggers.get("combined")

        if logger:
            record = logging.LogRecord(
                name=logger.name,
                level=level,
                pathname="",
                lineno=0,
                msg=message,
                args=(),
                exc_info=None,
            )
            record.category = category.value
            if data:
                record.extra_data = data
            logger.handle(record)

        # Also log to combined
        if combined:
            record = logging.LogRecord(
                name=combined.name,
                level=level,
                pathname="",
                lineno=0,
                msg=message,
                args=(),
                exc_info=None,
            )
            record.category = category.value
            if data:
                record.extra_data = data
            combined.handle(record)

    # ========================================
    # Error Logging
    # ========================================

    def error(
        self,
        message: str,
        error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        """
        Log an error with full context.

        Args:
            message: Error description
            error: The exception if available
            context: Additional context (function, parameters, state)
        """
        data = {
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error) if error else None,
            "context": context or {},
        }
        self._log(LogCategory.ERROR, logging.ERROR, message, data)

    def critical(
        self,
        message: str,
        error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Log a critical error that requires immediate attention."""
        data = {
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error) if error else None,
            "context": context or {},
            "severity": "CRITICAL",
        }
        self._log(LogCategory.ERROR, logging.CRITICAL, message, data)

    # ========================================
    # Trade Logging
    # ========================================

    def trade_executed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: str,
        context: dict[str, Any] | None = None,
    ):
        """
        Log a trade execution.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            side: BUY or SELL
            quantity: Amount traded
            price: Execution price
            order_id: Binance order ID
            context: Market conditions at time of trade
        """
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "order_id": order_id,
            "value_usdt": quantity * price,
            "context": context or {},
        }
        self._log(
            LogCategory.TRADE,
            logging.INFO,
            f"Trade executed: {side} {quantity} {symbol} @ {price}",
            data,
        )

    def trade_failed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reason: str,
        error: Exception | None = None,
    ):
        """Log a failed trade attempt."""
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "reason": reason,
            "error": str(error) if error else None,
        }
        self._log(
            LogCategory.TRADE, logging.WARNING, f"Trade failed: {side} {symbol} - {reason}", data
        )

    def order_filled(
        self,
        order_id: str,
        symbol: str,
        side: str,
        filled_qty: float,
        filled_price: float,
        grid_level: int | None = None,
    ):
        """Log when an order is filled."""
        data = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
            "grid_level": grid_level,
            "value_usdt": filled_qty * filled_price,
        }
        self._log(LogCategory.TRADE, logging.INFO, f"Order filled: {order_id}", data)

    # ========================================
    # Decision Logging
    # ========================================

    def ai_decision(
        self,
        symbol: str,
        direction: str,
        action: str,
        confidence: float,
        reasoning: str,
        market_data: dict[str, Any] | None = None,
        playbook_rules_applied: list[str] | None = None,
    ):
        """
        Log an AI trading decision with full reasoning.

        This is crucial for analyzing what decisions led to good/bad outcomes.
        """
        data = {
            "symbol": symbol,
            "direction": direction,
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
            "market_data": market_data or {},
            "playbook_rules_applied": playbook_rules_applied or [],
        }
        self._log(
            LogCategory.DECISION,
            logging.INFO,
            f"AI Decision: {action} {symbol} (confidence: {confidence:.2f})",
            data,
        )

    def math_signal(
        self,
        symbol: str,
        signal: str,
        indicators: dict[str, float],
        thresholds: dict[str, float] | None = None,
    ):
        """Log a mathematical/technical analysis signal."""
        data = {
            "symbol": symbol,
            "signal": signal,
            "indicators": indicators,
            "thresholds": thresholds or {},
        }
        self._log(LogCategory.DECISION, logging.INFO, f"Math signal: {signal} for {symbol}", data)

    def decision_override(
        self,
        original_action: str,
        new_action: str,
        reason: str,
        override_source: str,
    ):
        """Log when a decision is overridden (e.g., by risk management)."""
        data = {
            "original_action": original_action,
            "new_action": new_action,
            "reason": reason,
            "override_source": override_source,
        }
        self._log(
            LogCategory.DECISION,
            logging.WARNING,
            f"Decision override: {original_action} -> {new_action}",
            data,
        )

    # ========================================
    # Performance Logging
    # ========================================

    def daily_performance(
        self,
        portfolio_value: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        trades_count: int,
        win_rate: float | None = None,
        fear_greed: int | None = None,
        btc_price: float | None = None,
    ):
        """Log daily performance metrics."""
        data = {
            "portfolio_value": portfolio_value,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "trades_count": trades_count,
            "win_rate": win_rate,
            "fear_greed": fear_greed,
            "btc_price": btc_price,
        }
        self._log(
            LogCategory.PERFORMANCE,
            logging.INFO,
            f"Daily Performance: {daily_pnl_pct:+.2f}% (${daily_pnl:+.2f})",
            data,
        )

    def weekly_performance(
        self,
        portfolio_value: float,
        weekly_pnl: float,
        weekly_pnl_pct: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        best_trade: dict[str, Any] | None = None,
        worst_trade: dict[str, Any] | None = None,
    ):
        """Log weekly performance summary."""
        data = {
            "portfolio_value": portfolio_value,
            "weekly_pnl": weekly_pnl,
            "weekly_pnl_pct": weekly_pnl_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": winning_trades / total_trades if total_trades > 0 else 0,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
        }
        self._log(
            LogCategory.PERFORMANCE,
            logging.INFO,
            f"Weekly Performance: {weekly_pnl_pct:+.2f}%",
            data,
        )

    def drawdown_alert(
        self,
        current_drawdown: float,
        max_allowed: float,
        portfolio_value: float,
        peak_value: float,
    ):
        """Log when drawdown exceeds threshold."""
        data = {
            "current_drawdown": current_drawdown,
            "max_allowed": max_allowed,
            "portfolio_value": portfolio_value,
            "peak_value": peak_value,
        }
        level = logging.CRITICAL if current_drawdown >= max_allowed else logging.WARNING
        self._log(
            LogCategory.PERFORMANCE,
            level,
            f"Drawdown Alert: {current_drawdown:.2f}% (max: {max_allowed:.2f}%)",
            data,
        )

    # ========================================
    # System Logging
    # ========================================

    def system_start(self, config: dict[str, Any] | None = None):
        """Log system startup."""
        data = {
            "event": "startup",
            "config": config or {},
            "python_version": sys.version,
        }
        self._log(LogCategory.SYSTEM, logging.INFO, "Trading bot started", data)

    def system_stop(self, reason: str, error: Exception | None = None):
        """Log system shutdown."""
        data = {
            "event": "shutdown",
            "reason": reason,
            "error": str(error) if error else None,
        }
        self._log(LogCategory.SYSTEM, logging.INFO, f"Trading bot stopped: {reason}", data)

    def system_health(
        self,
        status: str,
        api_status: str,
        db_status: str,
        memory_usage_mb: float | None = None,
        uptime_hours: float | None = None,
    ):
        """Log system health check."""
        data = {
            "status": status,
            "api_status": api_status,
            "db_status": db_status,
            "memory_usage_mb": memory_usage_mb,
            "uptime_hours": uptime_hours,
        }
        self._log(LogCategory.SYSTEM, logging.INFO, f"Health check: {status}", data)

    # ========================================
    # Playbook Logging
    # ========================================

    def playbook_updated(
        self,
        version: int,
        changes: list[str],
        patterns_found: int,
        anti_patterns_found: int,
    ):
        """Log playbook update."""
        data = {
            "version": version,
            "changes": changes,
            "patterns_found": patterns_found,
            "anti_patterns_found": anti_patterns_found,
        }
        self._log(
            LogCategory.PLAYBOOK,
            logging.INFO,
            f"Playbook updated to v{version}",
            data,
        )

    def playbook_rule_triggered(
        self,
        rule_name: str,
        rule_type: str,
        market_conditions: dict[str, Any],
        action_taken: str,
    ):
        """Log when a playbook rule is triggered."""
        data = {
            "rule_name": rule_name,
            "rule_type": rule_type,
            "market_conditions": market_conditions,
            "action_taken": action_taken,
        }
        self._log(
            LogCategory.PLAYBOOK,
            logging.INFO,
            f"Playbook rule triggered: {rule_name}",
            data,
        )

    def pattern_learned(
        self,
        pattern_type: str,
        pattern_description: str,
        sample_size: int,
        success_rate: float,
    ):
        """Log when a new pattern is learned."""
        data = {
            "pattern_type": pattern_type,
            "pattern_description": pattern_description,
            "sample_size": sample_size,
            "success_rate": success_rate,
        }
        self._log(
            LogCategory.PLAYBOOK,
            logging.INFO,
            f"New pattern learned: {pattern_type}",
            data,
        )

    # ========================================
    # API Logging
    # ========================================

    def api_call(
        self,
        api_name: str,
        endpoint: str,
        status: str,
        response_time_ms: float | None = None,
        error: str | None = None,
    ):
        """Log API calls for rate limiting analysis."""
        data = {
            "api_name": api_name,
            "endpoint": endpoint,
            "status": status,
            "response_time_ms": response_time_ms,
            "error": error,
        }
        level = logging.ERROR if status == "error" else logging.DEBUG
        self._log(LogCategory.API, level, f"API call: {api_name} - {status}", data)

    def api_rate_limit(self, api_name: str, retry_after: float | None = None):
        """Log rate limit hit."""
        data = {
            "api_name": api_name,
            "retry_after": retry_after,
        }
        self._log(
            LogCategory.API,
            logging.WARNING,
            f"Rate limit hit: {api_name}",
            data,
        )

    # ========================================
    # Analysis Helper Methods
    # ========================================

    def get_log_files(self) -> dict[str, Path]:
        """Get paths to all log files."""
        return {category.value: self.LOG_DIR / f"{category.value}.log" for category in LogCategory}

    def get_recent_errors(self, limit: int = 50) -> list[dict]:
        """Read recent errors for analysis."""
        error_file = self.LOG_DIR / "error.log"
        if not error_file.exists():
            return []

        errors = []
        try:
            with open(error_file, encoding="utf-8") as f:
                for line in f:
                    try:
                        errors.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return errors[-limit:]

    def get_analysis_summary(self) -> dict[str, Any]:
        """
        Generate a summary for Claude Code analysis.

        Returns a dict with key metrics and recent issues.
        """
        summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "log_files": {k: str(v) for k, v in self.get_log_files().items()},
            "recent_errors": self.get_recent_errors(20),
            "log_sizes": {},
        }

        # Get file sizes
        for category, path in self.get_log_files().items():
            if path.exists():
                summary["log_sizes"][category] = path.stat().st_size

        return summary


def get_logger() -> TradingLogger:
    """Get the singleton TradingLogger instance."""
    global _trading_logger
    if _trading_logger is None:
        _trading_logger = TradingLogger()
    return _trading_logger


# Convenience functions for direct import
def log_error(message: str, error: Exception | None = None, context: dict | None = None):
    """Log an error."""
    get_logger().error(message, error, context)


def log_trade(
    symbol: str, side: str, qty: float, price: float, order_id: str, context: dict | None = None
):
    """Log a trade execution."""
    get_logger().trade_executed(symbol, side, qty, price, order_id, context)


def log_decision(symbol: str, direction: str, action: str, confidence: float, reasoning: str):
    """Log an AI decision."""
    get_logger().ai_decision(symbol, direction, action, confidence, reasoning)
