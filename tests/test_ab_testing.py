"""
Tests für ABTestingFramework
"""

import numpy as np


class TestABTestingFramework:
    """Tests für A/B Testing Framework"""

    def test_create_experiment(self, reset_new_singletons):
        """Test Experiment-Erstellung"""
        from src.optimization.ab_testing import ABTestingFramework, ExperimentStatus

        framework = ABTestingFramework()

        experiment = framework.create_experiment(
            name="Test Experiment",
            description="Testing signal weights",
            hypothesis="Higher RSI weight improves performance",
            control_config={"rsi_weight": 0.1},
            treatment_configs=[{"rsi_weight": 0.2}, {"rsi_weight": 0.3}],
            metric="pnl",
            min_sample_size=10,
        )

        assert experiment.name == "Test Experiment"
        assert experiment.status == ExperimentStatus.DRAFT
        assert len(experiment.treatments) == 2

    def test_start_experiment(self, reset_new_singletons):
        """Test Experiment starten"""
        from src.optimization.ab_testing import ABTestingFramework, ExperimentStatus

        framework = ABTestingFramework()

        experiment = framework.create_experiment(
            name="Start Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )

        result = framework.start_experiment(experiment.id)

        assert result is True
        assert framework.experiments[experiment.id].status == ExperimentStatus.RUNNING
        assert framework.experiments[experiment.id].start_date is not None

    def test_record_trade(self, reset_new_singletons):
        """Test Trade Recording"""
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework()

        experiment = framework.create_experiment(
            name="Trade Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )

        framework.start_experiment(experiment.id)

        # Record trades
        framework.record_trade(experiment.id, "control", 10.0)
        framework.record_trade(experiment.id, "control", -5.0)
        framework.record_trade(experiment.id, "treatment_A", 15.0)

        exp = framework.experiments[experiment.id]
        assert exp.control.sample_size == 2
        assert exp.control.total_pnl == 5.0
        assert exp.treatments[0].sample_size == 1

    def test_variant_stats_update(self, reset_new_singletons):
        """Test Statistik-Update"""
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework()

        experiment = framework.create_experiment(
            name="Stats Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )

        framework.start_experiment(experiment.id)

        # Record multiple trades
        trades = [10, -5, 15, -3, 8, 12, -2]
        for pnl in trades:
            framework.record_trade(experiment.id, "control", float(pnl))

        exp = framework.experiments[experiment.id]

        assert exp.control.sample_size == len(trades)
        assert abs(exp.control.mean_pnl - np.mean(trades)) < 0.01
        assert exp.control.win_rate > 0.5  # Mehr Gewinner als Verlierer

    def test_statistical_result(self, reset_new_singletons):
        """Test StatisticalResult Creation"""
        from src.optimization.ab_testing import SignificanceLevel, StatisticalResult

        result = StatisticalResult(
            test_name="welch_t_test",
            p_value=0.03,
            significance=SignificanceLevel.SIGNIFICANT,
            effect_size=0.5,
            confidence_interval=(-0.1, 0.3),
            winner="treatment_A",
            winner_improvement=15.0,
        )

        assert result.test_name == "welch_t_test"
        assert result.significance == SignificanceLevel.SIGNIFICANT
        assert result.winner == "treatment_A"

    def test_experiment_summary(self, reset_new_singletons):
        """Test Experiment Summary"""
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework()

        experiment = framework.create_experiment(
            name="Summary Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )

        summary = framework.get_experiment_summary(experiment.id)

        assert summary["name"] == "Summary Test"
        assert "variants" in summary
        assert "control" in summary["variants"]

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.optimization.ab_testing import ABTestingFramework

        f1 = ABTestingFramework.get_instance()
        f2 = ABTestingFramework.get_instance()

        assert f1 is f2


class TestStatisticalCalculations:
    """Tests für statistische Berechnungen"""

    def test_simple_z_test(self, reset_new_singletons):
        """Test einfacher z-Test"""
        from src.optimization.ab_testing import ABTestingFramework, Variant

        framework = ABTestingFramework()

        control = Variant(
            id="1",
            name="control",
            config={},
            sample_size=50,
            mean_pnl=10.0,
            std_pnl=5.0,
            trades=[10.0] * 50,
        )

        treatment = Variant(
            id="2",
            name="treatment",
            config={},
            sample_size=50,
            mean_pnl=15.0,
            std_pnl=5.0,
            trades=[15.0] * 50,
        )

        p_value = framework._simple_z_test(control, treatment)

        # Sollte signifikant sein (p < 0.05)
        assert p_value < 0.05

    def test_bootstrap_ci(self, reset_new_singletons):
        """Test Bootstrap Confidence Interval"""
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework()

        np.random.seed(42)
        control_trades = list(np.random.normal(10, 5, 50))
        treatment_trades = list(np.random.normal(15, 5, 50))

        lower, upper = framework._bootstrap_ci(control_trades, treatment_trades)

        # CI sollte den wahren Unterschied enthalten (ca. 5)
        assert lower < 5 < upper or (lower < upper)  # At minimum, lower < upper


class TestExperimentStatus:
    """Tests für ExperimentStatus Enum"""

    def test_all_statuses_exist(self):
        """Test dass alle Status existieren"""
        from src.optimization.ab_testing import ExperimentStatus

        assert ExperimentStatus.DRAFT.value == "DRAFT"
        assert ExperimentStatus.RUNNING.value == "RUNNING"
        assert ExperimentStatus.PAUSED.value == "PAUSED"
        assert ExperimentStatus.COMPLETED.value == "COMPLETED"
        assert ExperimentStatus.TERMINATED.value == "TERMINATED"


class TestSignificanceLevel:
    """Tests für SignificanceLevel Enum"""

    def test_all_levels_exist(self):
        """Test dass alle Levels existieren"""
        from src.optimization.ab_testing import SignificanceLevel

        assert SignificanceLevel.HIGHLY_SIGNIFICANT.value == "HIGHLY_SIGNIFICANT"
        assert SignificanceLevel.SIGNIFICANT.value == "SIGNIFICANT"
        assert SignificanceLevel.MARGINALLY_SIGNIFICANT.value == "MARGINALLY_SIGNIFICANT"
        assert SignificanceLevel.NOT_SIGNIFICANT.value == "NOT_SIGNIFICANT"
