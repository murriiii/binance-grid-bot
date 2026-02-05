"""
Tests für WatchlistManager.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.data.watchlist import WatchlistCoin, WatchlistManager


@pytest.fixture
def mock_db_connection():
    """Mock für Datenbankverbindung."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock()
    return conn, cursor


@pytest.fixture
def sample_coin():
    """Sample WatchlistCoin für Tests."""
    return WatchlistCoin(
        id="test-uuid",
        symbol="BTCUSDT",
        base_asset="BTC",
        category="LARGE_CAP",
        tier=1,
        min_position_usd=Decimal("10.00"),
        max_position_usd=Decimal("500.00"),
        max_allocation_pct=Decimal("15.00"),
        default_grid_range_pct=Decimal("5.00"),
        min_volume_24h_usd=Decimal("500000000"),
        is_active=True,
        is_tradeable=True,
        total_trades=100,
        win_rate=Decimal("55.50"),
        avg_return_pct=Decimal("2.34"),
        sharpe_ratio=Decimal("1.50"),
        last_price=Decimal("50000.00"),
        last_volume_24h=Decimal("1000000000"),
        updated_at=None,
    )


class TestWatchlistCoin:
    """Tests für WatchlistCoin Dataclass."""

    def test_coin_creation(self, sample_coin):
        """Test dass WatchlistCoin korrekt erstellt wird."""
        assert sample_coin.symbol == "BTCUSDT"
        assert sample_coin.category == "LARGE_CAP"
        assert sample_coin.tier == 1
        assert sample_coin.is_active is True
        assert sample_coin.is_tradeable is True

    def test_coin_optional_fields(self):
        """Test dass optionale Felder None sein können."""
        coin = WatchlistCoin(
            id="test",
            symbol="ETHUSDT",
            base_asset="ETH",
            category="LARGE_CAP",
            tier=1,
            min_position_usd=Decimal("10"),
            max_position_usd=Decimal("500"),
            max_allocation_pct=Decimal("10"),
            default_grid_range_pct=None,
            min_volume_24h_usd=Decimal("100000000"),
            is_active=True,
            is_tradeable=True,
            total_trades=0,
            win_rate=None,
            avg_return_pct=None,
            sharpe_ratio=None,
            last_price=None,
            last_volume_24h=None,
            updated_at=None,
        )
        assert coin.default_grid_range_pct is None
        assert coin.win_rate is None


