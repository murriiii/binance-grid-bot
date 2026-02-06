"""Trading Mode types for the Hybrid Trading System."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TradingMode(Enum):
    """Trading modes corresponding to market regimes."""

    HOLD = "HOLD"  # BULL: Buy and hold, ride trends
    GRID = "GRID"  # SIDEWAYS: Grid trading
    CASH = "CASH"  # BEAR: Preserve capital


@dataclass
class ModeState:
    """Current trading mode state with metadata."""

    current_mode: TradingMode
    previous_mode: TradingMode | None = None
    mode_since: datetime = field(default_factory=datetime.now)
    regime_at_switch: str | None = None
    regime_probability: float = 0.0
    transition_count_24h: int = 0

    @property
    def mode_duration_hours(self) -> float:
        """Hours since last mode switch."""
        return (datetime.now() - self.mode_since).total_seconds() / 3600

    def to_dict(self) -> dict:
        return {
            "current_mode": self.current_mode.value,
            "previous_mode": self.previous_mode.value if self.previous_mode else None,
            "mode_since": self.mode_since.isoformat(),
            "regime_at_switch": self.regime_at_switch,
            "regime_probability": self.regime_probability,
            "transition_count_24h": self.transition_count_24h,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ModeState:
        return cls(
            current_mode=TradingMode(data["current_mode"]),
            previous_mode=TradingMode(data["previous_mode"]) if data.get("previous_mode") else None,
            mode_since=datetime.fromisoformat(data["mode_since"]),
            regime_at_switch=data.get("regime_at_switch"),
            regime_probability=data.get("regime_probability", 0.0),
            transition_count_24h=data.get("transition_count_24h", 0),
        )


@dataclass
class ModeTransitionEvent:
    """Record of a mode transition."""

    from_mode: TradingMode
    to_mode: TradingMode
    timestamp: datetime = field(default_factory=datetime.now)
    regime: str | None = None
    regime_probability: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime,
            "regime_probability": self.regime_probability,
            "reason": self.reason,
        }
