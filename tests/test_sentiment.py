"""
Tests für src/data/sentiment.py
"""

from datetime import datetime
from unittest.mock import patch


class TestFearGreedIndex:
    """Tests für FearGreedIndex"""

    def test_initialization(self, reset_singletons):
        """Testet Initialisierung"""
        from src.data.sentiment import FearGreedIndex

        fg = FearGreedIndex()

        assert fg.http is not None
        assert fg.config is not None

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_current_success(self, mock_get, reset_singletons, sample_fear_greed_response):
        """Testet erfolgreichen API-Aufruf"""
        from src.data.sentiment import FearGreedIndex

        mock_get.return_value = sample_fear_greed_response

        fg = FearGreedIndex()
        result = fg.get_current()

        assert result["value"] == 45
        assert result["classification"] == "Fear"
        assert "timestamp" in result

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_current_fallback_on_error(self, mock_get, reset_singletons):
        """Testet Fallback bei API-Fehler"""
        from src.api.http_client import HTTPClientError
        from src.data.sentiment import FearGreedIndex

        mock_get.side_effect = HTTPClientError("API Error")

        fg = FearGreedIndex()
        result = fg.get_current()

        # Sollte Fallback-Werte zurückgeben
        assert result["value"] == 50
        assert result["classification"] == "Neutral"

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_historical(self, mock_get, reset_singletons):
        """Testet historische Daten"""
        from src.data.sentiment import FearGreedIndex

        mock_get.return_value = {
            "data": [
                {
                    "value": "30",
                    "value_classification": "Fear",
                    "timestamp": str(int(datetime.now().timestamp())),
                },
                {
                    "value": "40",
                    "value_classification": "Fear",
                    "timestamp": str(int(datetime.now().timestamp())),
                },
            ]
        }

        fg = FearGreedIndex()
        result = fg.get_historical(days=2)

        assert len(result) == 2
        assert result[0]["value"] == 30
        assert result[1]["value"] == 40


class TestCoinGeckoSentiment:
    """Tests für CoinGeckoSentiment"""

    def test_symbol_mapping(self, reset_singletons):
        """Testet Symbol-zu-ID Mapping"""
        from src.data.sentiment import CoinGeckoSentiment

        cg = CoinGeckoSentiment()

        assert cg.SYMBOL_TO_ID["BTC"] == "bitcoin"
        assert cg.SYMBOL_TO_ID["ETH"] == "ethereum"
        assert cg.SYMBOL_TO_ID["SOL"] == "solana"

    def test_unknown_symbol_returns_none(self, reset_singletons):
        """Testet dass unbekannte Symbole None zurückgeben"""
        from src.data.sentiment import CoinGeckoSentiment

        cg = CoinGeckoSentiment()
        result = cg.get_coin_data("UNKNOWN_COIN")

        assert result is None

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_coin_data_success(self, mock_get, reset_singletons):
        """Testet erfolgreichen Coin-Daten-Abruf"""
        from src.data.sentiment import CoinGeckoSentiment

        mock_get.return_value = {
            "name": "Bitcoin",
            "sentiment_votes_up_percentage": 75,
            "community_data": {
                "twitter_followers": 5000000,
                "reddit_subscribers": 4000000,
                "reddit_accounts_active_48h": 10000,
            },
            "developer_data": {
                "stars": 70000,
                "commit_count_4_weeks": 100,
            },
            "coingecko_score": 85,
            "community_score": 80,
            "developer_score": 90,
        }

        cg = CoinGeckoSentiment()
        result = cg.get_coin_data("BTC")

        assert result is not None
        assert result["symbol"] == "BTC"
        assert result["name"] == "Bitcoin"
        assert result["sentiment_up"] == 75
        assert result["twitter_followers"] == 5000000

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_trending(self, mock_get, reset_singletons, sample_coingecko_trending):
        """Testet Trending Coins"""
        from src.data.sentiment import CoinGeckoSentiment

        mock_get.return_value = sample_coingecko_trending

        cg = CoinGeckoSentiment()
        result = cg.get_trending()

        assert len(result) == 3
        assert result[0]["symbol"] == "BTC"
        assert result[1]["symbol"] == "ETH"


