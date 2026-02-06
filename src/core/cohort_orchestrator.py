"""Cohort Orchestrator - manages 4 independent HybridOrchestrator instances.

Each cohort runs its own strategy (conservative, balanced, aggressive, baseline)
with its own capital allocation, coin selection, and state persistence.
All cohorts share the same Binance client (single testnet account).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.api.binance_client import BinanceClient
from src.core.cohort_manager import CohortManager
from src.core.hybrid_config import HybridConfig
from src.core.hybrid_orchestrator import HybridOrchestrator
from src.utils.heartbeat import touch_heartbeat

logger = logging.getLogger("trading_bot")


class CohortOrchestrator:
    """Top-level orchestrator that manages one HybridOrchestrator per cohort.

    Lifecycle:
        1. Load cohorts from DB via CohortManager
        2. Create HybridConfig.from_cohort() for each cohort
        3. Create HybridOrchestrator per cohort (shared BinanceClient)
        4. Initial scan_and_allocate() per cohort
        5. Main loop: tick() all orchestrators every 30s
    """

    TICK_INTERVAL_SECONDS = 30
    MAX_CONSECUTIVE_ERRORS = 5

    def __init__(self, client: BinanceClient | None = None):
        self.client = client or BinanceClient(
            testnet=True,
        )
        self.orchestrators: dict[str, HybridOrchestrator] = {}
        self.cohort_configs: dict[str, dict[str, Any]] = {}
        self.running = False
        self.consecutive_errors = 0

    def initialize(self) -> bool:
        """Load cohorts from DB and create per-cohort orchestrators.

        Returns True if at least one cohort was successfully initialized.
        """
        cohort_manager = CohortManager.get_instance()
        cohorts = cohort_manager.get_active_cohorts()

        if not cohorts:
            logger.error("CohortOrchestrator: no active cohorts found")
            return False

        success_count = 0
        for cohort in cohorts:
            try:
                config = HybridConfig.from_cohort(cohort)
                valid, errors = config.validate()
                if not valid:
                    logger.error(f"CohortOrchestrator: invalid config for {cohort.name}: {errors}")
                    continue

                orch = HybridOrchestrator(
                    config=config,
                    client=self.client,
                    cohort_id=cohort.id,
                    cohort_name=cohort.name,
                )

                self.orchestrators[cohort.name] = orch
                self.cohort_configs[cohort.name] = {
                    "id": cohort.id,
                    "strategy": cohort.description,
                    "grid_range_pct": cohort.config.grid_range_pct,
                    "risk_tolerance": cohort.config.risk_tolerance,
                    "starting_capital": cohort.starting_capital,
                    "current_capital": cohort.current_capital,
                }
                success_count += 1
                logger.info(
                    f"CohortOrchestrator: initialized {cohort.name} "
                    f"(${cohort.current_capital:.0f}, "
                    f"grid={cohort.config.grid_range_pct}%)"
                )
            except Exception as e:
                logger.error(f"CohortOrchestrator: failed to init {cohort.name}: {e}")

        logger.info(f"CohortOrchestrator: {success_count}/{len(cohorts)} cohorts initialized")
        return success_count > 0

    def initial_allocation(self) -> int:
        """Run initial scan_and_allocate for each cohort.

        Returns the number of cohorts that got allocations.
        """
        allocated = 0
        for name, orch in self.orchestrators.items():
            try:
                result = orch.scan_and_allocate()
                if result and result.allocations:
                    allocated += 1
                    symbols = ", ".join(result.allocations.keys())
                    logger.info(
                        f"CohortOrchestrator: {name} allocated "
                        f"${result.total_allocated:.2f} -> [{symbols}]"
                    )
                else:
                    logger.warning(f"CohortOrchestrator: {name} got no allocations")
            except Exception as e:
                logger.error(f"CohortOrchestrator: {name} allocation failed: {e}")

        return allocated

    def tick(self) -> bool:
        """Execute one tick across all cohort orchestrators.

        Returns True to continue, False to stop.
        """
        for name, orch in self.orchestrators.items():
            try:
                orch.tick()
            except Exception as e:
                logger.error(f"CohortOrchestrator: {name} tick error: {e}")

        self.consecutive_errors = 0
        touch_heartbeat()
        return True

    def run(self) -> None:
        """Main loop - runs until stopped."""
        if not self.orchestrators:
            logger.error("CohortOrchestrator: no orchestrators configured")
            return

        self.running = True

        # Load saved state for each orchestrator
        for name, orch in self.orchestrators.items():
            orch.load_state()

        logger.info(f"CohortOrchestrator: starting {len(self.orchestrators)} cohorts")

        try:
            while self.running:
                try:
                    if not self.tick():
                        break
                    time.sleep(self.TICK_INTERVAL_SECONDS)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.consecutive_errors += 1
                    logger.error(
                        f"CohortOrchestrator: error ({self.consecutive_errors}/"
                        f"{self.MAX_CONSECUTIVE_ERRORS}): {e}"
                    )
                    if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        logger.critical("CohortOrchestrator: too many errors, stopping")
                        break
                    time.sleep(30 * self.consecutive_errors)
        except KeyboardInterrupt:
            logger.info("CohortOrchestrator: stopped (Ctrl+C)")

        self.running = False
        self.save_state()

    def stop(self) -> None:
        """Stop all orchestrators gracefully."""
        self.running = False
        for orch in self.orchestrators.values():
            orch.stop()

    def save_state(self) -> None:
        """Save state for all orchestrators."""
        for name, orch in self.orchestrators.items():
            try:
                orch.save_state()
            except Exception as e:
                logger.error(f"CohortOrchestrator: {name} save_state error: {e}")

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Return status for all cohorts (used by Telegram summary)."""
        statuses = {}
        for name, orch in self.orchestrators.items():
            try:
                status = orch.get_status()
                status["cohort_config"] = self.cohort_configs.get(name, {})
                statuses[name] = status
            except Exception as e:
                logger.error(f"CohortOrchestrator: {name} get_status error: {e}")
                statuses[name] = {"error": str(e)}
        return statuses
