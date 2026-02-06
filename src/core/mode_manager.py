"""Mode Manager for the Hybrid Trading System.

Manages trading mode transitions with hysteresis to prevent flip-flopping.

Hysteresis rules:
- regime_probability >= min_regime_probability AND regime_duration >= min_duration
- Exception: BEAR with probability >= 0.85 → immediate CASH (capital protection)
- Cooldown period between mode switches
- Lock to GRID if >2 transitions in 48h (safety fallback)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.core.hybrid_config import HybridConfig
from src.core.trading_mode import ModeState, ModeTransitionEvent, TradingMode
from src.portfolio.constraints import (
    AGGRESSIVE_CONSTRAINTS,
    BALANCED_CONSTRAINTS,
    CONSERVATIVE_CONSTRAINTS,
    SMALL_PORTFOLIO_CONSTRAINTS,
    AllocationConstraints,
)

logger = logging.getLogger("trading_bot")

# Regime → Mode mapping
REGIME_MODE_MAP: dict[str, TradingMode] = {
    "BULL": TradingMode.HOLD,
    "SIDEWAYS": TradingMode.GRID,
    "BEAR": TradingMode.CASH,
}

# Mode → Constraints mapping
MODE_CONSTRAINTS_MAP: dict[TradingMode, AllocationConstraints] = {
    TradingMode.HOLD: AGGRESSIVE_CONSTRAINTS,
    TradingMode.GRID: BALANCED_CONSTRAINTS,
    TradingMode.CASH: CONSERVATIVE_CONSTRAINTS,
}

# Emergency BEAR threshold - skip hysteresis
EMERGENCY_BEAR_PROBABILITY = 0.85

# Max transitions before safety lock
MAX_TRANSITIONS_48H = 2


class ModeManager:
    """Manages trading mode with hysteresis-based transitions."""

    _instance: ModeManager | None = None

    def __init__(self, config: HybridConfig | None = None):
        self.config = config or HybridConfig()
        self._state = ModeState(
            current_mode=TradingMode(self.config.initial_mode),
        )
        self._transition_history: list[ModeTransitionEvent] = []
        self._locked_mode: TradingMode | None = None

    @classmethod
    def get_instance(cls, config: HybridConfig | None = None) -> ModeManager:
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def get_current_mode(self) -> ModeState:
        return self._state

    def get_constraints_for_mode(self, mode: TradingMode | None = None) -> AllocationConstraints:
        """Return constraints appropriate for the given mode.

        Uses SMALL_PORTFOLIO_CONSTRAINTS when configured, otherwise mode-based.
        """
        if self.config.portfolio_constraints_preset == "small":
            return SMALL_PORTFOLIO_CONSTRAINTS

        target = mode or self._state.current_mode
        return MODE_CONSTRAINTS_MAP.get(target, BALANCED_CONSTRAINTS)

    def evaluate_mode(
        self,
        regime: str | None,
        regime_probability: float = 0.0,
        regime_duration_days: int = 0,
    ) -> tuple[TradingMode, str]:
        """Evaluate whether a mode switch is warranted.

        Args:
            regime: Current detected regime (BULL/BEAR/SIDEWAYS/TRANSITION/None)
            regime_probability: Confidence of the regime detection (0-1)
            regime_duration_days: How many days the regime has been active

        Returns:
            (recommended_mode, reason) - the mode to switch to and why
        """
        if not self.config.enable_mode_switching:
            return self._state.current_mode, "Mode switching disabled"

        # Safety lock: too many transitions
        if self._locked_mode is not None:
            return self._locked_mode, "Safety lock active (too many transitions)"

        # None/unknown regime → keep current mode
        if regime is None or regime == "TRANSITION":
            return self._state.current_mode, f"Regime {regime} - keeping current mode"

        # Map regime to target mode
        target_mode = REGIME_MODE_MAP.get(regime, TradingMode.GRID)

        # Already in target mode
        if target_mode == self._state.current_mode:
            return target_mode, "Already in correct mode"

        # Emergency BEAR → immediate CASH
        if regime == "BEAR" and regime_probability >= EMERGENCY_BEAR_PROBABILITY:
            return TradingMode.CASH, f"Emergency BEAR (probability {regime_probability:.2f})"

        # Hysteresis checks
        if regime_probability < self.config.min_regime_probability:
            return (
                self._state.current_mode,
                f"Regime probability {regime_probability:.2f} below threshold "
                f"{self.config.min_regime_probability}",
            )

        if regime_duration_days < self.config.min_regime_duration_days:
            return (
                self._state.current_mode,
                f"Regime duration {regime_duration_days}d below threshold "
                f"{self.config.min_regime_duration_days}d",
            )

        # Cooldown check
        if self._is_in_cooldown():
            return self._state.current_mode, "Mode cooldown active"

        return (
            target_mode,
            f"Regime {regime} (prob={regime_probability:.2f}, dur={regime_duration_days}d)",
        )

    def request_switch(self, new_mode: TradingMode, reason: str) -> bool:
        """Request a mode switch. Returns True if the switch was executed.

        Applies safety checks (cooldown, transition count).
        """
        if new_mode == self._state.current_mode:
            return False

        # Check transition count in 48h
        recent_count = self._count_recent_transitions(hours=48)
        if recent_count >= MAX_TRANSITIONS_48H:
            self._locked_mode = TradingMode.GRID
            logger.warning(f"ModeManager: {recent_count} transitions in 48h - locking to GRID")
            if self._state.current_mode != TradingMode.GRID:
                self._execute_switch(TradingMode.GRID, "Safety lock: too many transitions")
            return False

        self._execute_switch(new_mode, reason)
        return True

    def _execute_switch(self, new_mode: TradingMode, reason: str) -> None:
        """Execute a mode transition."""
        event = ModeTransitionEvent(
            from_mode=self._state.current_mode,
            to_mode=new_mode,
            regime=self._state.regime_at_switch,
            regime_probability=self._state.regime_probability,
            reason=reason,
        )
        self._transition_history.append(event)

        old_mode = self._state.current_mode
        self._state = ModeState(
            current_mode=new_mode,
            previous_mode=old_mode,
            mode_since=datetime.now(),
            regime_at_switch=self._state.regime_at_switch,
            regime_probability=self._state.regime_probability,
            transition_count_24h=self._count_recent_transitions(hours=24),
        )

        logger.info(f"ModeManager: {old_mode.value} → {new_mode.value} ({reason})")

    def _is_in_cooldown(self) -> bool:
        """Check if we're still in cooldown from the last transition."""
        if not self._transition_history:
            return False
        last = self._transition_history[-1]
        cooldown_end = last.timestamp + timedelta(hours=self.config.mode_cooldown_hours)
        return datetime.now() < cooldown_end

    def _count_recent_transitions(self, hours: int) -> int:
        """Count transitions in the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return sum(1 for t in self._transition_history if t.timestamp > cutoff)

    def get_transition_history(self) -> list[ModeTransitionEvent]:
        return list(self._transition_history)

    def update_regime_info(self, regime: str | None, probability: float) -> None:
        """Update regime info on the current state (for tracking, not switching)."""
        self._state.regime_at_switch = regime
        self._state.regime_probability = probability
