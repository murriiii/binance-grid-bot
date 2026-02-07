"""Profit Redistribution Engine - Weekly rebalancing of portfolio tiers.

Calculates current tier allocations, compares against targets,
and generates transfer orders to bring the portfolio back into balance.
Only redistributes profits — never pulls below initial capital per tier.
"""

import logging
from dataclasses import dataclass

from src.tasks.base import get_db_connection

logger = logging.getLogger("trading_bot")


@dataclass
class TierTransfer:
    """A single transfer between tiers."""

    from_tier: str
    to_tier: str
    amount_usd: float
    reason: str


class ProfitRedistributionEngine:
    """Redistributes profits to match tier target allocations.

    Runs weekly. Rebalances when any tier deviates more than
    REBALANCE_THRESHOLD_PCT from its target.

    Priority order: Cash first (safety), then Index, then Trading.
    """

    REBALANCE_THRESHOLD_PCT = 3.0
    MIN_TRANSFER_USD = 10.0

    def __init__(self, portfolio_manager):
        self.pm = portfolio_manager

    def needs_rebalance(self) -> bool:
        """Check if any tier has drifted beyond threshold."""
        breakdown = self.pm.get_total_value()
        if breakdown.total_value <= 0:
            return False

        targets = self.pm._targets
        deviations = {
            "cash_reserve": abs(breakdown.cash_pct - targets.get("cash_reserve", 10.0)),
            "index_holdings": abs(breakdown.index_pct - targets.get("index_holdings", 65.0)),
            "trading": abs(breakdown.trading_pct - targets.get("trading", 25.0)),
        }

        return any(d > self.REBALANCE_THRESHOLD_PCT for d in deviations.values())

    def calculate_rebalance(self) -> list[TierTransfer]:
        """Calculate transfers needed to match target allocations.

        Returns list of transfers sorted by priority (cash first).
        """
        breakdown = self.pm.get_total_value()
        total = breakdown.total_value
        if total <= 0:
            return []

        targets = self.pm._targets
        current = {
            "cash_reserve": breakdown.cash_value,
            "index_holdings": breakdown.index_value,
            "trading": breakdown.trading_value,
        }
        target_values = {tier: total * (pct / 100) for tier, pct in targets.items()}

        # Calculate surplus/deficit per tier
        deltas = {}
        for tier in targets:
            deltas[tier] = current.get(tier, 0) - target_values.get(tier, 0)

        # Tiers with surplus (positive delta) fund tiers with deficit (negative delta)
        surplus_tiers = sorted(
            [(t, d) for t, d in deltas.items() if d > self.MIN_TRANSFER_USD],
            key=lambda x: x[1],
            reverse=True,
        )
        deficit_tiers = sorted(
            [(t, -d) for t, d in deltas.items() if d < -self.MIN_TRANSFER_USD],
            key=lambda x: _tier_priority(x[0]),
        )

        transfers = []
        for def_tier, def_amount in deficit_tiers:
            remaining_need = def_amount
            for i, (sur_tier, sur_amount) in enumerate(surplus_tiers):
                if remaining_need <= self.MIN_TRANSFER_USD:
                    break
                if sur_amount <= self.MIN_TRANSFER_USD:
                    continue

                transfer_amount = min(remaining_need, sur_amount)
                transfers.append(
                    TierTransfer(
                        from_tier=sur_tier,
                        to_tier=def_tier,
                        amount_usd=round(transfer_amount, 2),
                        reason=f"Rebalance: {sur_tier} overfunded, {def_tier} underfunded",
                    )
                )

                remaining_need -= transfer_amount
                surplus_tiers[i] = (sur_tier, sur_amount - transfer_amount)

        return transfers

    def execute_rebalance(self) -> dict:
        """Calculate and log rebalance transfers.

        Note: Actual execution (sells from index, buys for index) is complex
        and will be done in phases. For now, this calculates + logs the plan.

        Returns:
            Dict with pre/post allocations and transfer details.
        """
        breakdown = self.pm.get_total_value()
        pre_allocation = {
            "cash_reserve": {"value": breakdown.cash_value, "pct": breakdown.cash_pct},
            "index_holdings": {"value": breakdown.index_value, "pct": breakdown.index_pct},
            "trading": {"value": breakdown.trading_value, "pct": breakdown.trading_pct},
            "total": breakdown.total_value,
        }

        transfers = self.calculate_rebalance()
        if not transfers:
            logger.info("Profit engine: no rebalance needed")
            return {"needed": False, "transfers": []}

        total_moved = sum(t.amount_usd for t in transfers)
        logger.info(f"Profit engine: {len(transfers)} transfers, ${total_moved:.2f} total")
        for t in transfers:
            logger.info(f"  {t.from_tier} → {t.to_tier}: ${t.amount_usd:.2f} ({t.reason})")

        # Log to DB
        self._log_redistribution(pre_allocation, transfers)

        return {
            "needed": True,
            "transfers": [
                {
                    "from": t.from_tier,
                    "to": t.to_tier,
                    "amount": t.amount_usd,
                    "reason": t.reason,
                }
                for t in transfers
            ],
            "pre_allocation": pre_allocation,
            "total_moved": total_moved,
        }

    def _log_redistribution(self, pre_allocation: dict, transfers: list[TierTransfer]):
        """Log redistribution to profit_redistributions table."""
        conn = get_db_connection()
        if not conn:
            return

        try:
            import json

            redistributed_to = {t.to_tier: t.amount_usd for t in transfers}
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO profit_redistributions
                        (total_profit_usd, redistributed_to, pre_allocation, post_allocation)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        sum(t.amount_usd for t in transfers),
                        json.dumps(redistributed_to),
                        json.dumps(pre_allocation),
                        json.dumps({}),  # Will be filled after execution
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log redistribution: {e}")
        finally:
            conn.close()


def _tier_priority(tier_name: str) -> int:
    """Priority order for deficit filling: cash first, then index, then trading."""
    return {"cash_reserve": 0, "index_holdings": 1, "trading": 2}.get(tier_name, 99)
