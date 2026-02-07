"""Trading Tier - Thin wrapper around CohortOrchestrator for hybrid trading."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("trading_bot")


@dataclass
class TradingTierStatus:
    """Current trading tier state."""

    total_value_usd: float
    target_value_usd: float
    target_pct: float
    cohort_count: int
    active_symbols: int
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    cohort_details: dict = field(default_factory=dict)


class TradingTier:
    """Wrapper around existing CohortOrchestrator.

    The trading tier delegates all actual trading to the cohort system.
    It provides a clean interface for the PortfolioManager to:
    - Set capital budget
    - Query realized/unrealized P&L
    - Get status for reporting
    """

    def __init__(self, orchestrator, target_pct: float = 25.0):
        self.orchestrator = orchestrator
        self.target_pct = target_pct
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the cohort orchestrator."""
        if not self._initialized:
            self._initialized = self.orchestrator.initialize()
        return self._initialized

    def initial_allocation(self) -> int:
        """Run initial scan and allocation for all cohorts."""
        return self.orchestrator.initial_allocation()

    def tick(self) -> bool:
        """Run one tick of all cohort orchestrators."""
        return self.orchestrator.tick()

    def stop(self):
        """Stop all orchestrators gracefully."""
        self.orchestrator.stop()

    def get_realized_pnl(self, conn) -> float:
        """Query total realized P&L from closed trade_pairs."""
        if not conn:
            return 0.0

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM trade_pairs
                    WHERE status = 'closed' AND net_pnl IS NOT NULL
                """)
                result = cur.fetchone()
                return float(result["total_pnl"]) if result else 0.0
        except Exception as e:
            logger.error(f"Failed to query trading tier P&L: {e}")
            return 0.0

    def get_total_value(self, conn) -> float:
        """Calculate total trading tier value (open positions + allocated capital)."""
        if not conn:
            return 0.0

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Sum of current_capital across active cohorts
                cur.execute("""
                    SELECT COALESCE(SUM(current_capital), 0) as total
                    FROM cohorts WHERE is_active = TRUE
                """)
                result = cur.fetchone()
                return float(result["total"]) if result else 0.0
        except Exception as e:
            logger.error(f"Failed to query trading tier value: {e}")
            return 0.0

    def get_status(self, total_portfolio_value: float, conn=None) -> TradingTierStatus:
        """Return current trading tier status."""
        target_value = total_portfolio_value * (self.target_pct / 100)
        total_value = self.get_total_value(conn) if conn else 0.0
        realized_pnl = self.get_realized_pnl(conn) if conn else 0.0

        # Collect per-cohort status
        cohort_details = {}
        if hasattr(self.orchestrator, "cohort_configs"):
            for name, info in self.orchestrator.cohort_configs.items():
                cohort_details[name] = {
                    "capital": info.get("current_capital", 0),
                    "risk": info.get("risk_tolerance", "unknown"),
                }

        active_symbols = 0
        if hasattr(self.orchestrator, "orchestrators"):
            for orch in self.orchestrator.orchestrators.values():
                active_symbols += len(getattr(orch, "symbols", {}))

        return TradingTierStatus(
            total_value_usd=total_value,
            target_value_usd=target_value,
            target_pct=self.target_pct,
            cohort_count=len(getattr(self.orchestrator, "orchestrators", {})),
            active_symbols=active_symbols,
            realized_pnl=realized_pnl,
            cohort_details=cohort_details,
        )
