#!/usr/bin/env python3
"""
Hybrid Trading Bot - Cohort-Based Multi-Strategy System

Runs 4 independent cohorts (conservative, balanced, aggressive, baseline),
each with its own HybridOrchestrator, capital allocation, and coin selection.

Start with: python main_hybrid.py
"""

import logging
import os
import signal
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.binance_client import BinanceClient
from src.core.cohort_orchestrator import CohortOrchestrator
from src.core.config import validate_environment

logger = logging.getLogger("trading_bot")


def main():
    load_dotenv()

    env_ok, warnings = validate_environment()
    for w in warnings:
        print(f"  WARNING: {w}")
    if not env_ok:
        sys.exit(1)

    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    if not testnet:
        print("LIVE MODUS - ECHTES GELD!")
        response = input("Fortfahren? (ja/nein): ")
        if response.lower() != "ja":
            print("Abgebrochen.")
            return

    # Create shared Binance client
    client = BinanceClient(testnet=testnet)

    # Create cohort orchestrator
    orchestrator = CohortOrchestrator(client=client)

    if not orchestrator.initialize():
        logger.critical("No cohorts could be initialized. Aborting.")
        sys.exit(1)

    # Print startup banner
    print(f"""
    ╔═══════════════════════════════════════════════╗
    ║       COHORT TRADING SYSTEM                   ║
    ╠═══════════════════════════════════════════════╣
    ║  Testnet:    {str(testnet):<30} ║
    ║  Cohorts:    {len(orchestrator.orchestrators):<30} ║""")

    for name, info in orchestrator.cohort_configs.items():
        cap = info["current_capital"]
        grid = info["grid_range_pct"]
        risk = info["risk_tolerance"]
        print(f"    ║  {name:<12} ${cap:<6.0f} grid={grid}% risk={risk:<12} ║")

    print("""    ╚═══════════════════════════════════════════════╝
    """)

    # Initial scan and allocation for all cohorts
    logger.info("Running initial scan and allocation for all cohorts...")
    allocated = orchestrator.initial_allocation()

    if allocated == 0:
        logger.critical("No cohorts got allocations - CoinScanner/DB not working. Aborting.")
        sys.exit(1)

    logger.info(f"{allocated}/{len(orchestrator.orchestrators)} cohorts allocated")

    # Handle SIGTERM for graceful Docker shutdown
    signal.signal(signal.SIGTERM, lambda _s, _f: orchestrator.stop())

    # Start the main loop
    orchestrator.run()


if __name__ == "__main__":
    main()
