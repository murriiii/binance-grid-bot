"""
Dynamic Grid Strategy - Volatilitäts-adaptive Grid-Abstände

Statt fixer Grid-Abstände passt diese Strategie die Grids dynamisch an:
1. ATR (Average True Range) für Volatilität
2. Trend-Richtung für asymmetrische Grids
3. Markt-Regime für Anzahl der Grids
4. Support/Resistance Levels

Features:
- ATR-basierte Grid-Spacing
- Asymmetrische Grids (mehr auf Trendseite)
- Dynamische Grid-Anzahl basierend auf Volatilität
- Support/Resistance als Grid-Levels
- Regime-adaptive Parameter
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from dotenv import load_dotenv

from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

# HTTP Client für Preisdaten
try:
    from src.api.http_client import get_http_client
except ImportError:
    get_http_client = None


class TrendDirection(Enum):
    """Trend-Richtung"""

    STRONG_UP = "STRONG_UP"
    UP = "UP"
    NEUTRAL = "NEUTRAL"
    DOWN = "DOWN"
    STRONG_DOWN = "STRONG_DOWN"


class GridType(Enum):
    """Grid-Typ"""

    SYMMETRIC = "SYMMETRIC"  # Gleiche Abstände oben/unten
    BULLISH = "BULLISH"  # Mehr Grids oberhalb
    BEARISH = "BEARISH"  # Mehr Grids unterhalb
    ADAPTIVE = "ADAPTIVE"  # Basierend auf Support/Resistance


@dataclass
class GridLevel:
    """Ein einzelnes Grid-Level"""

    price: float
    level_type: str  # BUY, SELL, NEUTRAL
    distance_from_current: float  # Prozentuale Distanz
    is_support: bool = False
    is_resistance: bool = False
    priority: int = 0  # Höher = wichtiger


@dataclass
class DynamicGridConfig:
    """Konfiguration für dynamische Grids"""

    # Basis-Parameter
    num_grids: int
    grid_spacing_pct: float  # Basis-Spacing

    # ATR-basierte Anpassung
    atr_multiplier: float
    volatility_adjustment: float

    # Asymmetrie
    grid_type: GridType
    upside_ratio: float  # Anteil der Grids oberhalb (0.3-0.7)

    # Grenzen
    min_spacing_pct: float
    max_spacing_pct: float
    total_range_pct: float

    # Support/Resistance
    sr_levels: list[float] = field(default_factory=list)


@dataclass
class DynamicGridResult:
    """Ergebnis der Grid-Berechnung"""

    grid_levels: list[GridLevel]
    config: DynamicGridConfig
    current_price: float

    # Statistiken
    total_range_pct: float
    avg_spacing_pct: float
    num_buy_levels: int
    num_sell_levels: int

    # Kontext
    atr_14: float
    trend: TrendDirection
    regime: str | None


# Konfiguration
DEFAULT_NUM_GRIDS = 10
DEFAULT_SPACING_PCT = 0.02  # 2%
ATR_PERIOD = 14
MIN_SPACING_PCT = 0.005  # 0.5%
MAX_SPACING_PCT = 0.10  # 10%


class DynamicGridStrategy(SingletonMixin):
    """
    Erstellt dynamische, volatilitäts-adaptive Grids.

    Features:
    1. ATR-basierte Abstände
    2. Trend-sensitive Asymmetrie
    3. Support/Resistance Integration
    4. Regime-aware Anpassungen
    """

    def __init__(self):
        self.conn = None
        self.http = get_http_client() if get_http_client else None
        self._connect_db()

        # Cache with max size to prevent memory leak (B6)
        self._price_cache: dict[str, tuple[datetime, dict]] = {}
        self._max_cache_size: int = 50

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.debug("DynamicGridStrategy: DB verbunden")
        except Exception as e:
            logger.error(f"DynamicGridStrategy: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # VOLATILITY CALCULATION
    # ═══════════════════════════════════════════════════════════════

    def calculate_atr(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = ATR_PERIOD,
    ) -> float:
        """
        Berechne Average True Range.

        True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        ATR = EMA/SMA von True Range
        """
        if len(close) < period + 1:
            # Fallback: Einfache Range
            return float(np.mean(high - low))

        true_ranges = []

        for i in range(1, len(close)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
            true_ranges.append(tr)

        # Einfacher Moving Average für ATR
        atr = np.mean(true_ranges[-period:])

        return float(atr)

    def calculate_atr_pct(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = ATR_PERIOD,
    ) -> float:
        """Berechne ATR als Prozentsatz des Preises"""
        atr = self.calculate_atr(high, low, close, period)
        current_price = close[-1] if len(close) > 0 else 1.0
        return atr / current_price

    def calculate_volatility_regime(
        self, atr_pct: float, historical_atr_pcts: list[float] | None = None
    ) -> str:
        """
        Bestimme Volatilitäts-Regime.

        Returns: LOW, NORMAL, HIGH, EXTREME
        """
        if historical_atr_pcts and len(historical_atr_pcts) >= 30:
            percentile = np.percentile(historical_atr_pcts, [25, 50, 75])

            if atr_pct < percentile[0]:
                return "LOW"
            elif atr_pct < percentile[1]:
                return "NORMAL"
            elif atr_pct < percentile[2]:
                return "HIGH"
            else:
                return "EXTREME"
        # Fallback: Absolute Schwellenwerte (für Crypto)
        elif atr_pct < 0.02:
            return "LOW"
        elif atr_pct < 0.04:
            return "NORMAL"
        elif atr_pct < 0.06:
            return "HIGH"
        else:
            return "EXTREME"

    # ═══════════════════════════════════════════════════════════════
    # TREND DETECTION
    # ═══════════════════════════════════════════════════════════════

    def detect_trend(
        self,
        close: np.ndarray,
        short_period: int = 10,
        long_period: int = 50,
    ) -> TrendDirection:
        """
        Erkenne Trend-Richtung basierend auf EMAs.
        """
        if len(close) < long_period:
            return TrendDirection.NEUTRAL

        # EMAs berechnen
        ema_short = self._ema(close, short_period)
        ema_long = self._ema(close, long_period)

        # Aktuelle Werte
        current_short = ema_short[-1]
        current_long = ema_long[-1]
        current_price = close[-1]

        # Trend-Stärke
        ema_diff_pct = (current_short - current_long) / current_long

        # Price vs EMA
        price_vs_short = (current_price - current_short) / current_short

        # Kombinierte Analyse
        if ema_diff_pct > 0.03 and price_vs_short > 0.01:
            return TrendDirection.STRONG_UP
        elif ema_diff_pct > 0.01:
            return TrendDirection.UP
        elif ema_diff_pct < -0.03 and price_vs_short < -0.01:
            return TrendDirection.STRONG_DOWN
        elif ema_diff_pct < -0.01:
            return TrendDirection.DOWN
        else:
            return TrendDirection.NEUTRAL

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average"""
        if len(data) < period:
            return data

        multiplier = 2 / (period + 1)
        ema = np.zeros(len(data))
        ema[period - 1] = np.mean(data[:period])

        for i in range(period, len(data)):
            ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1]

        ema[: period - 1] = data[: period - 1]  # Fill initial values
        return ema

    # ═══════════════════════════════════════════════════════════════
    # SUPPORT/RESISTANCE DETECTION
    # ═══════════════════════════════════════════════════════════════

    def find_support_resistance(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        num_levels: int = 5,
        lookback: int = 100,
    ) -> tuple[list[float], list[float]]:
        """
        Finde Support und Resistance Levels.

        Methode: Pivot Points und lokale Extrema
        """
        if len(close) < lookback:
            return [], []

        prices = close[-lookback:]
        highs = high[-lookback:]
        lows = low[-lookback:]

        supports = []
        resistances = []

        # Finde lokale Minima (Support)
        for i in range(2, len(lows) - 2):
            is_local_min = (
                lows[i] < lows[i - 1]
                and lows[i] < lows[i - 2]
                and lows[i] < lows[i + 1]
                and lows[i] < lows[i + 2]
            )
            if is_local_min:
                supports.append(float(lows[i]))

        # Finde lokale Maxima (Resistance)
        for i in range(2, len(highs) - 2):
            is_local_max = (
                highs[i] > highs[i - 1]
                and highs[i] > highs[i - 2]
                and highs[i] > highs[i + 1]
                and highs[i] > highs[i + 2]
            )
            if is_local_max:
                resistances.append(float(highs[i]))

        # Cluster nahe Levels zusammen
        supports = self._cluster_levels(supports, tolerance=0.005)
        resistances = self._cluster_levels(resistances, tolerance=0.005)

        # Sortiere und limitiere
        supports = sorted(supports, reverse=True)[:num_levels]
        resistances = sorted(resistances)[:num_levels]

        return supports, resistances

    def _cluster_levels(self, levels: list[float], tolerance: float = 0.005) -> list[float]:
        """Clustere nahe Levels zusammen"""
        if not levels:
            return []

        sorted_levels = sorted(levels)
        clustered = []
        current_cluster = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            if (level - current_cluster[-1]) / current_cluster[-1] < tolerance:
                current_cluster.append(level)
            else:
                # Speichere Durchschnitt des Clusters
                clustered.append(np.mean(current_cluster))
                current_cluster = [level]

        # Letzter Cluster
        clustered.append(np.mean(current_cluster))

        return clustered

    # ═══════════════════════════════════════════════════════════════
    # GRID CALCULATION
    # ═══════════════════════════════════════════════════════════════

    def calculate_dynamic_grids(
        self,
        symbol: str,
        current_price: float | None = None,
        num_grids: int = DEFAULT_NUM_GRIDS,
        base_spacing_pct: float = DEFAULT_SPACING_PCT,
        regime: str | None = None,
        use_sr_levels: bool = True,
    ) -> DynamicGridResult:
        """
        Berechne dynamische Grid-Levels.

        Args:
            symbol: Trading-Paar
            current_price: Aktueller Preis (oder aus API holen)
            num_grids: Basis-Anzahl Grids
            base_spacing_pct: Basis-Abstand
            regime: Markt-Regime (BULL, BEAR, SIDEWAYS)
            use_sr_levels: Support/Resistance einbeziehen

        Returns:
            DynamicGridResult mit berechneten Levels
        """
        # 1. Hole Marktdaten
        ohlcv = self._fetch_ohlcv(symbol, "1h", 200)

        if not ohlcv:
            # Fallback: Einfache symmetrische Grids
            return self._create_simple_grids(current_price or 0, num_grids, base_spacing_pct)

        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        if current_price is None:
            current_price = float(close[-1])

        # 2. Berechne ATR
        atr_pct = self.calculate_atr_pct(high, low, close)

        # 3. Erkenne Trend
        trend = self.detect_trend(close)

        # 4. Volatilitäts-angepasstes Spacing
        adjusted_spacing = self._calculate_adjusted_spacing(base_spacing_pct, atr_pct, regime)

        # 5. Grid-Typ basierend auf Trend
        grid_type, upside_ratio = self._determine_grid_type(trend, regime)

        # 6. Support/Resistance Levels
        supports, resistances = [], []
        if use_sr_levels:
            supports, resistances = self.find_support_resistance(high, low, close)

        # 7. Berechne Grid-Levels
        config = DynamicGridConfig(
            num_grids=num_grids,
            grid_spacing_pct=adjusted_spacing,
            atr_multiplier=atr_pct / base_spacing_pct if base_spacing_pct > 0 else 1.0,
            volatility_adjustment=1.0,
            grid_type=grid_type,
            upside_ratio=upside_ratio,
            min_spacing_pct=MIN_SPACING_PCT,
            max_spacing_pct=MAX_SPACING_PCT,
            total_range_pct=adjusted_spacing * num_grids,
            sr_levels=supports + resistances,
        )

        grid_levels = self._generate_grid_levels(current_price, config, supports, resistances)

        # 8. Ergebnis zusammenstellen
        buy_levels = [g for g in grid_levels if g.level_type == "BUY"]
        sell_levels = [g for g in grid_levels if g.level_type == "SELL"]

        return DynamicGridResult(
            grid_levels=grid_levels,
            config=config,
            current_price=current_price,
            total_range_pct=config.total_range_pct,
            avg_spacing_pct=adjusted_spacing,
            num_buy_levels=len(buy_levels),
            num_sell_levels=len(sell_levels),
            atr_14=self.calculate_atr(high, low, close),
            trend=trend,
            regime=regime,
        )

    def _calculate_adjusted_spacing(
        self,
        base_spacing: float,
        atr_pct: float,
        regime: str | None,
    ) -> float:
        """Berechne volatilitäts-angepasstes Spacing"""

        # ATR-basierte Anpassung
        # Höhere Volatilität = größere Abstände
        atr_factor = max(0.5, min(2.0, atr_pct / 0.03))  # Normalisiert auf 3%

        adjusted = base_spacing * atr_factor

        # Regime-Anpassung
        if regime:
            regime_multipliers = {
                "BULL": 1.1,  # Etwas größere Abstände (momentum)
                "BEAR": 1.1,  # Leicht größere Abstände (was 1.3 — reduced to avoid over-expansion)
                "SIDEWAYS": 0.9,  # Engere Abstände (range-bound)
                "TRANSITION": 1.0,  # Neutral (was 1.2 — reduced to avoid over-expansion)
            }
            adjusted *= regime_multipliers.get(regime.upper(), 1.0)

        # Limits
        return max(MIN_SPACING_PCT, min(MAX_SPACING_PCT, adjusted))

    def _determine_grid_type(
        self, trend: TrendDirection, regime: str | None
    ) -> tuple[GridType, float]:
        """
        Bestimme Grid-Typ und Upside-Ratio basierend auf Trend.

        Returns: (GridType, upside_ratio)
        """
        # Trend-basierte Asymmetrie
        trend_config = {
            TrendDirection.STRONG_UP: (GridType.BULLISH, 0.65),
            TrendDirection.UP: (GridType.BULLISH, 0.55),
            TrendDirection.NEUTRAL: (GridType.SYMMETRIC, 0.50),
            TrendDirection.DOWN: (GridType.BEARISH, 0.45),
            TrendDirection.STRONG_DOWN: (GridType.BEARISH, 0.35),
        }

        grid_type, upside_ratio = trend_config.get(trend, (GridType.SYMMETRIC, 0.50))

        # Regime-Override
        if regime:
            if regime.upper() == "BULL" and trend != TrendDirection.STRONG_DOWN:
                upside_ratio = min(0.65, upside_ratio + 0.05)
            elif regime.upper() == "BEAR" and trend != TrendDirection.STRONG_UP:
                upside_ratio = max(0.35, upside_ratio - 0.05)

        return grid_type, upside_ratio

    def _generate_grid_levels(
        self,
        current_price: float,
        config: DynamicGridConfig,
        supports: list[float],
        resistances: list[float],
    ) -> list[GridLevel]:
        """Generiere die eigentlichen Grid-Levels"""

        grid_levels = []

        # Anzahl Grids oben und unten
        num_above = int(config.num_grids * config.upside_ratio)
        num_below = config.num_grids - num_above

        # Grids unterhalb (BUY)
        for i in range(1, num_below + 1):
            price = current_price * (1 - i * config.grid_spacing_pct)
            distance = -i * config.grid_spacing_pct

            # Prüfe ob nahe Support
            is_support = any(abs(price - s) / price < 0.005 for s in supports)

            grid_levels.append(
                GridLevel(
                    price=price,
                    level_type="BUY",
                    distance_from_current=distance,
                    is_support=is_support,
                    priority=i if is_support else 0,
                )
            )

        # Grids oberhalb (SELL)
        for i in range(1, num_above + 1):
            price = current_price * (1 + i * config.grid_spacing_pct)
            distance = i * config.grid_spacing_pct

            # Prüfe ob nahe Resistance
            is_resistance = any(abs(price - r) / price < 0.005 for r in resistances)

            grid_levels.append(
                GridLevel(
                    price=price,
                    level_type="SELL",
                    distance_from_current=distance,
                    is_resistance=is_resistance,
                    priority=i if is_resistance else 0,
                )
            )

        # Sortiere nach Preis
        grid_levels.sort(key=lambda x: x.price)

        return grid_levels

    def _create_simple_grids(
        self,
        current_price: float,
        num_grids: int,
        spacing_pct: float,
    ) -> DynamicGridResult:
        """Fallback: Einfache symmetrische Grids"""

        config = DynamicGridConfig(
            num_grids=num_grids,
            grid_spacing_pct=spacing_pct,
            atr_multiplier=1.0,
            volatility_adjustment=1.0,
            grid_type=GridType.SYMMETRIC,
            upside_ratio=0.5,
            min_spacing_pct=MIN_SPACING_PCT,
            max_spacing_pct=MAX_SPACING_PCT,
            total_range_pct=spacing_pct * num_grids,
        )

        grid_levels = []
        half_grids = num_grids // 2

        for i in range(1, half_grids + 1):
            # BUY
            grid_levels.append(
                GridLevel(
                    price=current_price * (1 - i * spacing_pct),
                    level_type="BUY",
                    distance_from_current=-i * spacing_pct,
                )
            )
            # SELL
            grid_levels.append(
                GridLevel(
                    price=current_price * (1 + i * spacing_pct),
                    level_type="SELL",
                    distance_from_current=i * spacing_pct,
                )
            )

        grid_levels.sort(key=lambda x: x.price)

        return DynamicGridResult(
            grid_levels=grid_levels,
            config=config,
            current_price=current_price,
            total_range_pct=config.total_range_pct,
            avg_spacing_pct=spacing_pct,
            num_buy_levels=half_grids,
            num_sell_levels=half_grids,
            atr_14=0.0,
            trend=TrendDirection.NEUTRAL,
            regime=None,
        )

    # ═══════════════════════════════════════════════════════════════
    # DATA FETCHING
    # ═══════════════════════════════════════════════════════════════

    def _fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> dict[str, np.ndarray] | None:
        """Hole OHLCV-Daten"""

        # Check Cache
        cache_key = f"{symbol}_{timeframe}"
        now = datetime.now()
        if cache_key in self._price_cache:
            cache_time, cached_data = self._price_cache[cache_key]
            if now - cache_time < timedelta(minutes=5):
                return cached_data

        # B6: Evict expired entries to prevent memory leak
        self._evict_expired_cache()

        if not self.http:
            return None

        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": timeframe,
                "limit": limit,
            }

            response = self.http.get(url, params=params, timeout=10)

            if response:
                data = np.array(response)
                result = {
                    "open": data[:, 1].astype(float),
                    "high": data[:, 2].astype(float),
                    "low": data[:, 3].astype(float),
                    "close": data[:, 4].astype(float),
                    "volume": data[:, 5].astype(float),
                }

                # Cache with size cap
                self._price_cache[cache_key] = (now, result)

                return result

        except Exception as e:
            logger.error(f"OHLCV Fetch Fehler: {e}")

        return None

    def _evict_expired_cache(self) -> None:
        """Remove expired cache entries and cap cache size (B6)."""
        now = datetime.now()
        expired = [k for k, (t, _) in self._price_cache.items() if now - t >= timedelta(minutes=5)]
        for k in expired:
            del self._price_cache[k]

        # If still over max size, remove oldest entries
        if len(self._price_cache) > self._max_cache_size:
            sorted_keys = sorted(self._price_cache, key=lambda k: self._price_cache[k][0])
            for k in sorted_keys[: len(self._price_cache) - self._max_cache_size]:
                del self._price_cache[k]

    # ═══════════════════════════════════════════════════════════════
    # DYNAMIC RANGE (lightweight bridge for GridBot integration)
    # ═══════════════════════════════════════════════════════════════

    def calculate_dynamic_range(
        self,
        symbol: str,
        current_price: float | None = None,
        base_range_pct: float = 5.0,
        regime: str | None = None,
    ) -> tuple[float, dict]:
        """Calculate ATR-based grid_range_percent for a symbol.

        Uses real market OHLCV data to determine optimal grid range based on
        actual volatility instead of a static per-cohort percentage.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").
            current_price: Current price (fetched from OHLCV if None).
            base_range_pct: Cohort-level default range (e.g. 5.0 for 5%).
            regime: Market regime for adjustment ("BULL", "BEAR", "SIDEWAYS").

        Returns:
            (recommended_range_pct, metadata_dict).
            Falls back to base_range_pct on any error.
        """
        try:
            ohlcv = self._fetch_ohlcv(symbol, "1h", 200)
            if not ohlcv:
                return base_range_pct, {"fallback": True, "reason": "no_ohlcv"}

            close = ohlcv["close"]
            high = ohlcv["high"]
            low = ohlcv["low"]

            if current_price is None:
                current_price = float(close[-1])

            atr_pct = self.calculate_atr_pct(high, low, close)
            vol_regime = self.calculate_volatility_regime(atr_pct)
            trend = self.detect_trend(close)

            # Use existing _calculate_adjusted_spacing (expects decimal, not percent)
            adjusted_spacing = self._calculate_adjusted_spacing(
                base_range_pct / 100,
                atr_pct,
                regime,
            )

            # Convert back to percent and clamp
            recommended_range_pct = round(max(1.0, min(15.0, adjusted_spacing * 100)), 2)

            metadata = {
                "atr_pct": round(atr_pct * 100, 3),
                "volatility_regime": vol_regime,
                "trend": trend.value,
                "base_range_pct": base_range_pct,
                "recommended_range_pct": recommended_range_pct,
                "fallback": False,
            }

            return recommended_range_pct, metadata

        except Exception as e:
            logger.warning(f"Dynamic range calculation failed for {symbol}: {e}")
            return base_range_pct, {"fallback": True, "reason": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # GRID ADJUSTMENT
    # ═══════════════════════════════════════════════════════════════

    def should_recalculate_grids(
        self,
        current_grids: DynamicGridResult,
        current_price: float,
        threshold_pct: float = 0.05,
    ) -> tuple[bool, str]:
        """
        Prüfe ob Grids neu berechnet werden sollten.

        Returns: (should_recalculate, reason)
        """
        if not current_grids.grid_levels:
            return True, "No existing grids"

        # Preis außerhalb der Grid-Range?
        lowest_grid = min(g.price for g in current_grids.grid_levels)
        highest_grid = max(g.price for g in current_grids.grid_levels)

        if current_price < lowest_grid:
            return True, f"Price below grid range ({current_price:.2f} < {lowest_grid:.2f})"

        if current_price > highest_grid:
            return True, f"Price above grid range ({current_price:.2f} > {highest_grid:.2f})"

        # Preis zu weit vom Zentrum?
        center = (lowest_grid + highest_grid) / 2
        distance_from_center = abs(current_price - center) / center

        if distance_from_center > threshold_pct:
            return True, f"Price too far from center ({distance_from_center:.1%})"

        return False, "Grids are current"

    def adjust_grids_for_fills(
        self,
        current_grids: DynamicGridResult,
        filled_levels: list[float],
    ) -> list[GridLevel]:
        """
        Passe Grids nach Fills an.

        Bei gefülltem BUY → Füge SELL darüber hinzu
        Bei gefülltem SELL → Füge BUY darunter hinzu
        """
        adjusted = list(current_grids.grid_levels)

        for filled_price in filled_levels:
            # Finde den gefüllten Level
            filled_level = None
            for level in adjusted:
                if abs(level.price - filled_price) / filled_price < 0.001:
                    filled_level = level
                    break

            if not filled_level:
                continue

            if filled_level.level_type == "BUY":
                # Füge SELL darüber hinzu
                new_price = filled_price * (1 + current_grids.config.grid_spacing_pct)
                adjusted.append(
                    GridLevel(
                        price=new_price,
                        level_type="SELL",
                        distance_from_current=(new_price - current_grids.current_price)
                        / current_grids.current_price,
                    )
                )

            elif filled_level.level_type == "SELL":
                # Füge BUY darunter hinzu
                new_price = filled_price * (1 - current_grids.config.grid_spacing_pct)
                adjusted.append(
                    GridLevel(
                        price=new_price,
                        level_type="BUY",
                        distance_from_current=(new_price - current_grids.current_price)
                        / current_grids.current_price,
                    )
                )

        # Sortiere und dedupliziere
        seen_prices = set()
        unique = []
        for level in sorted(adjusted, key=lambda x: x.price):
            price_key = round(level.price, 2)
            if price_key not in seen_prices:
                seen_prices.add(price_key)
                unique.append(level)

        return unique

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_grid_config(
        self,
        symbol: str,
        result: DynamicGridResult,
        cycle_id: str | None = None,
    ):
        """Speichere Grid-Konfiguration"""
        if not self.conn:
            return

        try:
            import json

            levels_json = [
                {
                    "price": lvl.price,
                    "type": lvl.level_type,
                    "distance": lvl.distance_from_current,
                    "is_support": lvl.is_support,
                    "is_resistance": lvl.is_resistance,
                }
                for lvl in result.grid_levels
            ]

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO grid_configurations (
                        symbol, cycle_id, current_price, num_grids,
                        avg_spacing_pct, total_range_pct, trend,
                        regime, atr_14, grid_levels
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        cycle_id,
                        result.current_price,
                        len(result.grid_levels),
                        result.avg_spacing_pct,
                        result.total_range_pct,
                        result.trend.value,
                        result.regime,
                        result.atr_14,
                        json.dumps(levels_json),
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Grid Config Store Error (table may not exist): {e}")
            self.conn.rollback()

    def get_grid_history(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        """Hole Grid-Historie für Analyse"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM grid_configurations
                    WHERE symbol = %s
                    AND created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at DESC
                """,
                    (symbol, days),
                )
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.debug(f"Grid History Error: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung und leere Cache"""
        self._price_cache.clear()
        if self.conn:
            self.conn.close()
            self.conn = None
