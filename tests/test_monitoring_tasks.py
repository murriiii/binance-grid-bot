"""Tests for src/tasks/monitoring_tasks.py."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _grid_state(symbol: str, orders: dict | None = None) -> dict:
    """Build a minimal grid state dict."""
    return {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "active_orders": orders or {},
    }


def _hybrid_state(symbols: dict | None = None) -> dict:
    """Build a minimal hybrid state dict."""
    return {
        "symbols": symbols or {},
    }


def _write_state(tmp_path: Path, filename: str, data: dict):
    """Write a JSON state file to tmp_path/config/."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    with open(config_dir / filename, "w") as f:
        json.dump(data, f)


# ═══════════════════════════════════════════════════════════════
# _load_grid_states
# ═══════════════════════════════════════════════════════════════


class TestLoadGridStates:
    def test_loads_grid_state_files(self, tmp_path):
        from src.tasks.monitoring_tasks import _load_grid_states

        state = _grid_state("BTCUSDT", {"123": {"type": "BUY", "price": "50000"}})
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            result = _load_grid_states()

        assert "conservative:BTCUSDT" in result
        assert result["conservative:BTCUSDT"]["symbol"] == "BTCUSDT"

    def test_empty_dir(self, tmp_path):
        from src.tasks.monitoring_tasks import _load_grid_states

        (tmp_path / "config").mkdir(exist_ok=True)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            result = _load_grid_states()

        assert result == {}

    def test_corrupt_json_skipped(self, tmp_path):
        from src.tasks.monitoring_tasks import _load_grid_states

        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "grid_state_ETHUSDT_balanced.json").write_text("not json{{{")

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", config_dir):
            result = _load_grid_states()

        assert result == {}


# ═══════════════════════════════════════════════════════════════
# task_reconcile_orders
# ═══════════════════════════════════════════════════════════════


