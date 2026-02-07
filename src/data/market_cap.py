"""CoinGecko market cap data for Index Holdings tier."""

import logging
import time

logger = logging.getLogger("trading_bot")

# Simple cache to avoid rate limiting
_cache: dict = {}
_cache_ts: float = 0.0
CACHE_TTL_SECONDS = 3600  # 1 hour


def get_top_coins_by_market_cap(top_n: int = 20) -> list[dict]:
    """Fetch top N cryptocurrencies by market cap from CoinGecko.

    Returns:
        List of {"symbol": "BTC", "market_cap": 1234567890, "rank": 1, "price": 50000}
    """
    global _cache_ts

    cache_key = f"top_{top_n}"
    if cache_key in _cache and (time.time() - _cache_ts) < CACHE_TTL_SECONDS:
        return _cache[cache_key]

    try:
        from src.api.http_client import get_http_client

        http = get_http_client()
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": top_n + 10,  # Extra to account for stablecoins
            "page": 1,
            "sparkline": "false",
        }

        data = http.get(url, params=params, api_type="default")

        if not isinstance(data, list):
            logger.error(f"CoinGecko returned unexpected format: {type(data)}")
            return []

        result = []
        rank = 0
        for coin in data:
            symbol = (coin.get("symbol") or "").upper()
            market_cap = coin.get("market_cap") or 0
            price = coin.get("current_price") or 0

            if market_cap <= 0:
                continue

            rank += 1
            result.append(
                {
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "rank": rank,
                    "price": price,
                    "name": coin.get("name", ""),
                }
            )

            if len(result) >= top_n:
                break

        _cache[cache_key] = result
        _cache_ts = time.time()
        logger.info(f"Fetched top {len(result)} coins by market cap from CoinGecko")
        return result

    except Exception as e:
        logger.error(f"CoinGecko API error: {e}")
        # Return cached data if available
        if cache_key in _cache:
            logger.info("Using cached market cap data")
            return _cache[cache_key]
        return []
