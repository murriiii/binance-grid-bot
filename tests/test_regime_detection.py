"""
Tests für RegimeDetector
"""


class TestMarketRegime:
    """Tests für MarketRegime Enum"""

    def test_all_regimes_exist(self):
        """Test dass alle Regimes existieren"""
        from src.analysis.regime_detection import MarketRegime

        assert MarketRegime.BULL.value == "BULL"
        assert MarketRegime.BEAR.value == "BEAR"
        assert MarketRegime.SIDEWAYS.value == "SIDEWAYS"
        assert MarketRegime.TRANSITION.value == "TRANSITION"

    def test_regime_from_string(self):
        """Test Regime aus String"""
        from src.analysis.regime_detection import MarketRegime

        assert MarketRegime("BULL") == MarketRegime.BULL
        assert MarketRegime("BEAR") == MarketRegime.BEAR


class TestRegimeState:
    """Tests für RegimeState Dataclass"""

    def test_regime_state_creation(self):
        """Test RegimeState Erstellung"""
        from src.analysis.regime_detection import MarketRegime, RegimeState

        state = RegimeState(
            current_regime=MarketRegime.BULL,
            regime_probability=0.85,
            transition_probability=0.15,
            regime_duration_days=14,
            previous_regime=MarketRegime.SIDEWAYS,
            return_7d=0.05,
            volatility_7d=0.02,
            volume_trend=0.1,
            fear_greed_avg=65.0,
            model_confidence=0.90,
        )

        assert state.current_regime == MarketRegime.BULL
        assert state.regime_probability == 0.85
        assert state.model_confidence == 0.90


class TestRegimeDetector:
    """Tests für Regime Detector"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.analysis.regime_detection import RegimeDetector

        d1 = RegimeDetector.get_instance()
        d2 = RegimeDetector.get_instance()

        assert d1 is d2

    def test_detector_initialization(self, reset_new_singletons):
        """Test Detector Initialisierung"""
        from src.analysis.regime_detection import RegimeDetector

        detector = RegimeDetector()

        assert detector is not None
        assert detector.NUM_STATES == 3

    def test_regime_mapping(self, reset_new_singletons):
        """Test Regime Mapping"""
        from src.analysis.regime_detection import MarketRegime, RegimeDetector

        detector = RegimeDetector()

        assert detector.REGIME_MAPPING[0] == MarketRegime.BULL
        assert detector.REGIME_MAPPING[1] == MarketRegime.BEAR
        assert detector.REGIME_MAPPING[2] == MarketRegime.SIDEWAYS

    def test_get_regime_adjusted_weights(self, reset_new_singletons):
        """Test Gewichts-Anpassung pro Regime"""
        from src.analysis.regime_detection import MarketRegime, RegimeDetector

        detector = RegimeDetector()

        bull_weights = detector.get_regime_adjusted_weights(MarketRegime.BULL)
        bear_weights = detector.get_regime_adjusted_weights(MarketRegime.BEAR)

        # Sollte Dictionaries sein
        assert isinstance(bull_weights, dict)
        assert isinstance(bear_weights, dict)

        # Sollte Signal-Namen enthalten
        assert "trend" in bull_weights or len(bull_weights) > 0

    def test_get_regime_trading_rules(self, reset_new_singletons):
        """Test Trading-Regeln pro Regime"""
        from src.analysis.regime_detection import MarketRegime, RegimeDetector

        detector = RegimeDetector()

        bull_rules = detector.get_regime_trading_rules(MarketRegime.BULL)
        bear_rules = detector.get_regime_trading_rules(MarketRegime.BEAR)

        # Sollte Dictionaries sein
        assert isinstance(bull_rules, dict)
        assert isinstance(bear_rules, dict)

        # Sollte mindestens einige Regeln enthalten
        assert len(bull_rules) > 0
        assert len(bear_rules) > 0
