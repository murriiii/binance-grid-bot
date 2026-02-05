"""
Tests für DivergenceDetector
"""

import numpy as np


class TestDivergenceDetector:
    """Tests für Divergence Detection"""

    def test_calculate_rsi(self, sample_ohlcv_data, reset_new_singletons):
        """Test RSI Berechnung"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        rsi = detector._calculate_rsi(sample_ohlcv_data["close"])

        # RSI sollte zwischen 0 und 100 sein
        valid_rsi = rsi[~np.isnan(rsi)]
        assert all(0 <= r <= 100 for r in valid_rsi)

    def test_calculate_macd(self, sample_ohlcv_data, reset_new_singletons):
        """Test MACD Berechnung"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        macd_line, signal_line, histogram = detector._calculate_macd(sample_ohlcv_data["close"])

        # MACD Komponenten sollten nicht leer sein
        assert len(macd_line) > 0
        assert len(signal_line) > 0
        assert len(histogram) > 0

    def test_calculate_stochastic(self, sample_ohlcv_data, reset_new_singletons):
        """Test Stochastic Berechnung"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        k, d = detector._calculate_stochastic(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        # %K und %D sollten zwischen 0 und 100 sein
        valid_k = k[k > 0]
        assert all(0 <= v <= 100 for v in valid_k)

    def test_find_peaks(self, sample_ohlcv_data, reset_new_singletons):
        """Test Peak Detection"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        peaks = detector._find_peaks(sample_ohlcv_data["close"], order=3)

        # Sollte einige Peaks finden
        assert len(peaks) > 0

        # Peaks sollten (index, value) Tuples sein
        for idx, val in peaks:
            assert isinstance(idx, int | np.integer)
            assert isinstance(val, float | np.floating)

    def test_find_troughs(self, sample_ohlcv_data, reset_new_singletons):
        """Test Trough Detection"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        troughs = detector._find_troughs(sample_ohlcv_data["close"], order=3)

        # Sollte einige Troughs finden
        assert len(troughs) > 0

    def test_divergence_strength(self, reset_new_singletons):
        """Test Divergence Strength Berechnung"""
        from src.analysis.divergence_detector import DivergenceDetector, DivergenceStrength

        detector = DivergenceDetector()

        # Starke Divergenz
        strength = detector._calculate_divergence_strength(100, 95, 70, 80)
        assert strength in [DivergenceStrength.STRONG, DivergenceStrength.MODERATE]

        # Schwache Divergenz
        strength = detector._calculate_divergence_strength(100, 99.5, 50, 50.5)
        assert strength in [DivergenceStrength.WEAK, DivergenceStrength.NONE]

    def test_empty_analysis(self, reset_new_singletons):
        """Test leere Analyse ohne Daten"""
        from src.analysis.divergence_detector import DivergenceDetector, DivergenceType

        detector = DivergenceDetector()
        analysis = detector._empty_analysis("BTCUSDT", "1h")

        assert analysis.symbol == "BTCUSDT"
        assert analysis.divergence_count == 0
        assert analysis.dominant_type == DivergenceType.NONE

    def test_aggregate_divergences_empty(self, reset_new_singletons):
        """Test Aggregation ohne Divergenzen"""
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector()
        analysis = detector._aggregate_divergences("BTCUSDT", "1h", [])

        assert analysis.bullish_signal == 0.0
        assert analysis.bearish_signal == 0.0
        assert analysis.net_signal == 0.0

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.analysis.divergence_detector import DivergenceDetector

        d1 = DivergenceDetector.get_instance()
        d2 = DivergenceDetector.get_instance()

        assert d1 is d2


class TestDivergenceType:
    """Tests für DivergenceType Enum"""

    def test_all_types_exist(self):
        """Test dass alle Typen existieren"""
        from src.analysis.divergence_detector import DivergenceType

        assert DivergenceType.BULLISH.value == "BULLISH"
        assert DivergenceType.BEARISH.value == "BEARISH"
        assert DivergenceType.HIDDEN_BULLISH.value == "HIDDEN_BULLISH"
        assert DivergenceType.HIDDEN_BEARISH.value == "HIDDEN_BEARISH"
        assert DivergenceType.NONE.value == "NONE"


class TestDivergenceDataclass:
    """Tests für Divergence Dataclass"""

    def test_divergence_creation(self):
        """Test Divergence Erstellung"""
        from datetime import datetime

        from src.analysis.divergence_detector import (
            Divergence,
            DivergenceStrength,
            DivergenceType,
        )

        div = Divergence(
            indicator="RSI",
            divergence_type=DivergenceType.BULLISH,
            strength=DivergenceStrength.STRONG,
            signal_strength=0.8,
            confidence=0.9,
            price_point1=(10, 100.0),
            price_point2=(20, 95.0),
            indicator_point1=(10, 30.0),
            indicator_point2=(20, 40.0),
            lookback_periods=10,
            timestamp=datetime.now(),
        )

        assert div.indicator == "RSI"
        assert div.divergence_type == DivergenceType.BULLISH
        assert div.signal_strength == 0.8
