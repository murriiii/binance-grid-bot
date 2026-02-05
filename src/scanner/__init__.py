"""
Scanner Module für Multi-Coin Opportunity Detection.

Scannt die Watchlist nach Trading-Opportunities basierend auf:
- Technische Indikatoren (RSI, MACD, Divergenzen)
- Volume Spikes
- Sentiment-Daten
- Whale-Aktivität
"""

from src.scanner.coin_scanner import CoinScanner, get_coin_scanner
from src.scanner.opportunity import Opportunity, OpportunityDirection, OpportunityRisk

__all__ = [
    "CoinScanner",
    "Opportunity",
    "OpportunityDirection",
    "OpportunityRisk",
    "get_coin_scanner",
]
