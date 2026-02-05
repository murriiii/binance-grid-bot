"""
Tests für src/core/config.py
"""


class TestAPIConfig:
    """Tests für APIConfig"""

    def test_default_values(self, reset_singletons):
        """Testet Standard-Werte"""
        from src.core.config import APIConfig

        config = APIConfig()

        assert config.timeout_default == 10
        assert config.timeout_deepseek == 30
        assert config.timeout_binance == 10
        assert config.max_retries == 3
        assert config.binance_requests_per_minute == 1000

    def test_api_urls(self, reset_singletons):
        """Testet API URLs"""
        from src.core.config import APIConfig

        config = APIConfig()

        assert "alternative.me" in config.fear_greed_url
        assert "deepseek.com" in config.deepseek_url
        assert "coingecko.com" in config.coingecko_url
        assert "blockchain.info" in config.blockchain_url
        assert "tradingview.com" in config.economic_calendar_url

    def test_from_env(self, reset_singletons, monkeypatch):
        """Testet Laden aus Environment"""
        from src.core.config import APIConfig

        monkeypatch.setenv("API_TIMEOUT_DEFAULT", "20")
        monkeypatch.setenv("API_MAX_RETRIES", "5")

        config = APIConfig.from_env()

        assert config.timeout_default == 20
        assert config.max_retries == 5


class TestBotConfig:
    """Tests für BotConfig"""

    def test_default_values(self, reset_singletons):
        """Testet Standard-Werte"""
        from src.core.config import BotConfig

        config = BotConfig()

        assert config.symbol == "BTCUSDT"
        assert config.investment == 10.0
        assert config.num_grids == 3
        assert config.testnet is True
        assert config.max_consecutive_errors == 5

    def test_from_env(self, reset_singletons):
        """Testet Laden aus Environment"""
        from src.core.config import BotConfig

        config = BotConfig.from_env()

        assert config.symbol == "BTCUSDT"
        assert config.investment == 100.0  # From mock_env_vars
        assert config.num_grids == 5

    def test_validation_valid_config(self, reset_singletons):
        """Testet Validierung mit gültiger Config"""
        from src.core.config import BotConfig

        config = BotConfig(
            symbol="BTCUSDT",
            investment=100.0,
            num_grids=5,
            grid_range_percent=5.0,
        )

        is_valid, errors = config.validate()

        assert is_valid is True
        assert len(errors) == 0

    def test_validation_invalid_symbol(self, reset_singletons):
        """Testet Validierung mit ungültigem Symbol"""
        from src.core.config import BotConfig

        config = BotConfig(symbol="BTCEUR")  # Nicht USDT

        is_valid, errors = config.validate()

        assert is_valid is False
        assert any("USDT" in e for e in errors)

    def test_validation_investment_too_low(self, reset_singletons):
        """Testet Validierung mit zu geringem Investment"""
        from src.core.config import BotConfig

        config = BotConfig(investment=1.0)  # Unter Minimum

        is_valid, errors = config.validate()

        assert is_valid is False
        assert any("zu klein" in e for e in errors)

    def test_validation_too_many_grids(self, reset_singletons):
        """Testet Validierung mit zu vielen Grids"""
        from src.core.config import BotConfig

        config = BotConfig(num_grids=100)  # Über Maximum

        is_valid, errors = config.validate()

        assert is_valid is False
        assert any("Maximum" in e for e in errors)

    def test_to_dict(self, reset_singletons):
        """Testet Konvertierung zu Dictionary"""
        from src.core.config import BotConfig

        config = BotConfig(symbol="ETHUSDT", investment=500.0)
        result = config.to_dict()

        assert result["symbol"] == "ETHUSDT"
        assert result["investment"] == 500.0
        assert "testnet" in result


