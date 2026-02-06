"""Tests for src/tasks/system_tasks.py, hybrid_tasks.py, and reporting_tasks.py."""

import json
from unittest.mock import MagicMock, mock_open, patch

# ═══════════════════════════════════════════════════════════════
# system_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskCheckStops:
    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_happy_path_no_triggers(self, mock_md, mock_db):
        from src.tasks.system_tasks import task_check_stops

        mock_market = MagicMock()
        mock_market.get_price.return_value = 65000.0
        mock_md.return_value = mock_market

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "entry_price": 60000,
                "stop_price": 57000,
                "quantity": 0.1,
                "stop_type": "fixed",
                "highest_price": None,
                "trailing_distance": None,
            }
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        task_check_stops()

        mock_conn.close.assert_called()

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    @patch("src.risk.stop_loss_executor.execute_stop_loss_sell")
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.api.binance_client.BinanceClient")
    def test_stop_triggered(self, mock_client_cls, mock_tg, mock_exec, mock_md, mock_db):
        from src.tasks.system_tasks import task_check_stops

        mock_market = MagicMock()
        mock_market.get_price.return_value = 56000.0  # Below stop price
        mock_md.return_value = mock_market

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "entry_price": 60000,
                "stop_price": 57000,
                "quantity": 0.1,
                "stop_type": "fixed",
                "highest_price": None,
                "trailing_distance": None,
            }
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram
        mock_exec.return_value = {"success": True}

        task_check_stops()

        mock_exec.assert_called_once()
        mock_telegram.send_stop_loss_alert.assert_called_once()

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.system_tasks import task_check_stops

        mock_db.return_value = None
        task_check_stops()

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_trailing_stop_update(self, mock_md, mock_db):
        from src.tasks.system_tasks import task_check_stops

        mock_market = MagicMock()
        mock_market.get_price.return_value = 70000.0  # Above highest
        mock_md.return_value = mock_market

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "entry_price": 60000,
                "stop_price": 63650,
                "quantity": 0.1,
                "stop_type": "trailing",
                "highest_price": 65000,
                "trailing_distance": 5.0,
            }
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        task_check_stops()

        mock_conn.close.assert_called()


class TestTaskResetDailyDrawdown:
    @patch("src.api.binance_client.BinanceClient")
    def test_happy_path(self, mock_client_cls):
        from src.tasks.system_tasks import task_reset_daily_drawdown

        mock_client = MagicMock()
        mock_client.get_account_balance.return_value = 5000.0
        mock_client_cls.return_value = mock_client

        task_reset_daily_drawdown()

        mock_client.get_account_balance.assert_called_once_with("USDT")

    @patch("src.api.binance_client.BinanceClient")
    def test_zero_balance(self, mock_client_cls):
        from src.tasks.system_tasks import task_reset_daily_drawdown

        mock_client = MagicMock()
        mock_client.get_account_balance.return_value = 0
        mock_client_cls.return_value = mock_client

        task_reset_daily_drawdown()

    @patch("src.api.binance_client.BinanceClient")
    def test_exception(self, mock_client_cls):
        from src.tasks.system_tasks import task_reset_daily_drawdown

        mock_client_cls.side_effect = Exception("API error")
        task_reset_daily_drawdown()


class TestTaskUpdateOutcomes:
    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_happy_path(self, mock_md, mock_db):
        from src.tasks.system_tasks import task_update_outcomes

        mock_market = MagicMock()
        mock_market.get_price.return_value = 66000.0
        mock_md.return_value = mock_market

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "symbol": "BTCUSDT", "price": 65000, "action": "BUY"}
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        task_update_outcomes()

        mock_conn.commit.assert_called()
        mock_conn.close.assert_called()

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.system_tasks import task_update_outcomes

        mock_db.return_value = None
        task_update_outcomes()


class TestTaskMacroCheck:
    @patch("src.data.economic_events.EconomicCalendar")
    def test_happy_path(self, mock_cal_cls):
        from src.tasks.system_tasks import task_macro_check

        event = MagicMock()
        event.impact = "HIGH"
        event.name = "FOMC Meeting"
        event.date.strftime.return_value = "15.01 20:00"

        mock_cal = MagicMock()
        mock_cal.fetch_upcoming_events.return_value = [event]
        mock_cal_cls.return_value = mock_cal

        task_macro_check()

    @patch("src.data.economic_events.EconomicCalendar")
    def test_no_events(self, mock_cal_cls):
        from src.tasks.system_tasks import task_macro_check

        mock_cal = MagicMock()
        mock_cal.fetch_upcoming_events.return_value = []
        mock_cal_cls.return_value = mock_cal

        task_macro_check()

    @patch("src.data.economic_events.EconomicCalendar")
    def test_exception(self, mock_cal_cls):
        from src.tasks.system_tasks import task_macro_check

        mock_cal_cls.side_effect = ImportError("no module")
        task_macro_check()


class TestTaskSystemHealthCheck:
    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    @patch("src.core.logging_system.get_logger")
    def test_psutil_not_available(self, mock_logger, mock_md, mock_db):
        from src.tasks.system_tasks import task_system_health_check

        mock_tl = MagicMock()
        mock_logger.return_value = mock_tl
        mock_db.return_value = MagicMock()

        # psutil import may fail in test env
        task_system_health_check()


