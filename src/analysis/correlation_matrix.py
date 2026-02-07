"""D6: Real correlation matrix from historical price data.

Computes Pearson correlation between coin pairs using 60-day daily returns
from Binance mainnet. Used by PortfolioAllocator to penalize highly
correlated positions.
"""

import logging
from datetime import datetime, timedelta

import numpy as np

from src.api.http_client import get_http_client
from src.utils.singleton import SingletonMixin

logger = logging.getLogger("trading_bot")


class CorrelationCalculator(SingletonMixin):
    """Computes and caches pairwise correlation matrix from daily returns."""

    LOOKBACK_DAYS = 60
    CACHE_TTL_HOURS = 24

    def __init__(self):
        self.http = get_http_client()
        self._cache: dict[str, tuple[datetime, np.ndarray]] = {}
        self._returns_cache: dict[str, tuple[datetime, np.ndarray]] = {}

    def _fetch_daily_returns(self, symbol: str) -> np.ndarray | None:
        """Fetch daily close prices from Binance mainnet and compute returns."""
        cache_key = symbol
        now = datetime.now()
        if cache_key in self._returns_cache:
            cached_time, cached_returns = self._returns_cache[cache_key]
            if now - cached_time < timedelta(hours=self.CACHE_TTL_HOURS):
                return cached_returns

        try:
            data = self.http.get(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": symbol.upper(),
                    "interval": "1d",
                    "limit": self.LOOKBACK_DAYS + 1,
                },
                timeout=10,
            )
            if not data or len(data) < 10:
                return None

            closes = np.array([float(candle[4]) for candle in data])
            returns = np.diff(closes) / closes[:-1]

            self._returns_cache[cache_key] = (now, returns)
            return returns

        except Exception as e:
            logger.debug(f"Correlation: failed to fetch returns for {symbol}: {e}")
            return None

    def compute_correlation_matrix(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        """Compute pairwise Pearson correlation matrix for given symbols.

        Returns dict of dicts: matrix[sym_a][sym_b] = correlation coefficient.
        Only includes pairs where both symbols had sufficient data.
        """
        returns_map: dict[str, np.ndarray] = {}
        for sym in symbols:
            r = self._fetch_daily_returns(sym)
            if r is not None and len(r) >= 10:
                returns_map[sym] = r

        matrix: dict[str, dict[str, float]] = {}
        valid_symbols = list(returns_map.keys())

        for i, sym_a in enumerate(valid_symbols):
            matrix[sym_a] = {}
            for j, sym_b in enumerate(valid_symbols):
                if i == j:
                    matrix[sym_a][sym_b] = 1.0
                elif j < i and sym_b in matrix and sym_a in matrix[sym_b]:
                    matrix[sym_a][sym_b] = matrix[sym_b][sym_a]
                else:
                    r_a = returns_map[sym_a]
                    r_b = returns_map[sym_b]
                    min_len = min(len(r_a), len(r_b))
                    if min_len < 10:
                        continue
                    corr = float(np.corrcoef(r_a[-min_len:], r_b[-min_len:])[0, 1])
                    matrix[sym_a][sym_b] = round(corr, 4)

        return matrix

    def get_highly_correlated_pairs(
        self, symbols: list[str], threshold: float = 0.7
    ) -> list[tuple[str, str, float]]:
        """Find pairs with correlation above threshold.

        Returns list of (symbol_a, symbol_b, correlation) tuples.
        """
        matrix = self.compute_correlation_matrix(symbols)
        pairs = []
        seen = set()

        for sym_a, row in matrix.items():
            for sym_b, corr in row.items():
                if sym_a == sym_b:
                    continue
                pair_key = tuple(sorted([sym_a, sym_b]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                if abs(corr) >= threshold:
                    pairs.append((sym_a, sym_b, corr))

        return sorted(pairs, key=lambda x: abs(x[2]), reverse=True)

    def close(self):
        """Clear caches."""
        self._cache.clear()
        self._returns_cache.clear()
