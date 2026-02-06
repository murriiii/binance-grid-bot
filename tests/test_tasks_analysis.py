"""Tests for src/tasks/analysis_tasks.py and src/tasks/cycle_tasks.py."""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# analysis_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskRegimeDetection:
    """Tests for task_regime_detection."""

    @patch("src.tasks.analysis_tasks.get_db_connection")
    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_happy_path(self, mock_detector_cls, mock_db):
        from src.analysis.regime_detection import MarketRegime
        from src.tasks.analysis_tasks import task_regime_detection

        regime_state = MagicMock()
        regime_state.current_regime = MarketRegime.SIDEWAYS
        regime_state.regime_probability = 0.82
        regime_state.model_confidence = 0.75

        mock_detector = MagicMock()
        mock_detector.predict_regime.return_value = regime_state
        mock_detector_cls.return_value = mock_detector

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        task_regime_detection()

        mock_detector.predict_regime.assert_called_once()
        mock_detector.store_regime.assert_called_once_with(regime_state)

    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_none_regime(self, mock_detector_cls):
        from src.tasks.analysis_tasks import task_regime_detection

        mock_detector = MagicMock()
        mock_detector.predict_regime.return_value = None
        mock_detector_cls.return_value = mock_detector

        task_regime_detection()

        mock_detector.store_regime.assert_not_called()

    @patch("src.analysis.regime_detection.RegimeDetector.get_instance")
    def test_exception_handling(self, mock_detector_cls):
        from src.tasks.analysis_tasks import task_regime_detection

        mock_detector_cls.side_effect = Exception("DB down")

        task_regime_detection()  # Should not raise


class TestTaskUpdateSignalWeights:
    @patch("src.analysis.bayesian_weights.BayesianWeightLearner.get_instance")
    def test_happy_path(self, mock_learner_cls):
        from src.tasks.analysis_tasks import task_update_signal_weights

        mock_learner = MagicMock()
        mock_learner.weekly_update.return_value = {
            "updates": [
                {
                    "type": "global",
                    "weights": {"rsi": 0.3, "macd": 0.25, "volume": 0.2},
                    "confidence": 0.85,
                    "sample_size": 150,
                }
            ],
            "errors": [],
        }
        mock_learner_cls.return_value = mock_learner

        task_update_signal_weights()

        mock_learner.weekly_update.assert_called_once()

    @patch("src.analysis.bayesian_weights.BayesianWeightLearner.get_instance")
    def test_no_updates(self, mock_learner_cls):
        from src.tasks.analysis_tasks import task_update_signal_weights

        mock_learner = MagicMock()
        mock_learner.weekly_update.return_value = {"updates": [], "errors": []}
        mock_learner_cls.return_value = mock_learner

        task_update_signal_weights()

    @patch("src.analysis.bayesian_weights.BayesianWeightLearner.get_instance")
    def test_exception(self, mock_learner_cls):
        from src.tasks.analysis_tasks import task_update_signal_weights

        mock_learner_cls.side_effect = RuntimeError("fail")
        task_update_signal_weights()


class TestTaskDivergenceScan:
    @patch("src.analysis.divergence_detector.DivergenceDetector.get_instance")
    def test_happy_path_with_divergences(self, mock_det_cls):
        from src.tasks.analysis_tasks import task_divergence_scan

        analysis = MagicMock()
        analysis.divergence_count = 2
        analysis.average_confidence = 0.7
        analysis.dominant_type.value = "BULLISH"
        analysis.net_signal = 0.6
        div1 = MagicMock()
        div1.indicator = "RSI"
        div1.divergence_type.value = "BULLISH"
        analysis.divergences = [div1]

        mock_det = MagicMock()
        mock_det.analyze.return_value = analysis
        mock_det_cls.return_value = mock_det

        task_divergence_scan()

        assert mock_det.analyze.call_count == 3  # BTC, ETH, SOL

    @patch("src.analysis.divergence_detector.DivergenceDetector.get_instance")
    def test_no_divergences(self, mock_det_cls):
        from src.tasks.analysis_tasks import task_divergence_scan

        analysis = MagicMock()
        analysis.divergence_count = 0
        analysis.average_confidence = 0.0

        mock_det = MagicMock()
        mock_det.analyze.return_value = analysis
        mock_det_cls.return_value = mock_det

        task_divergence_scan()

    @patch("src.analysis.divergence_detector.DivergenceDetector.get_instance")
    def test_exception(self, mock_det_cls):
        from src.tasks.analysis_tasks import task_divergence_scan

        mock_det_cls.side_effect = ImportError("missing")
        task_divergence_scan()


