#!/usr/bin/env python3
"""
Binance Grid Trading Bot
Starte mit: python main.py
"""
import os
import sys
from dotenv import load_dotenv

# Füge src zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.bot import GridBot


def main():
    load_dotenv()

    # Konfiguration
    config = {
        'symbol': os.getenv('TRADING_PAIR', 'BTCUSDT'),
        'investment': float(os.getenv('INVESTMENT_AMOUNT', 10)),
        'testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true',
        'num_grids': 3,  # 3 Grids für 10€ (mehr macht keinen Sinn)
        'grid_range_percent': 3,  # ±3% vom aktuellen Preis
    }

    print(f"""
    ╔═══════════════════════════════════════════════╗
    ║         BINANCE GRID TRADING BOT              ║
    ╠═══════════════════════════════════════════════╣
    ║  Symbol:     {config['symbol']:<30} ║
    ║  Investment: {config['investment']:<30} ║
    ║  Testnet:    {str(config['testnet']):<30} ║
    ║  Grids:      {config['num_grids']:<30} ║
    ╚═══════════════════════════════════════════════╝
    """)

    if config['testnet']:
        print("⚠️  TESTNET MODUS - Kein echtes Geld!")
    else:
        print("🔴 LIVE MODUS - ECHTES GELD!")
        response = input("Fortfahren? (ja/nein): ")
        if response.lower() != 'ja':
            print("Abgebrochen.")
            return

    bot = GridBot(config)
    bot.run()


if __name__ == '__main__':
    main()