# ═══════════════════════════════════════════════════════════════
# hybrid_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskModeEvaluation:
    @patch("src.tasks.hybrid_tasks.get_db_connection")
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.core.mode_manager.ModeManager.get_instance")
    @patch("src.core.hybrid_config.HybridConfig.from_env")
    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_happy_path(self, mock_det_cls, mock_hcfg, mock_mm_cls, mock_tg, mock_db):
        from src.analysis.regime_detection import MarketRegime
        from src.tasks.hybrid_tasks import task_mode_evaluation

        regime_state = MagicMock()
        regime_state.current_regime = MarketRegime.BULL
        regime_state.regime_probability = 0.85

        mock_det = MagicMock()
        mock_det.predict_regime.return_value = regime_state
        mock_det_cls.return_value = mock_det

        mock_hcfg.return_value = MagicMock()

        from src.core.mode_manager import TradingMode

        current = MagicMock()
        current.current_mode = TradingMode.GRID

        mock_mm = MagicMock()
        mock_mm.evaluate_mode.return_value = (TradingMode.HOLD, "Bull regime detected")
        mock_mm.get_current_mode.return_value = current
        mock_mm_cls.return_value = mock_mm

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_mode_evaluation()

        mock_mm.update_regime_info.assert_called_once()
        mock_mm.evaluate_mode.assert_called_once()

    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_no_regime_data(self, mock_det_cls):
        from src.tasks.hybrid_tasks import task_mode_evaluation

        mock_det = MagicMock()
        mock_det.predict_regime.return_value = None
        mock_det_cls.return_value = mock_det

        task_mode_evaluation()

    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_exception(self, mock_det_cls):
        from src.tasks.hybrid_tasks import task_mode_evaluation

        mock_det_cls.side_effect = Exception("fail")
        task_mode_evaluation()


class TestTaskHybridRebalance:
    @patch("src.data.market_data.get_market_data")
    def test_no_state_file(self, mock_md):
        from src.tasks.hybrid_tasks import task_hybrid_rebalance

        with patch("pathlib.Path.exists", return_value=False):
            task_hybrid_rebalance()

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.data.market_data.get_market_data")
    def test_drift_detected(self, mock_md, mock_tg):
        from src.tasks.hybrid_tasks import task_hybrid_rebalance

        state = {
            "symbols": {
                "BTCUSDT": {"allocation_usd": 1000, "hold_quantity": 0.02},
            }
        }

        mock_market = MagicMock()
        mock_market.get_price.return_value = 80000.0  # 0.02 * 80000 = 1600, 60% drift
        mock_md.return_value = mock_market

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(state))),
        ):
            task_hybrid_rebalance()

        mock_telegram.send.assert_called_once()

    @patch("src.data.market_data.get_market_data")
    def test_no_drift(self, mock_md):
        from src.tasks.hybrid_tasks import task_hybrid_rebalance

        state = {
            "symbols": {
                "BTCUSDT": {"allocation_usd": 1000, "hold_quantity": 0.015},
            }
        }

        mock_market = MagicMock()
        mock_market.get_price.return_value = 65000.0  # 0.015 * 65000 = 975, 2.5% drift
        mock_md.return_value = mock_market

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(state))),
        ):
            task_hybrid_rebalance()

    @patch("src.data.market_data.get_market_data")
    def test_exception(self, mock_md):
        from src.tasks.hybrid_tasks import task_hybrid_rebalance

        mock_md.side_effect = Exception("fail")

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="{}")),
        ):
            task_hybrid_rebalance()


# ═══════════════════════════════════════════════════════════════
# reporting_tasks
# ═══════════════════════════════════════════════════════════════


class TestCheckDataSourcesStatus:
    def test_all_unavailable(self):
        from src.tasks.reporting_tasks import check_data_sources_status

        with patch.dict("os.environ", {}, clear=True):
            status = check_data_sources_status()

        assert not status["lunarcrush"]
        assert not status["reddit"]
        assert not status["telegram"]

    def test_some_available(self):
        from src.tasks.reporting_tasks import check_data_sources_status

        env = {"DEEPSEEK_API_KEY": "test", "LUNARCRUSH_API_KEY": "test"}
        with patch.dict("os.environ", env, clear=True):
            status = check_data_sources_status()

        assert status["deepseek"]
        assert status["lunarcrush"]
        assert not status["reddit"]


class TestFormatDataSourcesReport:
    def test_all_available(self):
        from src.tasks.reporting_tasks import format_data_sources_report

        env = {
            "LUNARCRUSH_API_KEY": "x",
            "REDDIT_CLIENT_ID": "x",
            "REDDIT_CLIENT_SECRET": "x",
            "TOKEN_UNLOCKS_API_KEY": "x",
            "DEEPSEEK_API_KEY": "x",
            "TELEGRAM_BOT_TOKEN": "x",
            "TELEGRAM_CHAT_ID": "x",
        }
        with patch.dict("os.environ", env, clear=True):
            report = format_data_sources_report()

        assert report == ""

    def test_some_unavailable(self):
        from src.tasks.reporting_tasks import format_data_sources_report

        with patch.dict("os.environ", {}, clear=True):
            report = format_data_sources_report()

        assert "Inaktive Datenquellen" in report