class TestSentimentAggregator:
    """Tests für SentimentAggregator"""

    @patch("src.data.sentiment.FearGreedIndex.get_current")
    @patch("src.data.sentiment.CoinGeckoSentiment.get_trending")
    def test_get_market_sentiment(self, mock_trending, mock_fg, reset_singletons):
        """Testet Markt-Sentiment-Aggregation"""
        from src.data.sentiment import SentimentAggregator

        mock_fg.return_value = {"value": 25, "classification": "Fear", "timestamp": datetime.now()}
        mock_trending.return_value = [{"symbol": "BTC", "name": "Bitcoin"}]

        agg = SentimentAggregator()
        result = agg.get_market_sentiment()

        assert result["fear_greed"]["value"] == 25
        assert result["signal"] == "BUY"  # Fear < 40 → BUY
        assert "reasoning" in result

    @patch("src.data.sentiment.FearGreedIndex.get_current")
    @patch("src.data.sentiment.CoinGeckoSentiment.get_trending")
    def test_extreme_fear_strong_buy(self, mock_trending, mock_fg, reset_singletons):
        """Testet STRONG_BUY bei Extreme Fear"""
        from src.data.sentiment import SentimentAggregator

        mock_fg.return_value = {
            "value": 15,
            "classification": "Extreme Fear",
            "timestamp": datetime.now(),
        }
        mock_trending.return_value = []

        agg = SentimentAggregator()
        result = agg.get_market_sentiment()

        assert result["signal"] == "STRONG_BUY"

    @patch("src.data.sentiment.FearGreedIndex.get_current")
    @patch("src.data.sentiment.CoinGeckoSentiment.get_trending")
    def test_extreme_greed_sell(self, mock_trending, mock_fg, reset_singletons):
        """Testet SELL bei Extreme Greed"""
        from src.data.sentiment import SentimentAggregator

        mock_fg.return_value = {
            "value": 85,
            "classification": "Extreme Greed",
            "timestamp": datetime.now(),
        }
        mock_trending.return_value = []

        agg = SentimentAggregator()
        result = agg.get_market_sentiment()

        assert result["signal"] == "SELL"

    @patch("src.data.sentiment.FearGreedIndex.get_current")
    @patch("src.data.sentiment.CoinGeckoSentiment.get_coin_data")
    def test_get_coin_sentiment(self, mock_coin, mock_fg, reset_singletons):
        """Testet Coin-spezifisches Sentiment"""
        from src.data.sentiment import SentimentAggregator

        mock_fg.return_value = {
            "value": 50,
            "classification": "Neutral",
            "timestamp": datetime.now(),
        }
        mock_coin.return_value = {
            "symbol": "BTC",
            "name": "Bitcoin",
            "sentiment_up": 60,
            "community_score": 70,
            "reddit_active_48h": 5000,
        }

        agg = SentimentAggregator()
        result = agg.get_coin_sentiment("BTC")

        assert result is not None
        assert result.symbol == "BTC"
        assert result.fear_greed == 50
        assert result.signal in ["BULLISH", "BEARISH", "NEUTRAL"]

    @patch("src.data.sentiment.FearGreedIndex.get_current")
    @patch("src.data.sentiment.CoinGeckoSentiment.get_coin_data")
    def test_coin_sentiment_unknown_returns_none(self, mock_coin, mock_fg, reset_singletons):
        """Testet dass unbekannte Coins None zurückgeben"""
        from src.data.sentiment import SentimentAggregator

        mock_fg.return_value = {
            "value": 50,
            "classification": "Neutral",
            "timestamp": datetime.now(),
        }
        mock_coin.return_value = None

        agg = SentimentAggregator()
        result = agg.get_coin_sentiment("UNKNOWN")

        assert result is None


class TestSentimentScore:
    """Tests für SentimentScore Dataclass"""

    def test_sentiment_score_creation(self, reset_singletons):
        """Testet SentimentScore Erstellung"""
        from src.data.sentiment import SentimentScore

        score = SentimentScore(
            timestamp=datetime.now(),
            symbol="BTC",
            fear_greed=45,
            social_score=65.0,
            reddit_activity=50.0,
            google_trend=0.0,
            overall_score=55.0,
            signal="NEUTRAL",
            reasoning="Test reasoning",
        )

        assert score.symbol == "BTC"
        assert score.fear_greed == 45
        assert score.signal == "NEUTRAL"