class TestWatchlistManager:
    """Tests für WatchlistManager."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton zwischen Tests."""
        WatchlistManager.reset_instance()
        yield
        WatchlistManager.reset_instance()

    @patch("src.data.watchlist.psycopg2")
    def test_singleton_pattern(self, mock_psycopg2):
        """Test dass Singleton-Pattern funktioniert."""
        mock_psycopg2.connect.return_value = MagicMock()

        manager1 = WatchlistManager.get_instance()
        manager2 = WatchlistManager.get_instance()

        assert manager1 is manager2

    @patch("src.data.watchlist.psycopg2")
    def test_connect_success(self, mock_psycopg2):
        """Test erfolgreiche DB-Verbindung."""
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        manager = WatchlistManager()

        assert manager.conn is not None
        mock_psycopg2.connect.assert_called_once()

    @patch("src.data.watchlist.psycopg2")
    def test_connect_failure(self, mock_psycopg2):
        """Test Fehlerbehandlung bei DB-Verbindung."""
        mock_psycopg2.connect.side_effect = Exception("Connection failed")

        manager = WatchlistManager()

        assert manager.conn is None

    @patch("src.data.watchlist.psycopg2")
    def test_load_watchlist(self, mock_psycopg2, mock_db_connection):
        """Test Laden der Watchlist aus DB."""
        conn, cursor = mock_db_connection
        mock_psycopg2.connect.return_value = conn

        # Mock DB response
        cursor.fetchall.return_value = [
            {
                "id": "uuid1",
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "category": "LARGE_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("500"),
                "max_allocation_pct": Decimal("15"),
                "default_grid_range_pct": Decimal("5"),
                "min_volume_24h_usd": Decimal("500000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 50,
                "win_rate": Decimal("55"),
                "avg_return_pct": Decimal("2.5"),
                "sharpe_ratio": Decimal("1.2"),
                "last_price": Decimal("50000"),
                "last_volume_24h": Decimal("1000000000"),
                "updated_at": None,
            }
        ]

        manager = WatchlistManager()
        coins = manager.load_watchlist()

        assert len(coins) == 1
        assert coins[0].symbol == "BTCUSDT"
        assert coins[0].category == "LARGE_CAP"

    @patch("src.data.watchlist.psycopg2")
    def test_get_tradeable_coins(self, mock_psycopg2, mock_db_connection):
        """Test Filtern nach tradeable Coins."""
        conn, cursor = mock_db_connection
        mock_psycopg2.connect.return_value = conn

        # Mock DB response mit einem tradeable und einem nicht-tradeable Coin
        cursor.fetchall.return_value = [
            {
                "id": "uuid1",
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "category": "LARGE_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("500"),
                "max_allocation_pct": Decimal("15"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("500000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
            {
                "id": "uuid2",
                "symbol": "LOWVOLCOIN",
                "base_asset": "LOW",
                "category": "MID_CAP",
                "tier": 3,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("100"),
                "max_allocation_pct": Decimal("5"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("10000000"),
                "is_active": True,
                "is_tradeable": False,  # Nicht tradeable
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
        ]

        manager = WatchlistManager()
        manager.load_watchlist()

        tradeable = manager.get_tradeable_coins()

        assert len(tradeable) == 1
        assert tradeable[0].symbol == "BTCUSDT"

    @patch("src.data.watchlist.psycopg2")
    def test_get_coins_by_category(self, mock_psycopg2, mock_db_connection):
        """Test Filtern nach Kategorie."""
        conn, cursor = mock_db_connection
        mock_psycopg2.connect.return_value = conn

        cursor.fetchall.return_value = [
            {
                "id": "uuid1",
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "category": "LARGE_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("500"),
                "max_allocation_pct": Decimal("15"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("500000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
            {
                "id": "uuid2",
                "symbol": "SOLUSDT",
                "base_asset": "SOL",
                "category": "MID_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("300"),
                "max_allocation_pct": Decimal("10"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("100000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
        ]

        manager = WatchlistManager()
        manager.load_watchlist()

        large_caps = manager.get_coins_by_category("LARGE_CAP")
        mid_caps = manager.get_coins_by_category("MID_CAP")

        assert len(large_caps) == 1
        assert large_caps[0].symbol == "BTCUSDT"
        assert len(mid_caps) == 1
        assert mid_caps[0].symbol == "SOLUSDT"

    @patch("src.data.watchlist.psycopg2")
    def test_get_stats(self, mock_psycopg2, mock_db_connection):
        """Test Statistik-Berechnung."""
        conn, cursor = mock_db_connection
        mock_psycopg2.connect.return_value = conn

        cursor.fetchall.return_value = [
            {
                "id": "uuid1",
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "category": "LARGE_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("500"),
                "max_allocation_pct": Decimal("15"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("500000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
            {
                "id": "uuid2",
                "symbol": "ETHUSDT",
                "base_asset": "ETH",
                "category": "LARGE_CAP",
                "tier": 1,
                "min_position_usd": Decimal("10"),
                "max_position_usd": Decimal("500"),
                "max_allocation_pct": Decimal("15"),
                "default_grid_range_pct": None,
                "min_volume_24h_usd": Decimal("200000000"),
                "is_active": True,
                "is_tradeable": True,
                "total_trades": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "sharpe_ratio": None,
                "last_price": None,
                "last_volume_24h": None,
                "updated_at": None,
            },
        ]

        manager = WatchlistManager()
        manager.load_watchlist()

        stats = manager.get_stats()

        assert stats["total_coins"] == 2
        assert stats["tradeable_coins"] == 2
        assert stats["by_category"]["LARGE_CAP"] == 2
        assert stats["by_tier"][1] == 2
