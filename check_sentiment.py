#!/usr/bin/env python3
"""
Sentiment Check
Zeigt aktuelles Markt-Sentiment aus kostenlosen Quellen

Keine API Keys nötig!
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.sentiment import print_sentiment_report

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║              KRYPTO SENTIMENT ANALYZER                            ║
    ╠═══════════════════════════════════════════════════════════════════╣
    ║  Daten von: Fear & Greed Index, CoinGecko                         ║
    ║  Keine API Keys nötig!                                            ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)

    print_sentiment_report()
