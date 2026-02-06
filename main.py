#!/usr/bin/env python3
"""
Binance Grid Trading Bot
Starte mit: python main.py
"""

import os
import signal
import sys

from dotenv import load_dotenv

# Füge src zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.bot import GridBot
from src.core.config import BotConfig


def main():
    load_dotenv()

    config = BotConfig.from_env()

    is_valid, errors = config.validate()
    if not is_valid:
        print("Config validation failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"""
    ╔═══════════════════════════════════════════════╗
    ║         BINANCE GRID TRADING BOT              ║
    ╠═══════════════════════════════════════════════╣
    ║  Symbol:     {config.symbol:<30} ║
    ║  Investment: {config.investment:<30} ║
    ║  Testnet:    {str(config.testnet):<30} ║
    ║  Grids:      {config.num_grids:<30} ║
    ║  Range:      ±{config.grid_range_percent:<28}%║
    ╚═══════════════════════════════════════════════╝
    """)

    if config.testnet:
        print("  TESTNET MODUS - Kein echtes Geld!")
    else:
        print("  LIVE MODUS - ECHTES GELD!")
        response = input("Fortfahren? (ja/nein): ")
        if response.lower() != "ja":
            print("Abgebrochen.")
            return

    bot = GridBot(config.to_dict())
    signal.signal(signal.SIGTERM, lambda _s, _f: bot.stop())
    bot.run()


if __name__ == "__main__":
    main()
