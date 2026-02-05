"""
Tests für SignalAnalyzer
"""


class TestSignalBreakdown:
    """Tests für SignalBreakdown Dataclass"""

    def test_signal_breakdown_creation(self):
        """Test SignalBreakdown Erstellung"""
        from src.analysis.signal_analyzer import SignalBreakdown

        breakdown = SignalBreakdown(
            fear_greed_signal=0.3,
            rsi_signal=-0.2,
            macd_signal=0.5,
            trend_signal=0.4,
            volume_signal=0.1,
            whale_signal=-0.1,
            sentiment_signal=0.2,
            macro_signal=0.0,
            ai_direction_signal=0.3,
            ai_confidence=0.75,
            ai_risk_level="MEDIUM",
            playbook_alignment=0.8,
            weights={"fear_greed": 0.15, "rsi": 0.12},
            math_composite=0.25,
            ai_composite=0.35,
            final_score=0.30,
        )

        assert breakdown.fear_greed_signal == 0.3
        assert breakdown.ai_confidence == 0.75
        assert breakdown.final_score == 0.30


class TestDefaultWeights:
    """Tests für Default Signal Weights"""

    def test_weights_sum_to_one(self):
        """Test dass Gewichte zu 1 summieren"""
        from src.analysis.signal_analyzer import DEFAULT_WEIGHTS

        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_all_signals_have_weights(self):
        """Test dass alle Signale Gewichte haben"""
        from src.analysis.signal_analyzer import DEFAULT_WEIGHTS

        expected_signals = [
            "fear_greed",
            "rsi",
            "macd",
            "trend",
            "volume",
            "whale",
            "sentiment",
            "macro",
            "ai",
        ]

        for signal in expected_signals:
            assert signal in DEFAULT_WEIGHTS


class TestSignalAnalyzer:
    """Tests für Signal Analyzer"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.analysis.signal_analyzer import SignalAnalyzer

        a1 = SignalAnalyzer.get_instance()
        a2 = SignalAnalyzer.get_instance()

        assert a1 is a2

    def test_analyzer_initialization(self, reset_new_singletons):
        """Test Analyzer Initialisierung"""
        from src.analysis.signal_analyzer import SignalAnalyzer

        analyzer = SignalAnalyzer()

        # Sollte ohne Fehler initialisieren
        assert analyzer is not None