class TestTaskDailySummary:
    @patch("src.tasks.reporting_tasks.generate_performance_chart")
    @patch("src.tasks.reporting_tasks.format_data_sources_report")
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.data.market_data.get_market_data")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    def test_happy_path(self, mock_db, mock_md, mock_tg, mock_fmt, mock_chart):
        from src.tasks.reporting_tasks import task_daily_summary

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"trade_count": 5, "wins": 3, "avg_return": 1.2},
            {"total_value_usd": 10000, "daily_pnl_pct": 2.5},
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_market = MagicMock()
        fg = MagicMock()
        fg.value = 55
        mock_market.get_fear_greed.return_value = fg
        mock_md.return_value = mock_market

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        mock_fmt.return_value = ""

        task_daily_summary()

        mock_telegram.send_daily_summary.assert_called_once()

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    def test_no_db(self, mock_db, mock_tg):
        from src.tasks.reporting_tasks import task_daily_summary

        mock_db.return_value = None
        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_daily_summary()

        mock_telegram.send.assert_called_once()


class TestTaskUpdatePlaybook:
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    @patch("src.data.playbook.TradingPlaybook")
    def test_happy_path(self, mock_pb_cls, mock_db, mock_tg):
        from src.tasks.reporting_tasks import task_update_playbook

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn

        mock_pb = MagicMock()
        mock_pb.analyze_and_update.return_value = {
            "version": 3,
            "changes": ["Added new rule"],
            "metrics": {
                "total_trades": 100,
                "success_rate": 65.0,
                "fear_greed_patterns": [{"action": "BUY", "range": "20-30", "success_rate": 75.0}],
                "anti_patterns": [
                    {"action": "SELL", "symbol": "BTC", "fear_greed": 90, "avg_return": -2.5}
                ],
            },
        }
        mock_pb_cls.return_value = mock_pb

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_update_playbook()

        mock_pb.analyze_and_update.assert_called_once()
        mock_telegram.send.assert_called()

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    def test_no_db(self, mock_db, mock_tg):
        from src.tasks.reporting_tasks import task_update_playbook

        mock_db.return_value = None
        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_update_playbook()

        mock_telegram.send.assert_called_once()

    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    @patch("src.data.playbook.TradingPlaybook")
    def test_error_result(self, mock_pb_cls, mock_db, mock_tg):
        from src.tasks.reporting_tasks import task_update_playbook

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn

        mock_pb = MagicMock()
        mock_pb.analyze_and_update.return_value = {"error": "Not enough data"}
        mock_pb_cls.return_value = mock_pb

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_update_playbook()


class TestTaskWeeklyExport:
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.core.logging_system.get_logger")
    @patch("src.analysis.weekly_export.WeeklyExporter")
    def test_happy_path(self, mock_exp_cls, mock_logger, mock_tg):
        from src.tasks.reporting_tasks import task_weekly_export

        mock_exp = MagicMock()
        mock_exp.export_weekly_analysis.return_value = {
            "summary": {
                "total_trades": 50,
                "win_rate": 0.65,
                "total_pnl": 250.0,
                "error_count": 2,
            },
            "export_path": "/app/exports/week_2025_01.json",
        }
        mock_exp_cls.return_value = mock_exp

        mock_tl = MagicMock()
        mock_logger.return_value = mock_tl

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_weekly_export()

        mock_exp.export_weekly_analysis.assert_called_once()
        mock_telegram.send.assert_called()

    @patch("src.analysis.weekly_export.WeeklyExporter")
    def test_exception(self, mock_exp_cls):
        from src.tasks.reporting_tasks import task_weekly_export

        mock_exp_cls.side_effect = Exception("fail")
        task_weekly_export()


class TestGeneratePerformanceChart:
    @patch("src.notifications.telegram_service.get_telegram")
    @patch("src.tasks.reporting_tasks.get_db_connection")
    def test_not_enough_data(self, mock_db, mock_tg):
        from src.tasks.reporting_tasks import generate_performance_chart

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"date": "2025-01-01", "total_value_usd": 1000}]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        generate_performance_chart()

    @patch("src.tasks.reporting_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.reporting_tasks import generate_performance_chart

        mock_db.return_value = None
        generate_performance_chart()


class TestTaskBase:
    @patch("src.data.database.DatabaseManager.get_instance")
    def test_get_db_connection_success(self, mock_db_cls):
        from src.tasks.base import get_db_connection

        mock_db = MagicMock()
        mock_db.get_connection.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        conn = get_db_connection()
        assert conn is not None

    @patch("src.data.database.DatabaseManager.get_instance")
    def test_get_db_connection_failure(self, mock_db_cls):
        from src.tasks.base import get_db_connection

        mock_db_cls.side_effect = Exception("no DB")
        conn = get_db_connection()
        assert conn is None