class TestTaskReconcileOrders:
    @patch("src.tasks.monitoring_tasks._get_binance_client")
    def test_all_orders_match(self, mock_client_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_reconcile_orders

        state = _grid_state(
            "BTCUSDT",
            {
                "111": {"type": "BUY", "price": "50000", "quantity": "0.001"},
                "222": {"type": "SELL", "price": "52000", "quantity": "0.001"},
            },
        )
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        mock_client = MagicMock()
        mock_client.get_open_orders.return_value = [
            {"orderId": 111},
            {"orderId": 222},
        ]
        mock_client_fn.return_value = mock_client

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_reconcile_orders()

        mock_client.get_open_orders.assert_called_once_with("BTCUSDT")

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.monitoring_tasks._get_binance_client")
    def test_orphan_detected(self, mock_client_fn, mock_tg_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_reconcile_orders

        state = _grid_state(
            "BTCUSDT",
            {
                "111": {"type": "BUY", "price": "50000", "quantity": "0.001"},
                "222": {"type": "SELL", "price": "52000", "quantity": "0.001"},
            },
        )
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        mock_client = MagicMock()
        # Only order 111 exists on Binance, 222 is orphan
        mock_client.get_open_orders.return_value = [{"orderId": 111}]
        mock_client_fn.return_value = mock_client

        mock_telegram = MagicMock()
        mock_tg_fn.return_value = mock_telegram

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_reconcile_orders()

        mock_telegram.send.assert_called_once()
        call_msg = mock_telegram.send.call_args[0][0]
        assert "Orphans" in call_msg
        assert "1" in call_msg

    def test_no_state_files(self, tmp_path):
        from src.tasks.monitoring_tasks import task_reconcile_orders

        (tmp_path / "config").mkdir(exist_ok=True)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_reconcile_orders()  # Should not raise


# ═══════════════════════════════════════════════════════════════
# task_order_timeout_check
# ═══════════════════════════════════════════════════════════════


class TestTaskOrderTimeoutCheck:
    def test_detects_stale_orders(self, tmp_path):
        from src.tasks.monitoring_tasks import task_order_timeout_check

        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        medium_time = (datetime.now() - timedelta(hours=8)).isoformat()
        fresh_time = datetime.now().isoformat()

        state = _grid_state(
            "BTCUSDT",
            {
                "1": {"type": "BUY", "price": "50000", "quantity": "0.001", "created_at": old_time},
                "2": {
                    "type": "BUY",
                    "price": "49000",
                    "quantity": "0.001",
                    "created_at": medium_time,
                },
                "3": {
                    "type": "SELL",
                    "price": "52000",
                    "quantity": "0.001",
                    "created_at": fresh_time,
                },
            },
        )
        _write_state(tmp_path, "grid_state_BTCUSDT_balanced.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_order_timeout_check()  # Should not raise

    def test_empty_state(self, tmp_path):
        from src.tasks.monitoring_tasks import task_order_timeout_check

        (tmp_path / "config").mkdir(exist_ok=True)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_order_timeout_check()


# ═══════════════════════════════════════════════════════════════
# task_portfolio_plausibility
# ═══════════════════════════════════════════════════════════════


class TestTaskPortfolioPlausibility:
    @patch("src.tasks.monitoring_tasks._get_binance_client")
    def test_healthy_portfolio(self, mock_client_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_portfolio_plausibility

        state = _hybrid_state(
            {
                "BTCUSDT": {"allocation_usd": 250, "mode": "GRID"},
                "ETHUSDT": {"allocation_usd": 250, "mode": "GRID"},
            }
        )
        _write_state(tmp_path, "hybrid_state_conservative.json", state)

        mock_client = MagicMock()
        mock_client.get_account_balance.return_value = 5000.0
        mock_client_fn.return_value = mock_client

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_portfolio_plausibility()

        mock_client.get_account_balance.assert_called_once_with("USDT")

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.monitoring_tasks._get_binance_client")
    def test_negative_allocation_alerts(self, mock_client_fn, mock_tg_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_portfolio_plausibility

        state = _hybrid_state(
            {
                "BTCUSDT": {"allocation_usd": -50, "mode": "GRID"},
            }
        )
        _write_state(tmp_path, "hybrid_state_broken.json", state)

        mock_client = MagicMock()
        mock_client.get_account_balance.return_value = 1000.0
        mock_client_fn.return_value = mock_client

        mock_telegram = MagicMock()
        mock_tg_fn.return_value = mock_telegram

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_portfolio_plausibility()

        mock_telegram.send.assert_called_once()
        assert "negative allocation" in mock_telegram.send.call_args[0][0]

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.monitoring_tasks._get_binance_client")
    def test_zero_balance_alerts(self, mock_client_fn, mock_tg_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_portfolio_plausibility

        state = _hybrid_state(
            {
                "BTCUSDT": {"allocation_usd": 250, "mode": "GRID"},
            }
        )
        _write_state(tmp_path, "hybrid_state_test.json", state)

        mock_client = MagicMock()
        mock_client.get_account_balance.return_value = 0.0
        mock_client_fn.return_value = mock_client

        mock_telegram = MagicMock()
        mock_tg_fn.return_value = mock_telegram

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_portfolio_plausibility()

        mock_telegram.send.assert_called_once()
        assert "USDT balance" in mock_telegram.send.call_args[0][0]


# ═══════════════════════════════════════════════════════════════
# task_grid_health_summary
# ═══════════════════════════════════════════════════════════════


class TestTaskGridHealthSummary:
    def test_healthy_grid(self, tmp_path):
        from src.tasks.monitoring_tasks import task_grid_health_summary

        state = _grid_state(
            "BTCUSDT",
            {
                "1": {"type": "BUY", "price": "50000", "quantity": "0.001"},
                "2": {"type": "SELL", "price": "52000", "quantity": "0.001"},
            },
        )
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_grid_health_summary()  # Should not raise, no alerts

    def test_empty_grid_detected(self, tmp_path):
        from src.tasks.monitoring_tasks import task_grid_health_summary

        state = _grid_state("BTCUSDT", {})
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_grid_health_summary()

    @patch("src.notifications.telegram_service.get_telegram")
    def test_failed_followup_alerts(self, mock_tg_fn, tmp_path):
        from src.tasks.monitoring_tasks import task_grid_health_summary

        state = _grid_state(
            "BTCUSDT",
            {
                "1": {
                    "type": "BUY",
                    "price": "50000",
                    "quantity": "0.001",
                    "failed_followup": True,
                },
                "2": {"type": "SELL", "price": "52000", "quantity": "0.001"},
            },
        )
        _write_state(tmp_path, "grid_state_BTCUSDT_aggressive.json", state)

        mock_telegram = MagicMock()
        mock_tg_fn.return_value = mock_telegram

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_grid_health_summary()

        mock_telegram.send.assert_called_once()
        assert "Failed follow-ups" in mock_telegram.send.call_args[0][0]

    def test_no_sell_orders_logged(self, tmp_path):
        from src.tasks.monitoring_tasks import task_grid_health_summary

        state = _grid_state(
            "ETHUSDT",
            {
                "1": {"type": "BUY", "price": "2500", "quantity": "0.1"},
                "2": {"type": "BUY", "price": "2400", "quantity": "0.1"},
            },
        )
        _write_state(tmp_path, "grid_state_ETHUSDT_balanced.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_grid_health_summary()  # Logs "no sells" but no Telegram alert


# ═══════════════════════════════════════════════════════════════
# task_stale_detection
# ═══════════════════════════════════════════════════════════════


class TestTaskStaleDetection:
    def test_no_grid_states(self, tmp_path):
        """No alert when no grid state files."""
        from src.tasks.monitoring_tasks import task_stale_detection

        (tmp_path / "config").mkdir(exist_ok=True)
        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_stale_detection()  # Should just log and return

    @patch("src.notifications.telegram_service.get_telegram")
    def test_stale_orders_triggers_alert(self, mock_tg, tmp_path):
        """Alert when newest order is older than 30 minutes."""
        from src.tasks.monitoring_tasks import task_stale_detection

        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        state = _grid_state("BTCUSDT", {"1": {"type": "BUY", "created_at": old_time}})
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_stale_detection()

        mock_tg.return_value.send.assert_called_once()
        call_args = mock_tg.return_value.send.call_args[0][0]
        assert "Stale" in call_args

    def test_fresh_orders_no_alert(self, tmp_path):
        """No alert when orders are recent."""
        from src.tasks.monitoring_tasks import task_stale_detection

        recent_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        state = _grid_state("BTCUSDT", {"1": {"type": "BUY", "created_at": recent_time}})
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_stale_detection()  # No telegram call expected

    def test_no_timestamps_in_orders(self, tmp_path):
        """Handles orders with no created_at gracefully."""
        from src.tasks.monitoring_tasks import task_stale_detection

        state = _grid_state("BTCUSDT", {"1": {"type": "BUY"}})
        _write_state(tmp_path, "grid_state_BTCUSDT_conservative.json", state)

        with patch("src.tasks.monitoring_tasks.CONFIG_DIR", tmp_path / "config"):
            task_stale_detection()  # Should log warning about no timestamps


# ═══════════════════════════════════════════════════════════════
# task_discovery_health_check
# ═══════════════════════════════════════════════════════════════


class TestTaskDiscoveryHealthCheck:
    @patch("src.tasks.base.get_db_connection")
    def test_no_db_connection(self, mock_db):
        """No crash when DB unavailable."""
        from src.tasks.monitoring_tasks import task_discovery_health_check

        mock_db.return_value = None
        task_discovery_health_check()  # Should just log warning

    @patch("src.tasks.base.get_db_connection")
    def test_empty_table(self, mock_db):
        """No alert when coin_discoveries is empty."""
        from src.tasks.monitoring_tasks import task_discovery_health_check

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"last_run": None}
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value = mock_conn

        task_discovery_health_check()  # Should log "no discoveries yet"

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.base.get_db_connection")
    def test_stale_discovery_alert(self, mock_db, mock_tg):
        """Alert when last discovery is older than 48h."""
        from src.tasks.monitoring_tasks import task_discovery_health_check

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        old_time = datetime.utcnow() - timedelta(hours=72)
        mock_cursor.fetchone.side_effect = [
            {"last_run": old_time},  # MAX(discovered_at)
            {"total": 5, "approved": 2},  # approval rate
        ]
        mock_cursor.fetchall.return_value = []  # idle coins
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value = mock_conn

        task_discovery_health_check()

        mock_tg.return_value.send.assert_called_once()
        call_args = mock_tg.return_value.send.call_args[0][0]
        assert ">48h" in call_args
