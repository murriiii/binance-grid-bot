"""Hybrid Trading System Configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.cohort_manager import Cohort


@dataclass
class HybridConfig:
    """Configuration for the regime-adaptive hybrid trading system."""

    # Initial mode
    initial_mode: str = "GRID"
    enable_mode_switching: bool = True

    # Hysteresis (prevent flip-flopping)
    min_regime_probability: float = 0.75
    min_regime_duration_days: int = 2
    mode_cooldown_hours: int = 24

    # HOLD mode
    hold_trailing_stop_pct: float = 7.0

    # GRID mode (passthrough to GridBot)
    grid_range_percent: float = 5.0
    num_grids: int = 3

    # CASH mode
    cash_exit_timeout_hours: float = 2.0

    # Multi-coin
    max_symbols: int = 8
    min_position_usd: float = 10.0
    total_investment: float = 400.0

    # Coin selection
    min_confidence: float = 0.3

    # Constraints preset
    portfolio_constraints_preset: str = "small"

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration values."""
        errors = []

        if self.initial_mode not in ("HOLD", "GRID", "CASH"):
            errors.append(f"initial_mode must be HOLD, GRID, or CASH, got '{self.initial_mode}'")

        if not 0.5 <= self.min_regime_probability <= 1.0:
            errors.append(
                f"min_regime_probability must be between 0.5 and 1.0, got {self.min_regime_probability}"
            )

        if self.min_regime_duration_days < 0:
            errors.append("min_regime_duration_days must be non-negative")

        if self.mode_cooldown_hours < 0:
            errors.append("mode_cooldown_hours must be non-negative")

        if self.hold_trailing_stop_pct <= 0 or self.hold_trailing_stop_pct > 50:
            errors.append(
                f"hold_trailing_stop_pct must be between 0 and 50, got {self.hold_trailing_stop_pct}"
            )

        if self.total_investment < 10:
            errors.append(f"total_investment must be at least 10 USD, got {self.total_investment}")

        if self.max_symbols < 1 or self.max_symbols > 20:
            errors.append(f"max_symbols must be between 1 and 20, got {self.max_symbols}")

        if self.min_position_usd < 5:
            errors.append(
                f"min_position_usd must be at least 5 (Binance minimum), got {self.min_position_usd}"
            )

        if not 0.0 <= self.min_confidence <= 1.0:
            errors.append(f"min_confidence must be between 0.0 and 1.0, got {self.min_confidence}")

        if self.portfolio_constraints_preset not in (
            "small",
            "conservative",
            "balanced",
            "aggressive",
        ):
            errors.append(
                f"portfolio_constraints_preset must be small/conservative/balanced/aggressive, "
                f"got '{self.portfolio_constraints_preset}'"
            )

        return len(errors) == 0, errors

    @classmethod
    def from_cohort(cls, cohort: Cohort) -> HybridConfig:
        """Create a HybridConfig from a Cohort's settings.

        Maps CohortConfig fields to HybridConfig equivalents,
        falling back to env vars for fields not in CohortConfig.
        """
        # All $100 cohorts use "small" preset — conservative/aggressive constraint
        # presets have per-coin limits (8%/15%) that produce positions below
        # Binance's $10 minimum after Kelly adjustment.  Risk differentiation
        # comes from grid_range_pct and min_confidence instead.
        preset = "small"

        return cls(
            initial_mode=os.getenv("HYBRID_INITIAL_MODE", "GRID"),
            enable_mode_switching=os.getenv("HYBRID_ENABLE_MODE_SWITCHING", "false").lower()
            == "true",
            min_regime_probability=float(os.getenv("HYBRID_MIN_REGIME_PROBABILITY", 0.75)),
            min_regime_duration_days=int(os.getenv("HYBRID_MIN_REGIME_DURATION_DAYS", 2)),
            mode_cooldown_hours=int(os.getenv("HYBRID_MODE_COOLDOWN_HOURS", 24)),
            hold_trailing_stop_pct=float(os.getenv("HYBRID_HOLD_TRAILING_STOP_PCT", 7.0)),
            min_confidence=cohort.config.min_confidence,
            grid_range_percent=cohort.config.grid_range_pct,
            num_grids=2,  # $100 budget → 2 grids to keep per-grid above $5 min_notional
            cash_exit_timeout_hours=float(os.getenv("HYBRID_CASH_EXIT_TIMEOUT_HOURS", 2.0)),
            max_symbols=2,  # $100 budget → max 2 coins
            min_position_usd=float(os.getenv("HYBRID_MIN_POSITION_USD", 10.0)),
            total_investment=cohort.current_capital,
            portfolio_constraints_preset=preset,
        )

    @classmethod
    def from_env(cls) -> HybridConfig:
        """Load hybrid config from environment variables."""
        return cls(
            initial_mode=os.getenv("HYBRID_INITIAL_MODE", "GRID"),
            enable_mode_switching=os.getenv("HYBRID_ENABLE_MODE_SWITCHING", "true").lower()
            == "true",
            min_regime_probability=float(os.getenv("HYBRID_MIN_REGIME_PROBABILITY", 0.75)),
            min_regime_duration_days=int(os.getenv("HYBRID_MIN_REGIME_DURATION_DAYS", 2)),
            mode_cooldown_hours=int(os.getenv("HYBRID_MODE_COOLDOWN_HOURS", 24)),
            hold_trailing_stop_pct=float(os.getenv("HYBRID_HOLD_TRAILING_STOP_PCT", 7.0)),
            grid_range_percent=float(os.getenv("GRID_RANGE_PERCENT", 5.0)),
            num_grids=int(os.getenv("NUM_GRIDS", 3)),
            cash_exit_timeout_hours=float(os.getenv("HYBRID_CASH_EXIT_TIMEOUT_HOURS", 2.0)),
            max_symbols=int(os.getenv("HYBRID_MAX_SYMBOLS", 8)),
            min_position_usd=float(os.getenv("HYBRID_MIN_POSITION_USD", 10.0)),
            total_investment=float(os.getenv("HYBRID_TOTAL_INVESTMENT", 400.0)),
            portfolio_constraints_preset=os.getenv("HYBRID_CONSTRAINTS_PRESET", "small"),
        )

    def to_dict(self) -> dict:
        return {
            "initial_mode": self.initial_mode,
            "enable_mode_switching": self.enable_mode_switching,
            "min_regime_probability": self.min_regime_probability,
            "min_regime_duration_days": self.min_regime_duration_days,
            "mode_cooldown_hours": self.mode_cooldown_hours,
            "hold_trailing_stop_pct": self.hold_trailing_stop_pct,
            "grid_range_percent": self.grid_range_percent,
            "num_grids": self.num_grids,
            "cash_exit_timeout_hours": self.cash_exit_timeout_hours,
            "max_symbols": self.max_symbols,
            "min_position_usd": self.min_position_usd,
            "total_investment": self.total_investment,
            "min_confidence": self.min_confidence,
            "portfolio_constraints_preset": self.portfolio_constraints_preset,
        }
