"""
Sentiment Data Aggregator
Sammelt Sentiment-Daten aus kostenlosen Quellen

Quellen:
- Fear & Greed Index (Alternative.me)
- CoinGecko Social Stats
- Reddit Activity (optional)
- Google Trends (optional)
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from src.api.http_client import HTTPClientError, get_http_client
from src.core.config import get_config

logger = logging.getLogger("trading_bot")


@dataclass
class SentimentScore:
    """Aggregierter Sentiment-Score"""

    timestamp: datetime
    symbol: str

    # Einzelne Metriken
    fear_greed: int  # 0-100 (0=Extreme Fear, 100=Extreme Greed)
    social_score: float  # 0-100 normalisiert
    reddit_activity: float  # Posts/Comments pro Tag (normalisiert)
    google_trend: float  # 0-100

    # Aggregiert
    overall_score: float  # Gewichteter Durchschnitt
    signal: str  # "BULLISH", "BEARISH", "NEUTRAL"
    reasoning: str  # Erklärung


class FearGreedIndex:
    """
    Alternative.me Fear & Greed Index
    Kostenlos, keine API Keys nötig!

    0-24: Extreme Fear (Kaufsignal?)
    25-49: Fear
    50-74: Greed
    75-100: Extreme Greed (Verkaufssignal?)
    """

    def __init__(self):
        self.http = get_http_client()
        self.config = get_config()

    def get_current(self) -> dict:
        """Aktueller Fear & Greed Index"""
        try:
            data = self.http.get(self.config.api.fear_greed_url, api_type="default")
            fg_data = data["data"][0]

            return {
                "value": int(fg_data["value"]),
                "classification": fg_data["value_classification"],
                "timestamp": datetime.fromtimestamp(int(fg_data["timestamp"])),
            }
        except HTTPClientError as e:
            logger.warning(f"Fear & Greed API Fehler: {e}")
            return {"value": 50, "classification": "Neutral", "timestamp": datetime.now()}

    def get_historical(self, days: int = 30) -> list[dict]:
        """Historische Fear & Greed Daten"""
        try:
            data = self.http.get(
                f"{self.config.api.fear_greed_url}?limit={days}", api_type="default"
            )

            return [
                {
                    "value": int(d["value"]),
                    "classification": d["value_classification"],
                    "timestamp": datetime.fromtimestamp(int(d["timestamp"])),
                }
                for d in data["data"]
            ]
        except HTTPClientError as e:
            logger.warning(f"Fear & Greed Historical Fehler: {e}")
            return []


class CoinGeckoSentiment:
    """
    CoinGecko API - Kostenlos (rate-limited)
    Liefert: Community Score, Developer Score, Social Stats
    """

    # Mapping von unserem Symbol zu CoinGecko ID
    SYMBOL_TO_ID = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "ARB": "arbitrum",
        "OP": "optimism",
        "INJ": "injective-protocol",
    }

    def __init__(self):
        self.http = get_http_client()
        self.config = get_config()

    def get_coin_data(self, symbol: str) -> dict | None:
        """Holt Community und Developer Stats für einen Coin"""
        coin_id = self.SYMBOL_TO_ID.get(symbol.upper())
        if not coin_id:
            return None

        try:
            data = self.http.get(
                f"{self.config.api.coingecko_url}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "true",
                    "developer_data": "true",
                },
                api_type="default",
            )

            community = data.get("community_data", {})
            developer = data.get("developer_data", {})
            sentiment = data.get("sentiment_votes_up_percentage", 50)

            return {
                "symbol": symbol,
                "name": data.get("name"),
                "sentiment_up": sentiment,
                "sentiment_down": 100 - sentiment if sentiment else 50,
                "twitter_followers": community.get("twitter_followers", 0),
                "reddit_subscribers": community.get("reddit_subscribers", 0),
                "reddit_active_48h": community.get("reddit_accounts_active_48h", 0),
                "telegram_members": community.get("telegram_channel_user_count", 0),
                "github_stars": developer.get("stars", 0),
                "github_commits_4w": developer.get("commit_count_4_weeks", 0),
                "coingecko_score": data.get("coingecko_score", 0),
                "community_score": data.get("community_score", 0),
                "developer_score": data.get("developer_score", 0),
            }

        except HTTPClientError as e:
            logger.warning(f"CoinGecko API Fehler für {symbol}: {e}")
            return None

    def get_trending(self) -> list[dict]:
        """Top 7 trending coins auf CoinGecko"""
        try:
            data = self.http.get(
                f"{self.config.api.coingecko_url}/search/trending", api_type="default"
            )

            trending = []
            for item in data.get("coins", []):
                coin = item["item"]
                trending.append(
                    {
                        "symbol": coin["symbol"].upper(),
                        "name": coin["name"],
                        "market_cap_rank": coin.get("market_cap_rank"),
                        "score": coin.get("score", 0),
                    }
                )

            return trending

        except HTTPClientError as e:
            logger.warning(f"CoinGecko Trending Fehler: {e}")
            return []


class SentimentAggregator:
    """
    Kombiniert alle Sentiment-Quellen zu einem Score.

    Interpretation:
    - Score > 70: Markt überhitzt, vorsichtig sein
    - Score 40-70: Neutral, normale Bedingungen
    - Score < 40: Fear im Markt, potenzielle Kaufgelegenheit
    """

    def __init__(self):
        self.fear_greed = FearGreedIndex()
        self.coingecko = CoinGeckoSentiment()

    def get_market_sentiment(self) -> dict:
        """Gesamtmarkt-Sentiment"""
        fg = self.fear_greed.get_current()
        trending = self.coingecko.get_trending()

        # Fear & Greed invertieren für "Opportunity Score"
        # Bei Fear = hoher Opportunity Score
        opportunity_score = 100 - fg["value"]

        if fg["value"] < 25:
            signal = "STRONG_BUY"
            reasoning = f"Extreme Fear ({fg['value']}): Historisch gute Kaufgelegenheit"
        elif fg["value"] < 40:
            signal = "BUY"
            reasoning = f"Fear ({fg['value']}): Markt pessimistisch, Chance nutzen"
        elif fg["value"] > 75:
            signal = "SELL"
            reasoning = f"Extreme Greed ({fg['value']}): Markt überhitzt, Gewinne mitnehmen"
        elif fg["value"] > 60:
            signal = "HOLD"
            reasoning = f"Greed ({fg['value']}): Vorsichtig, keine neuen Positionen"
        else:
            signal = "NEUTRAL"
            reasoning = f"Neutral ({fg['value']}): Normale Marktbedingungen"

        return {
            "timestamp": datetime.now(),
            "fear_greed": fg,
            "opportunity_score": opportunity_score,
            "signal": signal,
            "reasoning": reasoning,
            "trending_coins": trending[:5],
        }

    def get_coin_sentiment(self, symbol: str) -> SentimentScore | None:
        """Sentiment für einen spezifischen Coin"""
        fg = self.fear_greed.get_current()
        coin_data = self.coingecko.get_coin_data(symbol)

        if not coin_data:
            return None

        # Normalisiere CoinGecko Scores (0-100)
        social_score = min(
            100, (coin_data.get("community_score", 0) + coin_data.get("sentiment_up", 50)) / 2
        )

        # Reddit Aktivität normalisieren (sehr grob)
        reddit_raw = coin_data.get("reddit_active_48h", 0)
        reddit_score = min(100, reddit_raw / 100)  # Annahme: 10000 = sehr aktiv

        # Gewichteter Gesamtscore
        overall = (
            fg["value"] * 0.4  # Fear & Greed hat großen Einfluss
            + social_score * 0.3  # CoinGecko Social
            + coin_data.get("sentiment_up", 50) * 0.3  # Direktes Sentiment
        )

        # Signal bestimmen
        if overall > 70 and fg["value"] > 60:
            signal = "BEARISH"
            reasoning = (
                f"Überhitzt: Fear&Greed={fg['value']}, "
                f"Coin Sentiment={coin_data.get('sentiment_up', 0):.0f}% positiv - "
                f"Möglicherweise überkauft"
            )
        elif overall < 40 and fg["value"] < 40:
            signal = "BULLISH"
            reasoning = (
                f"Unterbewertet: Fear&Greed={fg['value']}, "
                f"aber Community aktiv ({coin_data.get('reddit_active_48h', 0)} Reddit User) - "
                f"Kaufgelegenheit"
            )
        else:
            signal = "NEUTRAL"
            reasoning = f"Neutral: Fear&Greed={fg['value']}, Social Score={social_score:.0f}"

        return SentimentScore(
            timestamp=datetime.now(),
            symbol=symbol,
            fear_greed=fg["value"],
            social_score=social_score,
            reddit_activity=reddit_score,
            google_trend=0,  # TODO: Google Trends integrieren
            overall_score=overall,
            signal=signal,
            reasoning=reasoning,
        )


def print_sentiment_report():
    """Gibt einen Sentiment-Report aus"""
    agg = SentimentAggregator()

    logger.info("=" * 60)
    logger.info("MARKT SENTIMENT REPORT")
    logger.info("=" * 60)

    market = agg.get_market_sentiment()
    logger.info(f"FEAR & GREED INDEX: {market['fear_greed']['value']}")
    logger.info(f"   Klassifikation: {market['fear_greed']['classification']}")
    logger.info(f"   Signal: {market['signal']}")
    logger.info(f"   → {market['reasoning']}")

    logger.info("TRENDING COINS:")
    for i, coin in enumerate(market["trending_coins"], 1):
        logger.info(f"   {i}. {coin['symbol']} ({coin['name']})")

    logger.info("-" * 60)
    logger.info("COIN-SPEZIFISCHES SENTIMENT")
    logger.info("-" * 60)

    for symbol in ["BTC", "ETH", "SOL", "ARB"]:
        sentiment = agg.get_coin_sentiment(symbol)
        if sentiment:
            logger.info(f"{symbol}:")
            logger.info(f"   Score: {sentiment.overall_score:.1f}/100")
            logger.info(f"   Signal: {sentiment.signal}")
            logger.info(f"   → {sentiment.reasoning}")
        time.sleep(1)  # Rate limiting

    logger.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print_sentiment_report()
