#!/usr/bin/env python3
"""
Hybrid Trading Bot - Regime-Adaptive Multi-Coin System

Entry point for the hybrid orchestrator that switches between
HOLD (bull), GRID (sideways), and CASH (bear) modes based on
market regime detection.

Start with: python main_hybrid.py
"""

import logging
import os
import signal
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.binance_client import BinanceClient
from src.core.hybrid_config import HybridConfig
from src.core.hybrid_orchestrator import HybridOrchestrator

logger = logging.getLogger("trading_bot")


def main():
    load_dotenv()

    # Load config from environment
    config = HybridConfig.from_env()
    valid, errors = config.validate()

    if not valid:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    print(f"""
    ╔═══════════════════════════════════════════════╗
    ║       HYBRID TRADING BOT                      ║
    ╠═══════════════════════════════════════════════╣
    ║  Mode:       {config.initial_mode:<30} ║
    ║  Switching:  {str(config.enable_mode_switching):<30} ║
    ║  Investment: ${config.total_investment:<29} ║
    ║  Max Coins:  {config.max_symbols:<30} ║
    ║  Testnet:    {str(testnet):<30} ║
    ╚═══════════════════════════════════════════════╝
    """)

    if not testnet:
        print("LIVE MODUS - ECHTES GELD!")
        response = input("Fortfahren? (ja/nein): ")
        if response.lower() != "ja":
            print("Abgebrochen.")
            return

    # Create shared Binance client
    client = BinanceClient(testnet=testnet)

    # Create orchestrator
    orchestrator = HybridOrchestrator(config=config, client=client)

    # Initial scan and allocation
    logger.info("Running initial scan and allocation...")
    result = orchestrator.scan_and_allocate()

    if not result or not result.allocations:
        logger.warning("No initial allocations - using fallback symbol")
        fallback_symbol = os.getenv("TRADING_PAIR", "BTCUSDT")
        orchestrator.add_symbol(fallback_symbol, config.total_investment * 0.85)

    # Handle SIGTERM for graceful Docker shutdown
    signal.signal(signal.SIGTERM, lambda _s, _f: orchestrator.stop())

    # Start the main loop
    orchestrator.run()


if __name__ == "__main__":
    main()
