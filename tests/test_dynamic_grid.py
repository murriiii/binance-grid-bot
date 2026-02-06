"""
Tests für DynamicGridStrategy
"""

from unittest.mock import MagicMock, patch

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
        should_recalc, _reason = strategy.should_recalculate_grids(
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


class TestCalculateDynamicRange:
    """Tests for calculate_dynamic_range() — ATR-based range bridge."""

    def _make_ohlcv(self, n=200, base_price=100.0, volatility=0.02):
        """Generate synthetic OHLCV data."""
        np.random.seed(42)
        close = base_price * np.exp(np.cumsum(np.random.normal(0, volatility, n)))
        high = close * (1 + np.abs(np.random.normal(0, volatility / 2, n)))
        low = close * (1 - np.abs(np.random.normal(0, volatility / 2, n)))
        return {"close": close, "high": high, "low": low, "volume": np.ones(n) * 1e6}

    def test_returns_sensible_range(self, reset_new_singletons):
        """Dynamic range should be a reasonable percentage."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        ohlcv = self._make_ohlcv()

        with patch.object(strategy, "_fetch_ohlcv", return_value=ohlcv):
            range_pct, meta = strategy.calculate_dynamic_range(
                "BTCUSDT", current_price=100.0, base_range_pct=5.0
            )

        assert 1.0 <= range_pct <= 15.0
        assert not meta["fallback"]
        assert "atr_pct" in meta
        assert "volatility_regime" in meta
        assert "trend" in meta

    def test_fallback_on_no_ohlcv(self, reset_new_singletons):
        """Should return base_range_pct when OHLCV unavailable."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()

        with patch.object(strategy, "_fetch_ohlcv", return_value=None):
            range_pct, meta = strategy.calculate_dynamic_range("BTCUSDT", base_range_pct=7.0)

        assert range_pct == 7.0
        assert meta["fallback"] is True

    def test_fallback_on_exception(self, reset_new_singletons):
        """Should return base_range_pct when an exception occurs."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()

        with patch.object(strategy, "_fetch_ohlcv", side_effect=RuntimeError("API down")):
            range_pct, meta = strategy.calculate_dynamic_range("BTCUSDT", base_range_pct=5.0)

        assert range_pct == 5.0
        assert meta["fallback"] is True

    def test_range_clamped_low(self, reset_new_singletons):
        """Range should never go below 1.0%."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        # Very low volatility data
        ohlcv = self._make_ohlcv(volatility=0.001)

        with patch.object(strategy, "_fetch_ohlcv", return_value=ohlcv):
            range_pct, _ = strategy.calculate_dynamic_range(
                "BTCUSDT", current_price=100.0, base_range_pct=1.0
            )

        assert range_pct >= 1.0

    def test_range_clamped_high(self, reset_new_singletons):
        """Range should never exceed 15.0%."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        # Very high volatility data
        ohlcv = self._make_ohlcv(volatility=0.15)

        with patch.object(strategy, "_fetch_ohlcv", return_value=ohlcv):
            range_pct, _ = strategy.calculate_dynamic_range(
                "BTCUSDT", current_price=100.0, base_range_pct=15.0
            )

        assert range_pct <= 15.0

    def test_sideways_regime_tighter(self, reset_new_singletons):
        """SIDEWAYS regime should produce tighter range than BEAR."""
        from src.strategies.dynamic_grid import DynamicGridStrategy

        strategy = DynamicGridStrategy()
        ohlcv = self._make_ohlcv()

        with patch.object(strategy, "_fetch_ohlcv", return_value=ohlcv):
            sideways_pct, _ = strategy.calculate_dynamic_range(
                "BTCUSDT", current_price=100.0, base_range_pct=5.0, regime="SIDEWAYS"
            )
            bear_pct, _ = strategy.calculate_dynamic_range(
                "BTCUSDT", current_price=100.0, base_range_pct=5.0, regime="BEAR"
            )

        assert sideways_pct <= bear_pct


class TestHybridOrchestratorGridRebuild:
    """Tests for grid rebuild logic in HybridOrchestrator."""

    def _make_orchestrator(self):
        """Create a minimal HybridOrchestrator for testing."""
        from src.core.hybrid_config import HybridConfig
        from src.core.hybrid_orchestrator import HybridOrchestrator, SymbolState

        config = HybridConfig(
            total_investment=1000,
            max_symbols=3,
            num_grids=5,
            grid_range_percent=5.0,
        )
        mock_client = MagicMock()
        mock_client.testnet = True
        orch = HybridOrchestrator(config, client=mock_client)
        return orch, mock_client, SymbolState

    @patch("src.core.hybrid_orchestrator.TelegramNotifier")
    def test_should_rebuild_grid_no_bot(self, _tg, reset_new_singletons):
        """No rebuild needed when no grid bot exists."""
        orch, _, SymbolState = self._make_orchestrator()
        state = SymbolState("BTCUSDT")
        assert orch._should_rebuild_grid(state) is False

    @patch("src.core.hybrid_orchestrator.TelegramNotifier")
    def test_should_rebuild_grid_price_outside(self, _tg, reset_new_singletons):
        """Rebuild when price is outside grid range."""
        from decimal import Decimal

        orch, mock_client, SymbolState = self._make_orchestrator()
        state = SymbolState("BTCUSDT")

        # Fake grid bot with strategy
        mock_bot = MagicMock()
        mock_bot.strategy.lower_price = Decimal("95.0")
        mock_bot.strategy.upper_price = Decimal("105.0")
        state.grid_bot = mock_bot

        # Price far below range
        mock_client.get_current_price.return_value = 90.0
        assert orch._should_rebuild_grid(state) is True

    @patch("src.core.hybrid_orchestrator.TelegramNotifier")
    def test_should_rebuild_grid_price_near_edge(self, _tg, reset_new_singletons):
        """Rebuild when price approaches grid edge (within 10% margin)."""
        from decimal import Decimal

        orch, mock_client, SymbolState = self._make_orchestrator()
        state = SymbolState("BTCUSDT")

        mock_bot = MagicMock()
        mock_bot.strategy.lower_price = Decimal("95.0")
        mock_bot.strategy.upper_price = Decimal("105.0")
        state.grid_bot = mock_bot

        # Price near lower edge (within 10% of range)
        mock_client.get_current_price.return_value = 95.5  # 0.5 from lower, margin=1.0
        assert orch._should_rebuild_grid(state) is True

    @patch("src.core.hybrid_orchestrator.TelegramNotifier")
    def test_should_not_rebuild_grid_price_center(self, _tg, reset_new_singletons):
        """No rebuild when price is in the center of the grid."""
        from decimal import Decimal

        orch, mock_client, SymbolState = self._make_orchestrator()
        state = SymbolState("BTCUSDT")

        mock_bot = MagicMock()
        mock_bot.strategy.lower_price = Decimal("95.0")
        mock_bot.strategy.upper_price = Decimal("105.0")
        state.grid_bot = mock_bot

        mock_client.get_current_price.return_value = 100.0
        assert orch._should_rebuild_grid(state) is False
