"""
Portfolio Module für Multi-Coin Kapitalverteilung.

Verteilt Kapital intelligent auf Coins basierend auf:
- Opportunity Scores
- Risiko-Constraints
- Korrelationen
- Kelly-Criterion
"""

from src.portfolio.allocator import PortfolioAllocator, get_portfolio_allocator
from src.portfolio.constraints import AllocationConstraints

__all__ = [
    "AllocationConstraints",
    "PortfolioAllocator",
    "get_portfolio_allocator",
]
