"""
Social Sentiment Provider - Aggregiert Sentiment aus Social Media

Datenquellen:
- LunarCrush: Galaxy Score, Social Volume, Engagement (API)
- Reddit: r/cryptocurrency, r/bitcoin Sentiment (PRAW)
- Twitter/X: Mentions und Sentiment (optional)

Speichert alles in social_sentiment Tabelle für Analyse.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

try:
    import praw

    REDDIT_AVAILABLE = True
except ImportError:
    REDDIT_AVAILABLE = False
    logger.debug("praw nicht installiert - pip install praw")

# HTTP Client aus dem Projekt
try:
    from src.api.http_client import get_http_client
except ImportError:
    get_http_client = None


@dataclass
class SocialMetrics:
    """Aggregierte Social Metriken für ein Symbol"""

    timestamp: datetime
    symbol: str

    # LunarCrush Metriken
    galaxy_score: float | None  # 0-100, Gesamtbewertung
    alt_rank: int | None  # Ranking unter Altcoins
    social_volume: int | None  # Anzahl Social Posts
    social_engagement: int | None  # Likes, Shares, Comments
    social_contributors: int | None  # Unique Contributors
    social_dominance: float | None  # % des gesamten Crypto Social Volume

    # Reddit Metriken
    reddit_mentions: int | None
    reddit_sentiment: float | None  # -1 bis +1
    reddit_posts_24h: int | None
    reddit_comments_24h: int | None

    # Twitter Metriken (optional)
    twitter_mentions: int | None
    twitter_sentiment: float | None

    # Aggregiert
    composite_sentiment: float | None  # -1 bis +1
    sentiment_trend: str | None  # RISING, FALLING, STABLE


class SocialSentimentProvider(SingletonMixin):
    """
    Aggregiert Social Sentiment aus mehreren Quellen.

    Features:
    1. LunarCrush API für aggregierte Crypto-Social-Daten
    2. Reddit PRAW für direktes Subreddit-Sentiment
    3. Speichert alles in DB für historische Analyse
    4. Berechnet Composite Score aus allen Quellen
    """

    LUNARCRUSH_BASE_URL = "https://lunarcrush.com/api4/public"
    REDDIT_SUBREDDITS = ["cryptocurrency", "bitcoin", "ethtrader", "CryptoMarkets"]

    def __init__(self):
        self.conn = None
        self.http = get_http_client() if get_http_client else None
        self.reddit = None
        self.lunarcrush_key = os.getenv("LUNARCRUSH_API_KEY")

        self._connect_db()
        self._init_reddit()

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("SocialSentimentProvider: DB verbunden")
        except Exception as e:
            logger.error(f"SocialSentimentProvider: DB Fehler: {e}")

    def _init_reddit(self):
        """Initialisiere Reddit PRAW Client"""
        if not REDDIT_AVAILABLE:
            return

        try:
            client_id = os.getenv("REDDIT_CLIENT_ID")
            client_secret = os.getenv("REDDIT_CLIENT_SECRET")
            user_agent = os.getenv("REDDIT_USER_AGENT", "TradingBot/1.0")

            if client_id and client_secret:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent,
                )
                logger.info("SocialSentimentProvider: Reddit verbunden")
        except Exception as e:
            logger.error(f"SocialSentimentProvider: Reddit Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # LUNARCRUSH API
    # ═══════════════════════════════════════════════════════════════

    def get_lunarcrush_metrics(self, symbol: str) -> dict[str, Any] | None:
        """
        Hole Metriken von LunarCrush API.

        LunarCrush aggregiert:
        - Twitter, Reddit, YouTube, News
        - Galaxy Score (0-100)
        - Social Volume und Engagement
        - Alt Rank

        HINWEIS: LunarCrush hat kein kostenloses Tier mehr ($90/Monat minimum).
        Diese Methode gibt None zurück wenn kein API Key konfiguriert ist.
        """
        if not self.http:
            logger.debug("LunarCrush: HTTP Client nicht verfügbar")
            return None

        if not self.lunarcrush_key:
            logger.debug("LunarCrush: Kein API Key konfiguriert (kostenpflichtig)")
            return None

        try:
            url = f"{self.LUNARCRUSH_BASE_URL}/coins/{symbol.lower()}/v1"
            headers = {"Authorization": f"Bearer {self.lunarcrush_key}"}

            response = self.http.get(url, headers=headers, timeout=10)

            if response and "data" in response:
                data = response["data"]
                return {
                    "galaxy_score": data.get("galaxy_score"),
                    "alt_rank": data.get("alt_rank"),
                    "social_volume": data.get("social_volume"),
                    "social_engagement": data.get("social_engagement"),
                    "social_contributors": data.get("social_contributors"),
                    "social_dominance": data.get("social_dominance"),
                    "sentiment": data.get("sentiment"),  # 0-5 scale
                    "categories": data.get("categories", []),
                }

            return None

        except Exception as e:
            logger.error(f"LunarCrush API Fehler für {symbol}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # REDDIT API
    # ═══════════════════════════════════════════════════════════════

    def get_reddit_sentiment(
        self,
        symbol: str,
        hours: int = 24,
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """
        Analysiere Reddit Sentiment für ein Symbol.

        Durchsucht relevante Subreddits nach Mentions
        und analysiert Sentiment basierend auf:
        - Upvote Ratio
        - Comment Sentiment (einfache Keyword-Analyse)
        - Post Frequency

        Benötigt REDDIT_CLIENT_ID und REDDIT_CLIENT_SECRET in .env
        """
        if not self.reddit:
            logger.debug("Reddit: PRAW nicht konfiguriert (REDDIT_CLIENT_ID/SECRET fehlt)")
            return None

        try:
            mentions = 0
            total_score = 0
            total_comments = 0
            sentiment_scores = []

            # Symbol-Varianten für Suche
            search_terms = self._get_search_terms(symbol)

            for subreddit_name in self.REDDIT_SUBREDDITS:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)

                    # Suche nach Symbol
                    for term in search_terms:
                        for submission in subreddit.search(
                            term,
                            time_filter="day",
                            limit=limit // len(self.REDDIT_SUBREDDITS),
                        ):
                            mentions += 1
                            total_score += submission.score
                            total_comments += submission.num_comments

                            # Einfaches Sentiment aus Upvote Ratio
                            sentiment = (submission.upvote_ratio - 0.5) * 2
                            sentiment_scores.append(sentiment)

                except Exception as e:
                    logger.debug(f"Reddit Subreddit {subreddit_name} Fehler: {e}")
                    continue

            # Keine Daten gefunden
            if not sentiment_scores:
                logger.debug(f"Reddit: Keine Posts für {symbol} gefunden")
                return None

            # Aggregiere Sentiment
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)

            return {
                "mentions": mentions,
                "sentiment": avg_sentiment,
                "total_score": total_score,
                "total_comments": total_comments,
                "posts_analyzed": len(sentiment_scores),
            }

        except Exception as e:
            logger.error(f"Reddit API Fehler für {symbol}: {e}")
            return None

    def _get_search_terms(self, symbol: str) -> list[str]:
        """Generiere Suchbegriffe für ein Symbol"""
        symbol_map = {
            "BTC": ["Bitcoin", "BTC", "$BTC"],
            "ETH": ["Ethereum", "ETH", "$ETH"],
            "SOL": ["Solana", "SOL", "$SOL"],
            "AVAX": ["Avalanche", "AVAX", "$AVAX"],
            "LINK": ["Chainlink", "LINK", "$LINK"],
            "DOT": ["Polkadot", "DOT", "$DOT"],
        }
        return symbol_map.get(symbol.upper(), [symbol, f"${symbol}"])

    # ═══════════════════════════════════════════════════════════════
    # SENTIMENT ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def analyze_text_sentiment(self, text: str) -> float:
        """
        Einfache Sentiment-Analyse basierend auf Keywords.

        Returns: -1 (bearish) bis +1 (bullish)
        """
        bullish_keywords = [
            "moon",
            "bullish",
            "buy",
            "pump",
            "gains",
            "profit",
            "hodl",
            "long",
            "breakout",
            "undervalued",
            "gem",
            "rocket",
            "ath",
            "green",
            "accumulate",
            "dip",
        ]
        bearish_keywords = [
            "dump",
            "bearish",
            "sell",
            "crash",
            "loss",
            "scam",
            "short",
            "overvalued",
            "dead",
            "rug",
            "ponzi",
            "red",
            "fear",
            "panic",
            "drop",
            "tank",
        ]

        text_lower = text.lower()

        bullish_count = sum(1 for kw in bullish_keywords if kw in text_lower)
        bearish_count = sum(1 for kw in bearish_keywords if kw in text_lower)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        return (bullish_count - bearish_count) / total

    # ═══════════════════════════════════════════════════════════════
    # AGGREGATION
    # ═══════════════════════════════════════════════════════════════

    def get_aggregated_sentiment(self, symbol: str) -> SocialMetrics:
        """
        Hole und aggregiere Sentiment aus allen Quellen.

        Kombiniert:
        - LunarCrush Galaxy Score (40%)
        - LunarCrush Sentiment (20%)
        - Reddit Sentiment (30%)
        - Reddit Activity (10%)
        """
        timestamp = datetime.now()

        # Hole Daten aus allen Quellen
        lunarcrush = self.get_lunarcrush_metrics(symbol)
        reddit = self.get_reddit_sentiment(symbol)

        # LunarCrush Metriken
        galaxy_score = lunarcrush.get("galaxy_score") if lunarcrush else None
        social_volume = lunarcrush.get("social_volume") if lunarcrush else None
        social_engagement = lunarcrush.get("social_engagement") if lunarcrush else None
        lc_sentiment = lunarcrush.get("sentiment") if lunarcrush else None  # 0-5

        # Reddit Metriken
        reddit_mentions = reddit.get("mentions") if reddit else None
        reddit_sentiment = reddit.get("sentiment") if reddit else None  # -1 to +1

        # Composite Sentiment berechnen
        composite = self._calculate_composite_sentiment(
            galaxy_score=galaxy_score,
            lc_sentiment=lc_sentiment,
            reddit_sentiment=reddit_sentiment,
            reddit_mentions=reddit_mentions,
        )

        # Trend bestimmen (würde historische Daten benötigen)
        trend = self._determine_sentiment_trend(symbol, composite)

        return SocialMetrics(
            timestamp=timestamp,
            symbol=symbol,
            galaxy_score=galaxy_score,
            alt_rank=lunarcrush.get("alt_rank") if lunarcrush else None,
            social_volume=social_volume,
            social_engagement=social_engagement,
            social_contributors=lunarcrush.get("social_contributors") if lunarcrush else None,
            social_dominance=lunarcrush.get("social_dominance") if lunarcrush else None,
            reddit_mentions=reddit_mentions,
            reddit_sentiment=reddit_sentiment,
            reddit_posts_24h=reddit.get("posts_analyzed") if reddit else None,
            reddit_comments_24h=reddit.get("total_comments") if reddit else None,
            twitter_mentions=None,  # Optional, nicht implementiert
            twitter_sentiment=None,
            composite_sentiment=composite,
            sentiment_trend=trend,
        )

    # C4: Source-availability dampening factors
    _SOURCE_DAMPENING = {0: 0.0, 1: 0.5, 2: 0.8, 3: 1.0}

    def _calculate_composite_sentiment(
        self,
        galaxy_score: float | None,
        lc_sentiment: float | None,
        reddit_sentiment: float | None,
        reddit_mentions: int | None,
    ) -> float | None:
        """
        Berechne gewichteten Composite Sentiment Score.

        C4 improvements:
        - Source-availability dampening: fewer sources → lower confidence
        - Volume-threshold dampening: low reddit mentions → reduced weight
        - Divergence detection: opposing sources → dampened composite

        Gewichte:
        - Galaxy Score: 40% (normalisiert auf -1 bis +1)
        - LunarCrush Sentiment: 20% (normalisiert)
        - Reddit Sentiment: 30%
        - Reddit Activity: 10% (Log-normalisiert)
        """
        components = []
        weights = []
        source_count = 0

        # Galaxy Score (0-100 → -1 bis +1)
        if galaxy_score is not None:
            normalized_gs = (galaxy_score - 50) / 50
            components.append(normalized_gs)
            weights.append(0.40)
            source_count += 1

        # LunarCrush Sentiment (0-5 → -1 bis +1)
        lc_normalized = None
        if lc_sentiment is not None:
            lc_normalized = (lc_sentiment - 2.5) / 2.5
            components.append(lc_normalized)
            weights.append(0.20)
            source_count += 1

        # Reddit Sentiment (bereits -1 bis +1)
        reddit_weight = 0.30
        if reddit_sentiment is not None:
            # C4: Volume-threshold dampening for reddit
            if reddit_mentions is not None:
                if reddit_mentions < 5:
                    reddit_weight *= 0.3
                elif reddit_mentions < 20:
                    reddit_weight *= 0.7

            components.append(reddit_sentiment)
            weights.append(reddit_weight)
            source_count += 1

        # Reddit Activity (Log-normalisiert)
        if reddit_mentions is not None and reddit_mentions > 0:
            import math

            # Mehr Mentions = mehr Interesse (neutral bis leicht positiv)
            activity_score = min(1.0, math.log10(reddit_mentions) / 3)
            components.append(activity_score * 0.5)  # Dämpfen
            weights.append(0.10)

        if not components:
            return None

        # Gewichteter Durchschnitt
        total_weight = sum(weights)
        composite = sum(c * w for c, w in zip(components, weights)) / total_weight

        # C4: Source-availability dampening
        dampening = self._SOURCE_DAMPENING.get(source_count, 1.0)
        composite *= dampening

        # C4: Divergence detection — opposing LunarCrush and Reddit
        if (
            lc_normalized is not None
            and reddit_sentiment is not None
            and (
                (lc_normalized > 0.2 and reddit_sentiment < -0.2)
                or (lc_normalized < -0.2 and reddit_sentiment > 0.2)
            )
        ):
            composite *= 0.8

        return max(-1.0, min(1.0, composite))

    def _determine_sentiment_trend(self, symbol: str, current: float | None) -> str | None:
        """Bestimme Sentiment-Trend basierend auf historischen Daten"""
        if current is None or not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT AVG(composite_sentiment) as avg_sentiment
                    FROM social_sentiment
                    WHERE symbol = %s
                      AND timestamp > NOW() - INTERVAL '24 hours'
                """,
                    (symbol,),
                )
                row = cur.fetchone()

                if row and row["avg_sentiment"] is not None:
                    prev_avg = float(row["avg_sentiment"])
                    diff = current - prev_avg

                    if diff > 0.1:
                        return "RISING"
                    elif diff < -0.1:
                        return "FALLING"
                    else:
                        return "STABLE"

        except Exception as e:
            logger.debug(f"Trend-Bestimmung Fehler: {e}")

        return None

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_metrics(self, metrics: SocialMetrics):
        """Speichere Social Metriken in der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO social_sentiment (
                        timestamp, symbol,
                        galaxy_score, social_volume, social_engagement,
                        reddit_mentions, reddit_sentiment,
                        twitter_mentions, twitter_sentiment,
                        composite_sentiment
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        metrics.timestamp,
                        metrics.symbol,
                        metrics.galaxy_score,
                        metrics.social_volume,
                        metrics.social_engagement,
                        metrics.reddit_mentions,
                        metrics.reddit_sentiment,
                        metrics.twitter_mentions,
                        metrics.twitter_sentiment,
                        metrics.composite_sentiment,
                    ),
                )
                self.conn.commit()
                logger.debug(f"Social Metrics für {metrics.symbol} gespeichert")

        except Exception as e:
            logger.error(f"Social Metrics Speicherfehler: {e}")
            self.conn.rollback()

    def get_latest_metrics(self, symbol: str) -> SocialMetrics | None:
        """Hole neueste gespeicherte Metriken"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM social_sentiment
                    WHERE symbol = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    (symbol,),
                )
                row = cur.fetchone()

                if row:
                    return SocialMetrics(
                        timestamp=row["timestamp"],
                        symbol=row["symbol"],
                        galaxy_score=float(row["galaxy_score"]) if row["galaxy_score"] else None,
                        alt_rank=None,
                        social_volume=row["social_volume"],
                        social_engagement=row["social_engagement"],
                        social_contributors=None,
                        social_dominance=None,
                        reddit_mentions=row["reddit_mentions"],
                        reddit_sentiment=float(row["reddit_sentiment"])
                        if row["reddit_sentiment"]
                        else None,
                        reddit_posts_24h=None,
                        reddit_comments_24h=None,
                        twitter_mentions=row["twitter_mentions"],
                        twitter_sentiment=float(row["twitter_sentiment"])
                        if row["twitter_sentiment"]
                        else None,
                        composite_sentiment=float(row["composite_sentiment"])
                        if row["composite_sentiment"]
                        else None,
                        sentiment_trend=None,
                    )

        except Exception as e:
            logger.error(f"Social Metrics Abruf Fehler: {e}")

        return None

    def fetch_and_store(self, symbols: list[str] | None = None):
        """Hole und speichere Metriken für mehrere Symbole"""
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "AVAX", "LINK"]

        for symbol in symbols:
            try:
                metrics = self.get_aggregated_sentiment(symbol)
                self.store_metrics(metrics)
                logger.info(f"Social Sentiment für {symbol}: {metrics.composite_sentiment:.2f}")
            except Exception as e:
                logger.error(f"Social Sentiment Fehler für {symbol}: {e}")

    def close(self):
        """Schließe Verbindungen"""
        if self.conn:
            self.conn.close()
            self.conn = None
