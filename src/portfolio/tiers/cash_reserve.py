"""Cash Reserve Tier - Always hold X% in USDT as safety buffer."""

import logging
from dataclasses import dataclass

logger = logging.getLogger("trading_bot")


@dataclass
class CashReserveStatus:
    """Current cash reserve state."""

    balance_usd: float
    target_usd: float
    target_pct: float
    current_pct: float
    is_underfunded: bool
    is_overfunded: bool
    deficit_usd: float  # Positive = need more cash
    surplus_usd: float  # Positive = excess cash to distribute


class CashReserveTier:
    """Simplest tier: always hold X% in USDT.

    No active trading — just tracks balance and signals
    when rebalancing is needed.
    """

    UNDERFUNDED_THRESHOLD_PCT = 2.0  # Trigger rebalance from other tiers
    OVERFUNDED_THRESHOLD_PCT = 5.0  # Distribute excess to other tiers

    def __init__(self, client, target_pct: float = 10.0):
        self.client = client
        self.target_pct = target_pct
        self._balance: float = 0.0

    def update_balance(self) -> float:
        """Fetch current USDT balance from exchange."""
        try:
            self._balance = self.client.get_account_balance("USDT")
        except Exception as e:
            logger.error(f"Cash reserve balance fetch failed: {e}")
        return self._balance

    @property
    def balance(self) -> float:
        return self._balance

    def get_status(self, total_portfolio_value: float) -> CashReserveStatus:
        """Calculate current cash reserve status.

        Args:
            total_portfolio_value: Total portfolio value across all tiers.
        """
        target_usd = total_portfolio_value * (self.target_pct / 100)
        current_pct = (
            (self._balance / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
        )

        deficit = max(0, target_usd - self._balance)
        surplus = max(0, self._balance - target_usd)

        is_underfunded = (self.target_pct - current_pct) > self.UNDERFUNDED_THRESHOLD_PCT
        is_overfunded = (current_pct - self.target_pct) > self.OVERFUNDED_THRESHOLD_PCT

        return CashReserveStatus(
            balance_usd=self._balance,
            target_usd=target_usd,
            target_pct=self.target_pct,
            current_pct=current_pct,
            is_underfunded=is_underfunded,
            is_overfunded=is_overfunded,
            deficit_usd=deficit,
            surplus_usd=surplus,
        )

    def tick(self, total_portfolio_value: float) -> CashReserveStatus:
        """Run one tick — update balance and return status."""
        self.update_balance()
        return self.get_status(total_portfolio_value)
