"""
Divergence Detector - Erkennt Divergenzen zwischen Preis und Indikatoren

Divergenzen sind eines der stärksten TA-Signale:
- Bullish Divergence: Preis macht tieferes Tief, Indikator macht höheres Tief → Umkehr nach oben
- Bearish Divergence: Preis macht höheres Hoch, Indikator macht tieferes Hoch → Umkehr nach unten

Unterstützte Indikatoren:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Stochastic
- OBV (On-Balance Volume)
- MFI (Money Flow Index)

Hidden Divergences (Trend-Fortsetzung):
- Hidden Bullish: Preis macht höheres Tief, Indikator macht tieferes Tief → Aufwärtstrend setzt fort
- Hidden Bearish: Preis macht tieferes Hoch, Indikator macht höheres Hoch → Abwärtstrend setzt fort
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
from dotenv import load_dotenv

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


class DivergenceType(Enum):
    """Typ der Divergenz"""

    BULLISH = "BULLISH"  # Reguläre bullische Divergenz
    BEARISH = "BEARISH"  # Reguläre bärische Divergenz
    HIDDEN_BULLISH = "HIDDEN_BULLISH"  # Hidden bullisch (Trend-Fortsetzung)
    HIDDEN_BEARISH = "HIDDEN_BEARISH"  # Hidden bärisch (Trend-Fortsetzung)
    NONE = "NONE"


class DivergenceStrength(Enum):
    """Stärke der Divergenz"""

    STRONG = "STRONG"  # Klare Divergenz, große Abweichung
    MODERATE = "MODERATE"  # Mittlere Divergenz
    WEAK = "WEAK"  # Schwache Divergenz
    NONE = "NONE"


@dataclass
class Divergence:
    """Eine erkannte Divergenz"""

    indicator: str  # RSI, MACD, etc.
    divergence_type: DivergenceType
    strength: DivergenceStrength
    signal_strength: float  # -1 bis +1
    confidence: float  # 0 bis 1

    # Details
    price_point1: tuple[int, float]  # (index, price) - erster Extrempunkt
    price_point2: tuple[int, float]  # (index, price) - zweiter Extrempunkt
    indicator_point1: tuple[int, float]  # (index, value)
    indicator_point2: tuple[int, float]  # (index, value)

    # Kontext
    lookback_periods: int
    timestamp: datetime | None = None


@dataclass
class DivergenceAnalysis:
    """Gesamtanalyse aller Divergenzen"""

    symbol: str
    timestamp: datetime
    timeframe: str

    # Gefundene Divergenzen
    divergences: list[Divergence]

    # Aggregierte Signals
    bullish_signal: float  # 0 bis 1
    bearish_signal: float  # 0 bis 1
    net_signal: float  # -1 bis +1

    # Consensus
    divergence_count: int
    dominant_type: DivergenceType
    average_confidence: float


# Konfiguration
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
STOCH_PERIOD = 14
MFI_PERIOD = 14

# Mindest-Lookback für Divergenz-Erkennung
MIN_LOOKBACK = 10
DEFAULT_LOOKBACK = 30


class DivergenceDetector:
    """
    Erkennt Divergenzen zwischen Preis und technischen Indikatoren.

    Features:
    1. Multi-Indikator Divergenz-Erkennung
    2. Hidden Divergenzen für Trend-Fortsetzung
    3. Stärke-Bewertung basierend auf Abweichung
    4. Konsens-Signal aus mehreren Divergenzen
    """

    _instance = None

    def __init__(self):
        self.conn = None
        self.http = get_http_client() if get_http_client else None
        self._connect_db()

    @classmethod
    def get_instance(cls) -> "DivergenceDetector":
        """Singleton Pattern"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset für Tests"""
        cls._instance = None

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.debug("DivergenceDetector: DB verbunden")
        except Exception as e:
            logger.error(f"DivergenceDetector: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # INDICATOR CALCULATIONS
    # ═══════════════════════════════════════════════════════════════

    def _calculate_rsi(self, prices: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
        """Berechne RSI"""
        if len(prices) < period + 1:
            return np.array([])

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.zeros(len(deltas))
        avg_loss = np.zeros(len(deltas))

        # Initialer SMA
        avg_gain[period - 1] = np.mean(gains[:period])
        avg_loss[period - 1] = np.mean(losses[:period])

        # EMA-Style Smoothing
        for i in range(period, len(deltas)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))

        # Padding für gleiche Länge
        result = np.full(len(prices), np.nan)
        result[period:] = rsi[period - 1 :]

        return result

    def _calculate_macd(
        self,
        prices: np.ndarray,
        fast: int = MACD_FAST,
        slow: int = MACD_SLOW,
        signal: int = MACD_SIGNAL,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Berechne MACD, Signal Line, Histogram"""
        if len(prices) < slow + signal:
            empty = np.array([])
            return empty, empty, empty

        # EMAs
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)

        # MACD Line
        macd_line = ema_fast - ema_slow

        # Signal Line
        signal_line = self._ema(macd_line, signal)

        # Histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _calculate_stochastic(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = STOCH_PERIOD,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Berechne Stochastic %K und %D"""
        if len(close) < period:
            empty = np.array([])
            return empty, empty

        k = np.zeros(len(close))

        for i in range(period - 1, len(close)):
            lowest_low = np.min(low[i - period + 1 : i + 1])
            highest_high = np.max(high[i - period + 1 : i + 1])

            if highest_high != lowest_low:
                k[i] = 100 * (close[i] - lowest_low) / (highest_high - lowest_low)
            else:
                k[i] = 50

        # %D ist 3-Perioden SMA von %K
        d = self._sma(k, 3)

        return k, d

    def _calculate_mfi(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        period: int = MFI_PERIOD,
    ) -> np.ndarray:
        """Berechne Money Flow Index"""
        if len(close) < period + 1:
            return np.array([])

        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * volume

        positive_flow = np.zeros(len(close))
        negative_flow = np.zeros(len(close))

        for i in range(1, len(close)):
            if typical_price[i] > typical_price[i - 1]:
                positive_flow[i] = raw_money_flow[i]
            elif typical_price[i] < typical_price[i - 1]:
                negative_flow[i] = raw_money_flow[i]

        mfi = np.zeros(len(close))

        for i in range(period, len(close)):
            pos_sum = np.sum(positive_flow[i - period + 1 : i + 1])
            neg_sum = np.sum(negative_flow[i - period + 1 : i + 1])

            if neg_sum != 0:
                money_ratio = pos_sum / neg_sum
                mfi[i] = 100 - (100 / (1 + money_ratio))
            else:
                mfi[i] = 100

        return mfi

    def _calculate_obv(self, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """Berechne On-Balance Volume"""
        obv = np.zeros(len(close))
        obv[0] = volume[0]

        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]

        return obv

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average"""
        if len(data) < period:
            return np.full(len(data), np.nan)

        multiplier = 2 / (period + 1)
        ema = np.zeros(len(data))
        ema[period - 1] = np.mean(data[:period])

        for i in range(period, len(data)):
            ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1]

        ema[: period - 1] = np.nan
        return ema

    def _sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average"""
        if len(data) < period:
            return np.full(len(data), np.nan)

        sma = np.convolve(data, np.ones(period) / period, mode="valid")
        result = np.full(len(data), np.nan)
        result[period - 1 :] = sma
        return result

    # ═══════════════════════════════════════════════════════════════
    # PEAK/TROUGH DETECTION
    # ═══════════════════════════════════════════════════════════════

    def _find_peaks(self, data: np.ndarray, order: int = 5) -> list[tuple[int, float]]:
        """Finde lokale Hochpunkte"""
        peaks = []

        for i in range(order, len(data) - order):
            if np.isnan(data[i]):
                continue

            is_peak = True
            for j in range(1, order + 1):
                if data[i] <= data[i - j] or data[i] <= data[i + j]:
                    is_peak = False
                    break

            if is_peak:
                peaks.append((i, data[i]))

        return peaks

    def _find_troughs(self, data: np.ndarray, order: int = 5) -> list[tuple[int, float]]:
        """Finde lokale Tiefpunkte"""
        troughs = []

        for i in range(order, len(data) - order):
            if np.isnan(data[i]):
                continue

            is_trough = True
            for j in range(1, order + 1):
                if data[i] >= data[i - j] or data[i] >= data[i + j]:
                    is_trough = False
                    break

            if is_trough:
                troughs.append((i, data[i]))

        return troughs

    # ═══════════════════════════════════════════════════════════════
    # DIVERGENCE DETECTION
    # ═══════════════════════════════════════════════════════════════

    def detect_divergence(
        self,
        prices: np.ndarray,
        indicator: np.ndarray,
        indicator_name: str,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> Divergence | None:
        """
        Erkenne Divergenz zwischen Preis und Indikator.

        Args:
            prices: Close-Preise
            indicator: Indikator-Werte
            indicator_name: Name des Indikators
            lookback: Anzahl Perioden für Analyse

        Returns:
            Divergence oder None
        """
        if len(prices) < lookback or len(indicator) < lookback:
            return None

        # Nur die letzten N Perioden
        prices = prices[-lookback:]
        indicator = indicator[-lookback:]

        # Finde Extrempunkte
        price_peaks = self._find_peaks(prices)
        price_troughs = self._find_troughs(prices)
        ind_peaks = self._find_peaks(indicator)
        ind_troughs = self._find_troughs(indicator)

        # Brauchen mindestens 2 Extrempunkte
        if len(price_peaks) < 2 and len(price_troughs) < 2:
            return None

        # Prüfe Bearish Divergence (Preis höher, Indikator niedriger)
        if len(price_peaks) >= 2 and len(ind_peaks) >= 2:
            div = self._check_bearish_divergence(price_peaks[-2:], ind_peaks[-2:], indicator_name)
            if div:
                return div

        # Prüfe Bullish Divergence (Preis niedriger, Indikator höher)
        if len(price_troughs) >= 2 and len(ind_troughs) >= 2:
            div = self._check_bullish_divergence(
                price_troughs[-2:], ind_troughs[-2:], indicator_name
            )
            if div:
                return div

        # Prüfe Hidden Divergenzen
        if len(price_troughs) >= 2 and len(ind_troughs) >= 2:
            div = self._check_hidden_bullish(price_troughs[-2:], ind_troughs[-2:], indicator_name)
            if div:
                return div

        if len(price_peaks) >= 2 and len(ind_peaks) >= 2:
            div = self._check_hidden_bearish(price_peaks[-2:], ind_peaks[-2:], indicator_name)
            if div:
                return div

        return None

    def _check_bullish_divergence(
        self,
        price_troughs: list[tuple[int, float]],
        ind_troughs: list[tuple[int, float]],
        indicator_name: str,
    ) -> Divergence | None:
        """
        Bullish Divergence: Preis macht tieferes Tief, Indikator macht höheres Tief
        """
        p1, p2 = price_troughs[0], price_troughs[1]
        i1, i2 = ind_troughs[0], ind_troughs[1]

        # Preis: tieferes Tief (p2 < p1)
        # Indikator: höheres Tief (i2 > i1)
        if p2[1] < p1[1] and i2[1] > i1[1]:
            strength = self._calculate_divergence_strength(p1[1], p2[1], i1[1], i2[1])

            return Divergence(
                indicator=indicator_name,
                divergence_type=DivergenceType.BULLISH,
                strength=strength,
                signal_strength=self._strength_to_signal(strength, is_bullish=True),
                confidence=self._calculate_confidence(p1, p2, i1, i2),
                price_point1=p1,
                price_point2=p2,
                indicator_point1=i1,
                indicator_point2=i2,
                lookback_periods=p2[0] - p1[0],
                timestamp=datetime.now(),
            )

        return None

    def _check_bearish_divergence(
        self,
        price_peaks: list[tuple[int, float]],
        ind_peaks: list[tuple[int, float]],
        indicator_name: str,
    ) -> Divergence | None:
        """
        Bearish Divergence: Preis macht höheres Hoch, Indikator macht tieferes Hoch
        """
        p1, p2 = price_peaks[0], price_peaks[1]
        i1, i2 = ind_peaks[0], ind_peaks[1]

        # Preis: höheres Hoch (p2 > p1)
        # Indikator: tieferes Hoch (i2 < i1)
        if p2[1] > p1[1] and i2[1] < i1[1]:
            strength = self._calculate_divergence_strength(p1[1], p2[1], i1[1], i2[1])

            return Divergence(
                indicator=indicator_name,
                divergence_type=DivergenceType.BEARISH,
                strength=strength,
                signal_strength=self._strength_to_signal(strength, is_bullish=False),
                confidence=self._calculate_confidence(p1, p2, i1, i2),
                price_point1=p1,
                price_point2=p2,
                indicator_point1=i1,
                indicator_point2=i2,
                lookback_periods=p2[0] - p1[0],
                timestamp=datetime.now(),
            )

        return None

    def _check_hidden_bullish(
        self,
        price_troughs: list[tuple[int, float]],
        ind_troughs: list[tuple[int, float]],
        indicator_name: str,
    ) -> Divergence | None:
        """
        Hidden Bullish: Preis macht höheres Tief, Indikator macht tieferes Tief
        (Aufwärtstrend setzt sich fort)
        """
        p1, p2 = price_troughs[0], price_troughs[1]
        i1, i2 = ind_troughs[0], ind_troughs[1]

        # Preis: höheres Tief (p2 > p1)
        # Indikator: tieferes Tief (i2 < i1)
        if p2[1] > p1[1] and i2[1] < i1[1]:
            strength = self._calculate_divergence_strength(p1[1], p2[1], i1[1], i2[1])

            return Divergence(
                indicator=indicator_name,
                divergence_type=DivergenceType.HIDDEN_BULLISH,
                strength=strength,
                signal_strength=self._strength_to_signal(strength, is_bullish=True)
                * 0.7,  # Etwas schwächer
                confidence=self._calculate_confidence(p1, p2, i1, i2) * 0.8,
                price_point1=p1,
                price_point2=p2,
                indicator_point1=i1,
                indicator_point2=i2,
                lookback_periods=p2[0] - p1[0],
                timestamp=datetime.now(),
            )

        return None

    def _check_hidden_bearish(
        self,
        price_peaks: list[tuple[int, float]],
        ind_peaks: list[tuple[int, float]],
        indicator_name: str,
    ) -> Divergence | None:
        """
        Hidden Bearish: Preis macht tieferes Hoch, Indikator macht höheres Hoch
        (Abwärtstrend setzt sich fort)
        """
        p1, p2 = price_peaks[0], price_peaks[1]
        i1, i2 = ind_peaks[0], ind_peaks[1]

        # Preis: tieferes Hoch (p2 < p1)
        # Indikator: höheres Hoch (i2 > i1)
        if p2[1] < p1[1] and i2[1] > i1[1]:
            strength = self._calculate_divergence_strength(p1[1], p2[1], i1[1], i2[1])

            return Divergence(
                indicator=indicator_name,
                divergence_type=DivergenceType.HIDDEN_BEARISH,
                strength=strength,
                signal_strength=self._strength_to_signal(strength, is_bullish=False) * 0.7,
                confidence=self._calculate_confidence(p1, p2, i1, i2) * 0.8,
                price_point1=p1,
                price_point2=p2,
                indicator_point1=i1,
                indicator_point2=i2,
                lookback_periods=p2[0] - p1[0],
                timestamp=datetime.now(),
            )

        return None

    def _calculate_divergence_strength(
        self,
        price1: float,
        price2: float,
        ind1: float,
        ind2: float,
    ) -> DivergenceStrength:
        """Berechne Stärke der Divergenz"""
        # Prozentuale Abweichung
        price_change = abs((price2 - price1) / price1) if price1 != 0 else 0
        ind_change = abs((ind2 - ind1) / ind1) if ind1 != 0 else 0

        # Kombinierte Abweichung
        combined = (price_change + ind_change) / 2

        if combined > 0.05:  # >5%
            return DivergenceStrength.STRONG
        elif combined > 0.02:  # >2%
            return DivergenceStrength.MODERATE
        elif combined > 0.005:  # >0.5%
            return DivergenceStrength.WEAK
        else:
            return DivergenceStrength.NONE

    def _strength_to_signal(self, strength: DivergenceStrength, is_bullish: bool) -> float:
        """Konvertiere Stärke zu Signal (-1 bis +1)"""
        strength_map = {
            DivergenceStrength.STRONG: 0.9,
            DivergenceStrength.MODERATE: 0.6,
            DivergenceStrength.WEAK: 0.3,
            DivergenceStrength.NONE: 0.0,
        }

        value = strength_map.get(strength, 0.0)
        return value if is_bullish else -value

    def _calculate_confidence(
        self,
        p1: tuple[int, float],
        p2: tuple[int, float],
        i1: tuple[int, float],
        i2: tuple[int, float],
    ) -> float:
        """
        Berechne Confidence basierend auf:
        - Zeitliche Nähe der Extrempunkte
        - Klarheit der Divergenz
        """
        # Zeitliche Nähe (5-20 Perioden ist ideal)
        time_diff = abs(p2[0] - p1[0])
        time_confidence = 1.0 if 5 <= time_diff <= 20 else 0.7

        # Preis und Indikator sollten ähnliche Zeitpunkte haben
        price_ind_sync = 1.0 - min(1.0, abs(p1[0] - i1[0]) / 10)

        return time_confidence * price_ind_sync

    # ═══════════════════════════════════════════════════════════════
    # FULL ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def analyze(
        self,
        symbol: str,
        timeframe: str = "1h",
        lookback: int = DEFAULT_LOOKBACK,
        ohlcv_data: dict[str, np.ndarray] | None = None,
    ) -> DivergenceAnalysis:
        """
        Führe vollständige Divergenz-Analyse durch.

        Args:
            symbol: Trading-Paar (z.B. "BTCUSDT")
            timeframe: Zeitrahmen
            lookback: Analyse-Perioden
            ohlcv_data: Optional vorgefertigte OHLCV-Daten

        Returns:
            DivergenceAnalysis mit allen gefundenen Divergenzen
        """
        if ohlcv_data is None:
            ohlcv_data = self._fetch_ohlcv(symbol, timeframe, lookback + 50)

        if not ohlcv_data or "close" not in ohlcv_data:
            return self._empty_analysis(symbol, timeframe)

        close = ohlcv_data["close"]
        high = ohlcv_data.get("high", close)
        low = ohlcv_data.get("low", close)
        volume = ohlcv_data.get("volume", np.ones_like(close))

        divergences = []

        # RSI Divergence
        rsi = self._calculate_rsi(close)
        if len(rsi) > 0:
            div = self.detect_divergence(close, rsi, "RSI", lookback)
            if div:
                divergences.append(div)

        # MACD Divergence (Histogram)
        _macd_line, _, histogram = self._calculate_macd(close)
        if len(histogram) > 0:
            div = self.detect_divergence(close, histogram, "MACD", lookback)
            if div:
                divergences.append(div)

        # Stochastic Divergence
        stoch_k, _ = self._calculate_stochastic(high, low, close)
        if len(stoch_k) > 0:
            div = self.detect_divergence(close, stoch_k, "STOCH", lookback)
            if div:
                divergences.append(div)

        # MFI Divergence
        mfi = self._calculate_mfi(high, low, close, volume)
        if len(mfi) > 0:
            div = self.detect_divergence(close, mfi, "MFI", lookback)
            if div:
                divergences.append(div)

        # OBV Divergence
        obv = self._calculate_obv(close, volume)
        if len(obv) > 0:
            # Normalisiere OBV für Vergleichbarkeit
            obv_norm = (obv - np.nanmin(obv)) / (np.nanmax(obv) - np.nanmin(obv) + 1e-10) * 100
            div = self.detect_divergence(close, obv_norm, "OBV", lookback)
            if div:
                divergences.append(div)

        # Aggregiere Ergebnisse
        return self._aggregate_divergences(symbol, timeframe, divergences)

    def _fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> dict[str, np.ndarray]:
        """Hole OHLCV-Daten von Binance"""
        if not self.http:
            return {}

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
                return {
                    "open": data[:, 1].astype(float),
                    "high": data[:, 2].astype(float),
                    "low": data[:, 3].astype(float),
                    "close": data[:, 4].astype(float),
                    "volume": data[:, 5].astype(float),
                }

        except Exception as e:
            logger.error(f"OHLCV Fetch Fehler: {e}")

        return {}

    def _empty_analysis(self, symbol: str, timeframe: str) -> DivergenceAnalysis:
        """Leere Analyse wenn keine Daten"""
        return DivergenceAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            timeframe=timeframe,
            divergences=[],
            bullish_signal=0.0,
            bearish_signal=0.0,
            net_signal=0.0,
            divergence_count=0,
            dominant_type=DivergenceType.NONE,
            average_confidence=0.0,
        )

    def _aggregate_divergences(
        self,
        symbol: str,
        timeframe: str,
        divergences: list[Divergence],
    ) -> DivergenceAnalysis:
        """Aggregiere alle gefundenen Divergenzen"""
        if not divergences:
            return self._empty_analysis(symbol, timeframe)

        # Berechne Signals
        bullish_signals = [
            d.signal_strength
            for d in divergences
            if d.divergence_type in (DivergenceType.BULLISH, DivergenceType.HIDDEN_BULLISH)
        ]
        bearish_signals = [
            abs(d.signal_strength)
            for d in divergences
            if d.divergence_type in (DivergenceType.BEARISH, DivergenceType.HIDDEN_BEARISH)
        ]

        bullish_signal = np.mean(bullish_signals) if bullish_signals else 0.0
        bearish_signal = np.mean(bearish_signals) if bearish_signals else 0.0

        # Net Signal: Bullish positiv, Bearish negativ
        net_signal = bullish_signal - bearish_signal

        # Dominanter Typ
        if bullish_signal > bearish_signal:
            dominant = (
                DivergenceType.BULLISH if bullish_signal > 0.5 else DivergenceType.HIDDEN_BULLISH
            )
        elif bearish_signal > bullish_signal:
            dominant = (
                DivergenceType.BEARISH if bearish_signal > 0.5 else DivergenceType.HIDDEN_BEARISH
            )
        else:
            dominant = DivergenceType.NONE

        # Average Confidence
        avg_confidence = np.mean([d.confidence for d in divergences])

        return DivergenceAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            timeframe=timeframe,
            divergences=divergences,
            bullish_signal=float(bullish_signal),
            bearish_signal=float(bearish_signal),
            net_signal=float(net_signal),
            divergence_count=len(divergences),
            dominant_type=dominant,
            average_confidence=float(avg_confidence),
        )

    # ═══════════════════════════════════════════════════════════════
    # SIGNAL GENERATION
    # ═══════════════════════════════════════════════════════════════

    def get_divergence_signal(
        self,
        symbol: str,
        timeframe: str = "1h",
    ) -> tuple[float, str]:
        """
        Generiere Trading-Signal basierend auf Divergenzen.

        Returns: (signal_strength, reasoning)
        """
        analysis = self.analyze(symbol, timeframe)

        if analysis.divergence_count == 0:
            return 0.0, "No divergences detected"

        # Signal ist das Net Signal
        signal = analysis.net_signal

        # Reasoning
        reasons = []
        for div in analysis.divergences:
            reasons.append(f"{div.indicator} {div.divergence_type.value} ({div.strength.value})")

        return signal, " | ".join(reasons)

    def get_multi_timeframe_signal(
        self,
        symbol: str,
        timeframes: list[str] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        Multi-Timeframe Divergenz-Analyse.

        Wenn mehrere Timeframes die gleiche Divergenz zeigen,
        ist das Signal stärker.
        """
        if timeframes is None:
            timeframes = ["15m", "1h", "4h"]

        signals = {}

        for tf in timeframes:
            signal, _ = self.get_divergence_signal(symbol, tf)
            signals[tf] = signal

        # Gewichteter Durchschnitt (höhere Timeframes zählen mehr)
        weights = {"15m": 0.2, "1h": 0.35, "4h": 0.45}
        weighted_signal = sum(signals.get(tf, 0) * weights.get(tf, 0.33) for tf in timeframes)

        # Bonus wenn alle Timeframes übereinstimmen
        if all(s > 0 for s in signals.values() if s != 0) or all(
            s < 0 for s in signals.values() if s != 0
        ):
            weighted_signal *= 1.2

        return max(-1.0, min(1.0, weighted_signal)), signals

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_divergence(self, divergence: Divergence, symbol: str, cycle_id: str | None = None):
        """Speichere erkannte Divergenz in DB"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO divergence_signals (
                        symbol, cycle_id, indicator, divergence_type,
                        strength, signal_strength, confidence,
                        price_point1, price_point2,
                        indicator_point1, indicator_point2
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        cycle_id,
                        divergence.indicator,
                        divergence.divergence_type.value,
                        divergence.strength.value,
                        divergence.signal_strength,
                        divergence.confidence,
                        f"{divergence.price_point1[0]}:{divergence.price_point1[1]}",
                        f"{divergence.price_point2[0]}:{divergence.price_point2[1]}",
                        f"{divergence.indicator_point1[0]}:{divergence.indicator_point1[1]}",
                        f"{divergence.indicator_point2[0]}:{divergence.indicator_point2[1]}",
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Divergence Store Error (table may not exist): {e}")
            self.conn.rollback()

    def get_historical_divergences(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        """Hole historische Divergenzen für Analyse"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM divergence_signals
                    WHERE symbol = %s
                    AND created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at DESC
                """,
                    (symbol, days),
                )
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.debug(f"Divergence History Error: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
