"""Portfolio Manager - Top-level orchestrator for 3-Tier Portfolio.

Manages Cash Reserve + Index Holdings + Hybrid Trading tiers.
Feature-flagged via PORTFOLIO_MANAGER=true env var.
"""

import logging
import time
from dataclasses import dataclass, field

from psycopg2.extras import RealDictCursor

from src.core.cohort_orchestrator import CohortOrchestrator
from src.portfolio.tiers.cash_reserve import CashReserveTier
from src.portfolio.tiers.index_holdings import IndexHoldingsTier
from src.portfolio.tiers.trading_tier import TradingTier
from src.tasks.base import get_db_connection
from src.utils.heartbeat import touch_heartbeat

logger = logging.getLogger("trading_bot")


@dataclass
class TierBreakdown:
    """Portfolio value breakdown by tier."""

    total_value: float = 0.0
    cash_value: float = 0.0
    cash_pct: float = 0.0
    index_value: float = 0.0
    index_pct: float = 0.0
    trading_value: float = 0.0
    trading_pct: float = 0.0
    targets: dict = field(default_factory=dict)


class PortfolioManager:
    """Top-level orchestrator managing all three portfolio tiers.

    Architecture:
        PortfolioManager
        ├── CashReserveTier (10%)  → USDT balance
        ├── IndexHoldingsTier (65%) → Top 20 crypto, buy-and-hold
        └── TradingTier (25%)      → CohortOrchestrator (6 cohorts)

    The manager:
    1. Initializes all tiers
    2. Ticks trading tier every 30s
    3. Updates index prices periodically
    4. Monitors tier drift for rebalancing
    """

    TICK_INTERVAL_SECONDS = 30
    INDEX_UPDATE_INTERVAL_SECONDS = 3600  # Update index prices hourly

    def __init__(self, client):
        self.client = client
        self.running = False

        # Load tier targets from DB or use defaults
        self._targets = {"cash_reserve": 10.0, "index_holdings": 65.0, "trading": 25.0}

        # Initialize tiers (lazy — actual init in initialize())
        self.cash_tier: CashReserveTier | None = None
        self.index_tier: IndexHoldingsTier | None = None
        self.trading_tier: TradingTier | None = None

        self._last_index_update: float = 0

    def _load_tier_targets(self):
        """Load tier target percentages from DB."""
        conn = get_db_connection()
        if not conn:
            return

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tier_name, target_pct FROM portfolio_tiers WHERE is_active = TRUE
                """)
                for row in cur.fetchall():
                    self._targets[row["tier_name"]] = float(row["target_pct"])
            logger.info(f"Loaded tier targets: {self._targets}")
        except Exception as e:
            logger.warning(f"Could not load tier targets from DB: {e}")
        finally:
            conn.close()

    def initialize(self) -> bool:
        """Initialize all three tiers.

        Returns:
            True if at least the trading tier initialized successfully.
        """
        logger.info("Initializing 3-Tier Portfolio Manager...")

        # Load targets from DB
        self._load_tier_targets()

        # 1. Cash Reserve Tier
        cash_target = self._targets.get("cash_reserve", 10.0)
        self.cash_tier = CashReserveTier(self.client, target_pct=cash_target)
        self.cash_tier.update_balance()
        logger.info(
            f"Cash Reserve Tier: target={cash_target}%, balance=${self.cash_tier.balance:.2f}"
        )

        # 2. Index Holdings Tier
        index_target = self._targets.get("index_holdings", 65.0)
        conn = get_db_connection()
        self.index_tier = IndexHoldingsTier(self.client, conn=conn, target_pct=index_target)
        self.index_tier.load_holdings()
        if conn:
            conn.close()
        logger.info(
            f"Index Holdings Tier: target={index_target}%, "
            f"holdings={len(self.index_tier._holdings)}"
        )

        # 3. Trading Tier (wraps CohortOrchestrator)
        trading_target = self._targets.get("trading", 25.0)
        orchestrator = CohortOrchestrator(client=self.client)
        self.trading_tier = TradingTier(orchestrator, target_pct=trading_target)

        if not self.trading_tier.initialize():
            logger.critical("Trading tier failed to initialize — no cohorts available")
            return False

        logger.info(
            f"Trading Tier: target={trading_target}%, cohorts={len(orchestrator.orchestrators)}"
        )

        return True

    def get_total_value(self) -> TierBreakdown:
        """Calculate total portfolio value and per-tier breakdown."""
        cash_value = self.cash_tier.balance if self.cash_tier else 0.0
        index_value = self.index_tier.get_total_value() if self.index_tier else 0.0

        conn = get_db_connection()
        trading_value = self.trading_tier.get_total_value(conn) if self.trading_tier else 0.0
        if conn:
            conn.close()

        total = cash_value + index_value + trading_value

        return TierBreakdown(
            total_value=total,
            cash_value=cash_value,
            cash_pct=(cash_value / total * 100) if total > 0 else 0,
            index_value=index_value,
            index_pct=(index_value / total * 100) if total > 0 else 0,
            trading_value=trading_value,
            trading_pct=(trading_value / total * 100) if total > 0 else 0,
            targets=self._targets.copy(),
        )

    def _update_tier_values_in_db(self, breakdown: TierBreakdown):
        """Update current percentages in portfolio_tiers table."""
        conn = get_db_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE portfolio_tiers SET
                        current_pct = %s, current_value_usd = %s, updated_at = NOW()
                    WHERE tier_name = 'cash_reserve'
                    """,
                    (breakdown.cash_pct, breakdown.cash_value),
                )
                cur.execute(
                    """
                    UPDATE portfolio_tiers SET
                        current_pct = %s, current_value_usd = %s, updated_at = NOW()
                    WHERE tier_name = 'index_holdings'
                    """,
                    (breakdown.index_pct, breakdown.index_value),
                )
                cur.execute(
                    """
                    UPDATE portfolio_tiers SET
                        current_pct = %s, current_value_usd = %s, updated_at = NOW()
                    WHERE tier_name = 'trading'
                    """,
                    (breakdown.trading_pct, breakdown.trading_value),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update tier values in DB: {e}")
        finally:
            conn.close()

    def tick(self) -> bool:
        """Run one tick of all tiers.

        Returns:
            True to continue, False to stop.
        """
        try:
            # Trading tier ticks every cycle (30s)
            if self.trading_tier and not self.trading_tier.tick():
                return False

            # Update cash balance
            if self.cash_tier:
                self.cash_tier.update_balance()

            # Update index prices hourly
            now = time.time()
            if now - self._last_index_update > self.INDEX_UPDATE_INTERVAL_SECONDS:
                self._update_index_prices()
                self._last_index_update = now

            touch_heartbeat()
            return True

        except Exception as e:
            logger.error(f"PortfolioManager tick error: {e}")
            return True  # Continue on error

    def _update_index_prices(self):
        """Update current prices for all index holdings."""
        if not self.index_tier:
            return

        try:
            from src.data.market_data import get_market_data

            market_data = get_market_data()

            for symbol, holding in self.index_tier._holdings.items():
                price = market_data.get_price(symbol)
                if price and price > 0:
                    holding.current_price = price

            # Check trailing stops
            triggered = self.index_tier.update_trailing_stops()
            if triggered:
                logger.warning(f"Index trailing stops triggered: {triggered}")

            # Save to DB
            conn = get_db_connection()
            if conn:
                self.index_tier.conn = conn
                self.index_tier.save_holdings()
                conn.close()

        except Exception as e:
            logger.error(f"Index price update failed: {e}")

    def run(self):
        """Main loop — runs all tiers until stopped."""
        self.running = True
        logger.info("PortfolioManager main loop starting...")

        # Initial allocation for trading tier
        if self.trading_tier:
            allocated = self.trading_tier.initial_allocation()
            logger.info(f"Trading tier initial allocation: {allocated} cohorts")

        while self.running:
            try:
                if not self.tick():
                    break
            except Exception as e:
                logger.error(f"PortfolioManager loop error: {e}")

            time.sleep(self.TICK_INTERVAL_SECONDS)

        logger.info("PortfolioManager stopped.")

    def stop(self):
        """Graceful shutdown."""
        self.running = False
        if self.trading_tier:
            self.trading_tier.stop()
        logger.info("PortfolioManager stop requested.")