class TestWhaleConfig:
    """Tests für WhaleConfig"""

    def test_default_thresholds(self, reset_singletons):
        """Testet Standard-Schwellwerte"""
        from src.core.config import WhaleConfig

        config = WhaleConfig()

        assert config.btc_threshold == 10_000_000
        assert config.eth_threshold == 5_000_000
        assert config.default_threshold == 1_000_000
        assert config.min_btc_amount == 100
        assert config.alert_threshold == 50_000_000


class TestSentimentConfig:
    """Tests für SentimentConfig"""

    def test_fear_greed_thresholds(self, reset_singletons):
        """Testet Fear & Greed Schwellwerte"""
        from src.core.config import SentimentConfig

        config = SentimentConfig()

        assert config.extreme_fear_threshold == 20
        assert config.fear_threshold == 40
        assert config.greed_threshold == 60
        assert config.extreme_greed_threshold == 80

    def test_classification(self, reset_singletons):
        """Testet Fear & Greed Klassifizierung"""
        from src.core.config import SentimentConfig

        assert SentimentConfig.get_classification(10) == "Extreme Fear"
        assert SentimentConfig.get_classification(30) == "Fear"
        assert SentimentConfig.get_classification(50) == "Neutral"
        assert SentimentConfig.get_classification(70) == "Greed"
        assert SentimentConfig.get_classification(90) == "Extreme Greed"


class TestDatabaseConfig:
    """Tests für DatabaseConfig"""

    def test_default_values(self, reset_singletons):
        """Testet Standard-Werte"""
        from src.core.config import DatabaseConfig

        config = DatabaseConfig()

        assert config.host == "localhost"
        assert config.database == "trading_bot"
        assert config.user == "trading"

    def test_connection_string(self, reset_singletons):
        """Testet Connection String Generation"""
        from src.core.config import DatabaseConfig

        config = DatabaseConfig(
            host="db.example.com",
            port=5432,
            database="mydb",
            user="myuser",
            password="mypass",
        )

        conn_str = config.get_connection_string()

        assert "postgresql://" in conn_str
        assert "myuser:mypass" in conn_str
        assert "db.example.com:5432" in conn_str
        assert "mydb" in conn_str


class TestAppConfig:
    """Tests für AppConfig (Hauptkonfiguration)"""

    def test_singleton_pattern(self, reset_singletons):
        """Testet Singleton-Pattern"""
        from src.core.config import get_config

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_contains_all_subconfigs(self, reset_singletons):
        """Testet dass alle Sub-Configs enthalten sind"""
        from src.core.config import get_config

        config = get_config()

        assert hasattr(config, "bot")
        assert hasattr(config, "api")
        assert hasattr(config, "whale")
        assert hasattr(config, "sentiment")
        assert hasattr(config, "scheduler")
        assert hasattr(config, "database")

    def test_from_env_loads_all(self, reset_singletons):
        """Testet dass from_env alle Configs lädt"""
        from src.core.config import AppConfig

        config = AppConfig.from_env()

        # Bot config sollte aus env geladen sein
        assert config.bot.symbol == "BTCUSDT"
        assert config.bot.investment == 100.0


class TestEnvironmentValidation:
    """Tests für Environment-Validierung"""

    def test_validate_with_all_vars(self, reset_singletons):
        """Testet Validierung mit allen Variablen"""
        from src.core.config import validate_environment

        is_valid, warnings = validate_environment()

        # Sollte valid sein da mock_env_vars alle setzt
        assert is_valid is True

    def test_validate_missing_api_key(self, reset_singletons, monkeypatch):
        """Testet Warnung bei fehlendem API Key"""
        from src.core.config import validate_environment

        monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)

        is_valid, warnings = validate_environment()

        assert any("API_KEY" in w for w in warnings)

    def test_validate_missing_telegram(self, reset_singletons, monkeypatch):
        """Testet Warnung bei fehlendem Telegram Token"""
        from src.core.config import validate_environment

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        is_valid, warnings = validate_environment()

        assert any("TELEGRAM" in w for w in warnings)