class TestTaskLearnPatterns:
    @patch("src.tasks.analysis_tasks.get_db_connection")
    @patch("src.data.memory.TradingMemory")
    def test_happy_path(self, mock_memory_cls, mock_db):
        from src.tasks.analysis_tasks import task_learn_patterns

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn

        mock_memory = MagicMock()
        mock_memory.db = True
        mock_memory_cls.return_value = mock_memory

        task_learn_patterns()

        mock_memory.learn_and_update_patterns.assert_called_once()
        mock_conn.close.assert_called()

    @patch("src.tasks.analysis_tasks.get_db_connection")
    def test_no_db(self, mock_db):
        from src.tasks.analysis_tasks import task_learn_patterns

        mock_db.return_value = None
        task_learn_patterns()


# ═══════════════════════════════════════════════════════════════
# cycle_tasks
# ═══════════════════════════════════════════════════════════════


class TestTaskCycleManagement:
    @patch("src.tasks.cycle_tasks.get_db_connection")
    @patch("src.core.cycle_manager.CycleManager.get_instance")
    def test_happy_path(self, mock_mgr_cls, mock_db):
        from src.tasks.cycle_tasks import task_cycle_management

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "aggressive"}]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        mock_mgr = MagicMock()
        mock_mgr.close_cycle.return_value = {
            "cycle_number": 5,
            "total_pnl_pct": 3.2,
            "sharpe_ratio": 1.5,
            "trades_count": 42,
        }
        new_cycle = MagicMock()
        new_cycle.cycle_number = 6
        mock_mgr.start_cycle.return_value = new_cycle
        mock_mgr_cls.return_value = mock_mgr

        task_cycle_management()

        mock_mgr.close_cycle.assert_called_once_with("1")
        mock_mgr.start_cycle.assert_called_once_with("1", "aggressive")

    @patch("src.tasks.cycle_tasks.get_db_connection")
    @patch("src.core.cycle_manager.CycleManager.get_instance")
    def test_no_db(self, mock_mgr_cls, mock_db):
        from src.tasks.cycle_tasks import task_cycle_management

        mock_db.return_value = None
        mock_mgr_cls.return_value = MagicMock()

        task_cycle_management()

    @patch("src.tasks.cycle_tasks.get_db_connection")
    @patch("src.core.cycle_manager.CycleManager.get_instance")
    def test_exception(self, mock_mgr_cls, mock_db):
        from src.tasks.cycle_tasks import task_cycle_management

        mock_mgr_cls.side_effect = Exception("fail")
        mock_db.return_value = None

        task_cycle_management()


class TestTaskWeeklyRebalance:
    @patch("src.notifications.telegram_service.get_telegram")
    def test_sends_message(self, mock_tg):
        from src.tasks.cycle_tasks import task_weekly_rebalance

        mock_telegram = MagicMock()
        mock_tg.return_value = mock_telegram

        task_weekly_rebalance()

        mock_telegram.send.assert_called_once()


class TestTaskAbTestCheck:
    @patch("src.optimization.ab_testing.ABTestingFramework.get_instance")
    def test_happy_path(self, mock_fw_cls):
        from src.tasks.cycle_tasks import task_ab_test_check

        mock_fw = MagicMock()
        mock_fw.get_all_experiments_summary.return_value = [
            {"id": "exp1", "name": "Test A", "status": "RUNNING"}
        ]
        mock_fw.check_early_stopping.return_value = (True, "Significant")
        result = MagicMock()
        result.winner = "variant_a"
        result.p_value = 0.01
        result.winner_improvement = 15.0
        result.significance.value = "HIGH"
        mock_fw.complete_experiment.return_value = result
        mock_fw_cls.return_value = mock_fw

        task_ab_test_check()

        mock_fw.check_early_stopping.assert_called_once_with("exp1")
        mock_fw.complete_experiment.assert_called_once()

    @patch("src.optimization.ab_testing.ABTestingFramework.get_instance")
    def test_no_running_experiments(self, mock_fw_cls):
        from src.tasks.cycle_tasks import task_ab_test_check

        mock_fw = MagicMock()
        mock_fw.get_all_experiments_summary.return_value = [
            {"id": "exp1", "name": "Done", "status": "COMPLETED"}
        ]
        mock_fw_cls.return_value = mock_fw

        task_ab_test_check()

        mock_fw.check_early_stopping.assert_not_called()

    @patch("src.optimization.ab_testing.ABTestingFramework.get_instance")
    def test_exception(self, mock_fw_cls):
        from src.tasks.cycle_tasks import task_ab_test_check

        mock_fw_cls.side_effect = RuntimeError("fail")
        task_ab_test_check()
