"""
Tests für DynamicGridStrategy
"""

import numpy as np


class TestDynamicGridStrategy:
    """Tests für Dynamic Grid Strategy"""

    def test_calculate_atr(self, sample_ohlcv_data, reset_new_singletons):
        """Test ATR Berechnung"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        atr = strategy.calculate_atr(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        # ATR sollte positiv sein
        assert atr > 0

    def test_calculate_atr_pct(self, sample_ohlcv_data, reset_new_singletons):
        """Test ATR als Prozentsatz"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        atr_pct = strategy.calculate_atr_pct(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        # ATR% sollte zwischen 0 und 1 sein (0-100%)
        assert 0 < atr_pct < 1

    def test_volatility_regime(self, reset_new_singletons):
        """Test Volatilitäts-Regime Erkennung"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()

        # Verschiedene Volatilitäten testen
        assert strategy.calculate_volatility_regime(0.01) == "LOW"
        assert strategy.calculate_volatility_regime(0.03) == "NORMAL"
        assert strategy.calculate_volatility_regime(0.05) == "HIGH"
        assert strategy.calculate_volatility_regime(0.08) == "EXTREME"

    def test_detect_trend_bullish(self, reset_new_singletons):
        """Test Trend-Erkennung bei Aufwärtstrend"""
        from src.strategies.dynamic_grid import DynamicGridStrategy, TrendDirection

        strategy = DynamicGridStrategy()

        # Generiere Aufwärtstrend
        np.random.seed(42)
        n = 100
        close = 100 * np.exp(np.cumsum(np.random.normal(0.003, 0.01, n)))

        trend = strategy.detect_trend(close)

        assert trend in [TrendDirection.STRONG_UP, TrendDirection.UP]

    def test_detect_trend_bearish(self, reset_new_singletons):
        """Test Trend-Erkennung bei Abwärtstrend"""
        from src.strategies.dynamic_grid import DynamicGridStrategy, TrendDirection

        strategy = DynamicGridStrategy()

        # Generiere Abwärtstrend
        np.random.seed(42)
        n = 100
        close = 100 * np.exp(np.cumsum(np.random.normal(-0.003, 0.01, n)))

        trend = strategy.detect_trend(close)

        assert trend in [TrendDirection.STRONG_DOWN, TrendDirection.DOWN]

    def test_find_support_resistance(self, sample_ohlcv_data, reset_new_singletons):
        """Test Support/Resistance Detection"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        supports, resistances = strategy.find_support_resistance(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        # Sollte einige Levels finden
        assert isinstance(supports, list)
        assert isinstance(resistances, list)

    def test_create_simple_grids(self, reset_new_singletons):
        """Test einfache Grid-Erstellung"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        result = strategy._create_simple_grids(
            current_price=100.0,
            num_grids=10,
            spacing_pct=0.02,
        )

        # Sollte Grid-Levels haben
        assert len(result.grid_levels) > 0

        # Sollte BUY und SELL Levels haben
        buy_levels = [g for g in result.grid_levels if g.level_type == "BUY"]
        sell_levels = [g for g in result.grid_levels if g.level_type == "SELL"]

        assert len(buy_levels) > 0
        assert len(sell_levels) > 0

    def test_grid_levels_sorted(self, reset_new_singletons):
        """Test dass Grid-Levels sortiert sind"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        result = strategy._create_simple_grids(
            current_price=100.0,
            num_grids=10,
            spacing_pct=0.02,
        )

        prices = [g.price for g in result.grid_levels]
        assert prices == sorted(prices)

    def test_should_recalculate_grids_price_outside(self, reset_new_singletons):
        """Test Grid-Neuberechnung bei Preis außerhalb Range"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        current_grids = strategy._create_simple_grids(100.0, 10, 0.02)

        # Preis weit unter Grid
        should_recalc, reason = strategy.should_recalculate_grids(current_grids, current_price=80.0)

        assert should_recalc is True
        assert "below" in reason.lower()

    def test_should_recalculate_grids_price_inside(self, reset_new_singletons):
        """Test keine Neuberechnung bei Preis innerhalb Range"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        current_grids = strategy._create_simple_grids(100.0, 10, 0.02)

        # Preis nah am Zentrum
        should_recalc, reason = strategy.should_recalculate_grids(
            current_grids, current_price=100.5
        )

        assert should_recalc is False

    def test_determine_grid_type(self, reset_new_singletons):
        """Test Grid-Typ Bestimmung"""
        from src.strategies.dynamic_grid import (
            DynamicGridStrategy,
            GridType,
            TrendDirection,
        )

        strategy = DynamicGridStrategy()

        # Bull Trend sollte bullisches Grid ergeben
        grid_type, upside_ratio = strategy._determine_grid_type(TrendDirection.STRONG_UP, None)

        assert grid_type == GridType.BULLISH
        assert upside_ratio > 0.5  # Mehr Grids oben

        # Bear Trend sollte bärisches Grid ergeben
        grid_type, upside_ratio = strategy._determine_grid_type(TrendDirection.STRONG_DOWN, None)

        assert grid_type == GridType.BEARISH
        assert upside_ratio < 0.5  # Mehr Grids unten

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        s1 = DynamicGridStrategy.get_instance()
        s2 = DynamicGridStrategy.get_instance()

        assert s1 is s2


class TestTrendDirection:
    """Tests für TrendDirection Enum"""

    def test_all_directions_exist(self):
        """Test dass alle Richtungen existieren"""
        from src.strategies.dynamic_grid import TrendDirection

        assert TrendDirection.STRONG_UP.value == "STRONG_UP"
        assert TrendDirection.UP.value == "UP"
        assert TrendDirection.NEUTRAL.value == "NEUTRAL"
        assert TrendDirection.DOWN.value == "DOWN"
        assert TrendDirection.STRONG_DOWN.value == "STRONG_DOWN"


class TestGridType:
    """Tests für GridType Enum"""

    def test_all_types_exist(self):
        """Test dass alle Typen existieren"""
        from src.strategies.dynamic_grid import GridType

        assert GridType.SYMMETRIC.value == "SYMMETRIC"
        assert GridType.BULLISH.value == "BULLISH"
        assert GridType.BEARISH.value == "BEARISH"
        assert GridType.ADAPTIVE.value == "ADAPTIVE"


class TestGridLevel:
    """Tests für GridLevel Dataclass"""

    def test_grid_level_creation(self):
        """Test GridLevel Erstellung"""
        from src.strategies.dynamic_grid import GridLevel

        level = GridLevel(
            price=100.0,
            level_type="BUY",
            distance_from_current=-0.02,
            is_support=True,
            is_resistance=False,
            priority=1,
        )

        assert level.price == 100.0
        assert level.level_type == "BUY"
        assert level.is_support is True
