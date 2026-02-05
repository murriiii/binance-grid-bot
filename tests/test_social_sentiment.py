"""
Tests für SocialSentimentProvider
"""

from datetime import datetime


class TestSocialMetrics:
    """Tests für SocialMetrics Dataclass"""

    def test_social_metrics_creation(self):
        """Test SocialMetrics Erstellung"""
        from src.data.social_sentiment import SocialMetrics

        metrics = SocialMetrics(
            timestamp=datetime.now(),
            symbol="BTC",
            galaxy_score=72.0,
            alt_rank=5,
            social_volume=150000,
            social_engagement=75000,
            social_contributors=5000,
            social_dominance=25.5,
            reddit_mentions=800,
            reddit_sentiment=0.45,
            reddit_posts_24h=120,
            reddit_comments_24h=3500,
            twitter_mentions=3500,
            twitter_sentiment=0.55,
            composite_sentiment=0.5,
            sentiment_trend="RISING",
        )

        assert metrics.symbol == "BTC"
        assert metrics.galaxy_score == 72.0
        assert metrics.composite_sentiment == 0.5
        assert metrics.sentiment_trend == "RISING"


class TestSocialSentimentProvider:
    """Tests für Social Sentiment Provider"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.data.social_sentiment import SocialSentimentProvider

        p1 = SocialSentimentProvider.get_instance()
        p2 = SocialSentimentProvider.get_instance()

        assert p1 is p2

    def test_provider_initialization(self, reset_new_singletons):
        """Test Provider Initialisierung"""
        from src.data.social_sentiment import SocialSentimentProvider

        provider = SocialSentimentProvider()

        # Sollte ohne Fehler initialisieren
        assert provider is not None
