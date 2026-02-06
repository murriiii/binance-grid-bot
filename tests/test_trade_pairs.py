"""Tests for TradePairTracker."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock


class TestTradePairTrackerNoDb:
    """TradePairTracker gracefully handles missing DB."""

    def test_no_db_open_pair_returns_none(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None
        tracker.db = None

        result = tracker.open_pair("BTCUSDT", "trade-1", 50000.0, 0.001, 0.05)
        assert result is None

    def test_no_db_close_pair_returns_false(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None
        tracker.db = None

        result = tracker.close_pair("BTCUSDT", "trade-2", 51000.0, 0.001, 0.05)
        assert result is False

    def test_no_db_close_pairs_by_symbol_returns_zero(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None
        tracker.db = None

        result = tracker.close_pairs_by_symbol("BTCUSDT", 48000.0, 0.001)
        assert result == 0


class TestTradePairTrackerOpen:
    """Test opening trade pairs with mocked DB."""

    def test_open_pair_inserts_row(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = "cohort-123"

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("pair-uuid-1",)

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        result = tracker.open_pair("ETHUSDT", "trade-42", 3000.0, 0.5, 1.5)

        assert result == "pair-uuid-1"
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO trade_pairs" in sql
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "cohort-123"  # cohort_id
        assert params[1] == "ETHUSDT"  # symbol
        assert params[4] == 3000.0  # entry_price
        assert params[5] == 0.5  # entry_qty
        assert params[6] == 1500.0  # entry_value_usd

    def test_open_pair_db_error_returns_none(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None

        mock_db = MagicMock()
        mock_db.get_cursor.side_effect = Exception("DB down")
        tracker.db = mock_db

        result = tracker.open_pair("BTCUSDT", "trade-1", 50000.0, 0.001, 0.05)
        assert result is None


class TestTradePairTrackerClose:
    """Test closing trade pairs with mocked DB."""

    def test_close_pair_fifo(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = "cohort-123"

        entry_ts = datetime.now() - timedelta(hours=2)
        mock_cursor = MagicMock()
        # SELECT returns oldest open pair
        mock_cursor.fetchone.return_value = (
            "pair-uuid-old",  # id
            100.0,  # entry_price
            1.0,  # entry_quantity
            100.0,  # entry_value_usd
            0.1,  # entry_fee_usd
            entry_ts,  # entry_timestamp
        )

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        result = tracker.close_pair("SOLUSDT", "trade-99", 110.0, 1.0, 0.11)

        assert result is True
        # Should have called SELECT then UPDATE
        assert mock_cursor.execute.call_count == 2
        update_sql = mock_cursor.execute.call_args_list[1][0][0]
        assert "UPDATE trade_pairs" in update_sql
        update_params = mock_cursor.execute.call_args_list[1][0][1]
        # exit_price = 110.0
        assert update_params[2] == 110.0
        # gross_pnl = 110*1 - 100 = 10.0
        assert update_params[6] == 10.0
        # net_pnl = 10.0 - 0.1 - 0.11 = 9.79
        assert abs(update_params[7] - 9.79) < 0.01

    def test_close_pair_no_open_returns_false(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        result = tracker.close_pair("BTCUSDT", "trade-2", 51000.0, 0.001, 0.05)
        assert result is False


class TestTradePairTrackerBulkClose:
    """Test closing all pairs for a symbol (stop-loss scenario)."""

    def test_close_pairs_by_symbol(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = "cohort-1"

        entry_ts = datetime.now() - timedelta(hours=4)
        mock_cursor = MagicMock()
        # Two open pairs
        mock_cursor.fetchall.return_value = [
            ("pair-1", 100.0, 0.5, 50.0, 0.05, entry_ts),
            ("pair-2", 105.0, 0.3, 31.5, 0.03, entry_ts),
        ]

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        result = tracker.close_pairs_by_symbol("SOLUSDT", 90.0, 0.8, "stop_loss")

        assert result == 2
        # 1 SELECT + 2 UPDATEs
        assert mock_cursor.execute.call_count == 3

    def test_close_pairs_no_open_returns_zero(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        result = tracker.close_pairs_by_symbol("BTCUSDT", 48000.0, 0.001)
        assert result == 0


class TestPnlCalculation:
    """Verify P&L math in close_pair."""

    def test_pnl_correct_with_fees(self):
        from src.data.trade_pairs import TradePairTracker

        tracker = TradePairTracker.__new__(TradePairTracker)
        tracker.cohort_id = None

        entry_ts = datetime.now() - timedelta(hours=1)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "pair-1",
            50000.0,  # entry_price
            0.01,  # entry_quantity
            500.0,  # entry_value_usd (50000 * 0.01)
            0.50,  # entry_fee_usd
            entry_ts,
        )

        mock_db = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        tracker.db = mock_db

        tracker.close_pair("BTCUSDT", "exit-1", 51000.0, 0.01, 0.51)

        update_params = mock_cursor.execute.call_args_list[1][0][1]
        exit_value = 51000.0 * 0.01  # 510.0
        gross_pnl = exit_value - 500.0  # 10.0
        net_pnl = gross_pnl - 0.50 - 0.51  # 8.99
        pnl_pct = net_pnl / 500.0 * 100  # 1.798

        assert abs(update_params[6] - gross_pnl) < 0.001  # gross_pnl
        assert abs(update_params[7] - net_pnl) < 0.001  # net_pnl
        assert abs(update_params[8] - pnl_pct) < 0.01  # pnl_pct
