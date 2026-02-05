"""
Tests für BayesianWeightLearner
"""


class TestBayesianWeightLearner:
    """Tests für Bayesian Signal Weight Learning"""

    def test_get_weights_default(self, reset_new_singletons):
        """Test Default-Gewichte"""
        from src.analysis.bayesian_weights import SIGNAL_NAMES, BayesianWeightLearner

        learner = BayesianWeightLearner()
        weights = learner.get_weights()

        # Alle Signale sollten vorhanden sein
        for signal in SIGNAL_NAMES:
            assert signal in weights

        # Gewichte sollten zu ~1 summieren
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_normalize_weights(self, reset_new_singletons):
        """Test Gewichts-Normalisierung"""
        from src.analysis.bayesian_weights import SIGNAL_NAMES, BayesianWeightLearner

        learner = BayesianWeightLearner()

        # Teste mit ungleichen Alphas
        alphas = {name: 10.0 + i for i, name in enumerate(SIGNAL_NAMES)}
        weights = learner._normalize_weights(alphas)

        # Sollte zu 1 summieren
        assert abs(sum(weights.values()) - 1.0) < 0.001

        # Alle Gewichte sollten zwischen MIN und MAX sein
        for w in weights.values():
            assert 0.02 <= w <= 0.30

    def test_combine_signals(self, reset_new_singletons, sample_signals):
        """Test Signal-Kombination"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner()
        combined, contributions = learner.combine_signals(sample_signals)

        # Combined sollte zwischen -1 und 1 sein
        assert -1 <= combined <= 1

        # Contributions sollten für alle Signale vorhanden sein
        assert len(contributions) == len(sample_signals)

    def test_combine_signals_extreme_bullish(self, reset_new_singletons):
        """Test Signal-Kombination bei extrem bullishen Signalen"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner()

        bullish_signals = {
            "fear_greed": 0.9,
            "rsi": 0.8,
            "macd": 0.9,
            "trend": 0.95,
            "volume": 0.7,
            "whale": 0.6,
            "sentiment": 0.8,
            "macro": 0.5,
            "ai": 0.9,
        }

        combined, _ = learner.combine_signals(bullish_signals)

        # Sollte stark positiv sein
        assert combined > 0.5

    def test_combine_signals_extreme_bearish(self, reset_new_singletons):
        """Test Signal-Kombination bei extrem bearishen Signalen"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner()

        bearish_signals = {
            "fear_greed": -0.9,
            "rsi": -0.8,
            "macd": -0.9,
            "trend": -0.95,
            "volume": -0.7,
            "whale": -0.6,
            "sentiment": -0.8,
            "macro": -0.5,
            "ai": -0.9,
        }

        combined, _ = learner.combine_signals(bearish_signals)

        # Sollte stark negativ sein
        assert combined < -0.5

    def test_signal_ranking(self, reset_new_singletons):
        """Test Signal-Ranking"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner()
        ranking = learner.get_signal_ranking()

        # Sollte nach Gewicht sortiert sein
        weights = [w for _, w in ranking]
        assert weights == sorted(weights, reverse=True)

    def test_compare_regimes(self, reset_new_singletons):
        """Test Regime-Vergleich"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner()
        comparison = learner.compare_regimes()

        # Global sollte immer vorhanden sein
        assert "GLOBAL" in comparison

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.analysis.bayesian_weights import BayesianWeightLearner

        l1 = BayesianWeightLearner.get_instance()
        l2 = BayesianWeightLearner.get_instance()

        assert l1 is l2


class TestSignalPerformance:
    """Tests für SignalPerformance Dataclass"""

    def test_signal_performance_creation(self):
        """Test SignalPerformance Erstellung"""
        from src.analysis.bayesian_weights import SignalPerformance

        perf = SignalPerformance(
            signal_name="rsi",
            total_trades=100,
            correct_predictions=65,
            accuracy=0.65,
            avg_contribution=0.12,
            correlation_with_pnl=0.45,
        )

        assert perf.signal_name == "rsi"
        assert perf.accuracy == 0.65
        assert perf.correlation_with_pnl == 0.45


class TestBayesianWeights:
    """Tests für BayesianWeights Dataclass"""

    def test_bayesian_weights_creation(self):
        """Test BayesianWeights Erstellung"""
        from datetime import datetime

        from src.analysis.bayesian_weights import BayesianWeights

        weights = BayesianWeights(
            weights={"rsi": 0.15, "macd": 0.12},
            alpha_values={"rsi": 15.0, "macd": 12.0},
            confidence=0.85,
            last_updated=datetime.now(),
            sample_size=100,
            regime="BULL",
        )

        assert weights.confidence == 0.85
        assert weights.sample_size == 100
        assert weights.regime == "BULL"
