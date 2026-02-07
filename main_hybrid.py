#!/usr/bin/env python3
"""
Hybrid Trading Bot - Cohort-Based Multi-Strategy System

Two modes:
1. PORTFOLIO_MANAGER=false (default): CohortOrchestrator only (trading tier)
2. PORTFOLIO_MANAGER=true: 3-Tier Portfolio (Cash + Index + Trading)

Start with: python main_hybrid.py
"""

import logging
import os
import signal
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.config import validate_environment

logger = logging.getLogger("trading_bot")


def _create_client():
    """Create Binance client based on environment."""
    paper_mode = os.getenv("PAPER_TRADING", "false").lower() == "true"
    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    if paper_mode:
        from src.api.paper_client import PaperBinanceClient

        initial = float(os.getenv("PAPER_INITIAL_USDT", "6000"))
        client = PaperBinanceClient(initial_usdt=initial)
        logger.info(f"Paper Trading mode — ${initial:.0f} initial USDT, real mainnet prices")
    else:
        from src.api.binance_client import BinanceClient

        if not testnet:
            print("LIVE MODUS - ECHTES GELD!")
            response = input("Fortfahren? (ja/nein): ")
            if response.lower() != "ja":
                print("Abgebrochen.")
                sys.exit(0)

        client = BinanceClient(testnet=testnet)

    return client, paper_mode, testnet


def _run_portfolio_manager(client, paper_mode, testnet):
    """Run the 3-Tier Portfolio Manager."""
    from src.portfolio.portfolio_manager import PortfolioManager

    manager = PortfolioManager(client=client)

    if not manager.initialize():
        logger.critical("Portfolio Manager failed to initialize. Aborting.")
        sys.exit(1)

    breakdown = manager.get_total_value()

    print(f"""
    ╔═══════════════════════════════════════════════════════╗
    ║       3-TIER PORTFOLIO SYSTEM                         ║
    ╠═══════════════════════════════════════════════════════╣
    ║  Mode:       {"PAPER" if paper_mode else "TESTNET" if testnet else "LIVE":<38} ║
    ║  Cash:       {breakdown.cash_pct:5.1f}% (target {manager._targets["cash_reserve"]:.0f}%){"":>18}║
    ║  Index:      {breakdown.index_pct:5.1f}% (target {manager._targets["index_holdings"]:.0f}%){"":>18}║
    ║  Trading:    {breakdown.trading_pct:5.1f}% (target {manager._targets["trading"]:.0f}%){"":>18}║
    ║  Total:      ${breakdown.total_value:<40.2f}║
    ╚═══════════════════════════════════════════════════════╝
    """)

    signal.signal(signal.SIGTERM, lambda _s, _f: manager.stop())
    manager.run()


def _run_cohort_orchestrator(client, paper_mode, testnet):
    """Run the classic CohortOrchestrator (trading only)."""
    from src.core.cohort_orchestrator import CohortOrchestrator

    orchestrator = CohortOrchestrator(client=client)

    if not orchestrator.initialize():
        logger.critical("No cohorts could be initialized. Aborting.")
        sys.exit(1)

    print(f"""
    ╔═══════════════════════════════════════════════╗
    ║       COHORT TRADING SYSTEM                   ║
    ╠═══════════════════════════════════════════════╣
    ║  Mode:       {"PAPER" if paper_mode else "TESTNET" if testnet else "LIVE":<30} ║
    ║  Cohorts:    {len(orchestrator.orchestrators):<30} ║""")

    for name, info in orchestrator.cohort_configs.items():
        cap = info["current_capital"]
        grid = info["grid_range_pct"]
        risk = info["risk_tolerance"]
        print(f"    ║  {name:<12} ${cap:<6.0f} grid={grid}% risk={risk:<12} ║")

    print("""    ╚═══════════════════════════════════════════════╝
    """)

    logger.info("Running initial scan and allocation for all cohorts...")
    allocated = orchestrator.initial_allocation()

    if allocated == 0:
        logger.critical("No cohorts got allocations - CoinScanner/DB not working. Aborting.")
        sys.exit(1)

    logger.info(f"{allocated}/{len(orchestrator.orchestrators)} cohorts allocated")

    signal.signal(signal.SIGTERM, lambda _s, _f: orchestrator.stop())
    orchestrator.run()


def main():
    load_dotenv()

    env_ok, warnings = validate_environment()
    for w in warnings:
        print(f"  WARNING: {w}")
    if not env_ok:
        sys.exit(1)

    client, paper_mode, testnet = _create_client()

    portfolio_mode = os.getenv("PORTFOLIO_MANAGER", "false").lower() == "true"

    if portfolio_mode:
        logger.info("Starting in 3-Tier Portfolio Manager mode")
        _run_portfolio_manager(client, paper_mode, testnet)
    else:
        logger.info("Starting in Cohort Trading mode")
        _run_cohort_orchestrator(client, paper_mode, testnet)


if __name__ == "__main__":
    main()
