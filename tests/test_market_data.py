"""
Tests für src/data/market_data.py
"""

from datetime import datetime
from unittest.mock import patch


class TestMarketDataProvider:
    """Tests für MarketDataProvider"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Testet Singleton-Pattern"""
        from src.data.market_data import MarketDataProvider, get_market_data

        provider1 = get_market_data()
        provider2 = get_market_data()
        provider3 = MarketDataProvider.get_instance()

        assert provider1 is provider2
        assert provider2 is provider3

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_fear_greed(self, mock_get, reset_new_singletons, sample_fear_greed_response):
        """Testet Fear & Greed Abruf"""
        from src.data.market_data import get_market_data

        mock_get.return_value = sample_fear_greed_response

        provider = get_market_data()
        result = provider.get_fear_greed()

        assert result.value == 45
        assert result.classification in ["Fear", "Neutral", "Greed"]
        assert isinstance(result.timestamp, datetime)

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_price(self, mock_get, reset_new_singletons, sample_btc_price_response):
        """Testet Preis-Abruf"""
        from src.data.market_data import get_market_data

        mock_get.return_value = sample_btc_price_response

        provider = get_market_data()
        price = provider.get_price("BTCUSDT")

        assert price == 42500.50

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_price_caching(self, mock_get, reset_new_singletons, sample_btc_price_response):
        """Testet Preis-Caching"""
        from src.data.market_data import get_market_data

        mock_get.return_value = sample_btc_price_response

        provider = get_market_data()
        price1 = provider.get_price("BTCUSDT")
        price2 = provider.get_price("BTCUSDT")

        # Sollte nur einmal API aufgerufen haben (Cache)
        assert mock_get.call_count == 1
        assert price1 == price2

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_24h_ticker(self, mock_get, reset_new_singletons, sample_ticker_24h_response):
        """Testet 24h Ticker Abruf"""
        from src.data.market_data import get_market_data

        mock_get.return_value = sample_ticker_24h_response

        provider = get_market_data()
        ticker = provider.get_24h_ticker("BTCUSDT")

        assert ticker is not None
        assert ticker.symbol == "BTCUSDT"
        assert ticker.price == 42500.50
        assert ticker.change_24h == 2.5

    @patch("src.api.http_client.HTTPClient.get")
    def test_get_trending_coins(self, mock_get, reset_new_singletons, sample_coingecko_trending):
        """Testet Trending Coins"""
        from src.data.market_data import get_market_data

        mock_get.return_value = sample_coingecko_trending

        provider = get_market_data()
        trending = provider.get_trending_coins(limit=3)

        assert len(trending) == 3
        assert trending[0]["symbol"] == "BTC"

    def test_classify_fear_greed(self, reset_new_singletons):
        """Testet Fear & Greed Klassifizierung"""
        from src.data.market_data import get_market_data

        provider = get_market_data()

        assert provider._classify_fear_greed(10) == "Extreme Fear"
        assert provider._classify_fear_greed(30) == "Fear"
        assert provider._classify_fear_greed(50) == "Neutral"
        assert provider._classify_fear_greed(70) == "Greed"
        assert provider._classify_fear_greed(90) == "Extreme Greed"

    def test_clear_cache(self, reset_new_singletons):
        """Testet Cache-Leerung"""
        from src.data.market_data import get_market_data

        provider = get_market_data()

        # Fülle Cache manuell
        provider._price_cache["BTCUSDT"] = (50000.0, datetime.now())

        provider.clear_cache()

        assert len(provider._price_cache) == 0


class TestFearGreedData:
    """Tests für FearGreedData Dataclass"""

    def test_creation(self, reset_new_singletons):
        """Testet Erstellung"""
        from src.data.market_data import FearGreedData

        data = FearGreedData(value=45, classification="Fear", timestamp=datetime.now())

        assert data.value == 45
        assert data.classification == "Fear"


class TestPriceData:
    """Tests für PriceData Dataclass"""

    def test_creation(self, reset_new_singletons):
        """Testet Erstellung"""
        from src.data.market_data import PriceData

        data = PriceData(
            symbol="BTCUSDT",
            price=42500.0,
            change_24h=2.5,
            volume_24h=1500000000.0,
            timestamp=datetime.now(),
        )

        assert data.symbol == "BTCUSDT"
        assert data.price == 42500.0
        assert data.change_24h == 2.5
