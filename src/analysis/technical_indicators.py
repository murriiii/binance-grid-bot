"""
Technische Indikatoren
RSI, MACD, Bollinger Bands, Moving Averages

Ergänzt die Markowitz-Optimierung mit Timing-Signalen:
- Markowitz sagt WAS kaufen (beste Sharpe Ratio)
- Technische Analyse sagt WANN kaufen (überkauft/überverkauft)
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Signal(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class TechnicalSignals:
    """Zusammenfassung aller technischen Signale"""

    symbol: str
    price: float

    # Indikatoren
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    sma_20: float
    sma_50: float
    sma_200: float
    bollinger_upper: float
    bollinger_lower: float
    atr: float

    # Interpretierte Signale
    trend: Signal
    momentum: Signal
    volatility: str  # LOW, MEDIUM, HIGH

    # Gesamt
    overall_signal: Signal
    confidence: float
    reasoning: str


class TechnicalAnalyzer:
    """
    Berechnet technische Indikatoren und leitet Signale ab.

    Verwendet für:
    1. Entry Timing: Nicht kaufen wenn RSI > 70
    2. Exit Timing: Verkaufen wenn RSI > 80
    3. Trend Confirmation: Nur mit dem Trend handeln
    4. Volatility Adjustment: Position Size bei hoher Vola reduzieren
    """

    def __init__(self):
        pass

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index

        RSI < 30: Überverkauft (Kaufsignal)
        RSI > 70: Überkauft (Verkaufssignal)
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_macd(
        self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Moving Average Convergence Divergence

        MACD > Signal: Bullish
        MACD < Signal: Bearish
        Histogram wachsend: Momentum steigt
        """
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_bollinger_bands(
        self, prices: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands

        Preis > Upper Band: Überkauft
        Preis < Lower Band: Überverkauft
        Bands eng: Niedrige Volatilität, Ausbruch erwartet
        """
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)

        return upper, sma, lower

    def calculate_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """
        Average True Range (Volatilitätsindikator)

        Hoher ATR: Hohe Volatilität
        Niedriger ATR: Niedrige Volatilität
        """
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr

    def calculate_sma(self, prices: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average"""
        return prices.rolling(window=period).mean()

    def calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average"""
        return prices.ewm(span=period, adjust=False).mean()

    def analyze(self, df: pd.DataFrame, symbol: str = "UNKNOWN") -> TechnicalSignals:
        """
        Vollständige technische Analyse.

        Args:
            df: DataFrame mit 'close', 'high', 'low', 'volume'
            symbol: Symbol für die Analyse

        Returns:
            TechnicalSignals mit allen Indikatoren und Signalen
        """
        close = df["close"]
        high = df.get("high", close)
        low = df.get("low", close)

        # Berechne Indikatoren
        rsi = self.calculate_rsi(close)
        macd_line, macd_signal, macd_hist = self.calculate_macd(close)
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(close)
        atr = self.calculate_atr(high, low, close)
        sma_20 = self.calculate_sma(close, 20)
        sma_50 = self.calculate_sma(close, 50)
        sma_200 = self.calculate_sma(close, 200)

        # Aktuelle Werte
        current_price = close.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_macd = macd_line.iloc[-1]
        current_macd_signal = macd_signal.iloc[-1]
        current_macd_hist = macd_hist.iloc[-1]
        current_atr = atr.iloc[-1]

        # Interpretiere Signale

        # 1. RSI Signal
        if current_rsi < 30:
            rsi_signal = Signal.STRONG_BUY
            rsi_reason = f"RSI {current_rsi:.1f} - Stark überverkauft"
        elif current_rsi < 40:
            rsi_signal = Signal.BUY
            rsi_reason = f"RSI {current_rsi:.1f} - Überverkauft"
        elif current_rsi > 70:
            rsi_signal = Signal.STRONG_SELL
            rsi_reason = f"RSI {current_rsi:.1f} - Stark überkauft"
        elif current_rsi > 60:
            rsi_signal = Signal.SELL
            rsi_reason = f"RSI {current_rsi:.1f} - Überkauft"
        else:
            rsi_signal = Signal.NEUTRAL
            rsi_reason = f"RSI {current_rsi:.1f} - Neutral"

        # 2. MACD Signal
        if current_macd > current_macd_signal and current_macd_hist > 0:
            macd_signal_result = Signal.BUY
            macd_reason = "MACD bullish crossover"
        elif current_macd < current_macd_signal and current_macd_hist < 0:
            macd_signal_result = Signal.SELL
            macd_reason = "MACD bearish crossover"
        else:
            macd_signal_result = Signal.NEUTRAL
            macd_reason = "MACD neutral"

        # 3. Trend (basierend auf SMAs)
        if current_price > sma_20.iloc[-1] > sma_50.iloc[-1]:
            if sma_50.iloc[-1] > sma_200.iloc[-1]:
                trend_signal = Signal.STRONG_BUY
                trend_reason = "Starker Aufwärtstrend (Preis > SMA20 > SMA50 > SMA200)"
            else:
                trend_signal = Signal.BUY
                trend_reason = "Aufwärtstrend (Preis > SMA20 > SMA50)"
        elif current_price < sma_20.iloc[-1] < sma_50.iloc[-1]:
            if sma_50.iloc[-1] < sma_200.iloc[-1]:
                trend_signal = Signal.STRONG_SELL
                trend_reason = "Starker Abwärtstrend"
            else:
                trend_signal = Signal.SELL
                trend_reason = "Abwärtstrend"
        else:
            trend_signal = Signal.NEUTRAL
            trend_reason = "Seitwärtstrend"

        # 4. Volatilität
        avg_atr = atr.mean()
        if current_atr > avg_atr * 1.5:
            volatility = "HIGH"
        elif current_atr < avg_atr * 0.7:
            volatility = "LOW"
        else:
            volatility = "MEDIUM"

        # 5. Gesamt-Signal
        signals = [rsi_signal, macd_signal_result, trend_signal]
        buy_signals = sum(1 for s in signals if s in [Signal.BUY, Signal.STRONG_BUY])
        sell_signals = sum(1 for s in signals if s in [Signal.SELL, Signal.STRONG_SELL])

        if buy_signals >= 2 and sell_signals == 0:
            overall = Signal.BUY if buy_signals == 2 else Signal.STRONG_BUY
            confidence = 0.7 + (buy_signals * 0.1)
        elif sell_signals >= 2 and buy_signals == 0:
            overall = Signal.SELL if sell_signals == 2 else Signal.STRONG_SELL
            confidence = 0.7 + (sell_signals * 0.1)
        else:
            overall = Signal.NEUTRAL
            confidence = 0.5

        reasoning = f"{rsi_reason} | {macd_reason} | {trend_reason} | Volatilität: {volatility}"

        return TechnicalSignals(
            symbol=symbol,
            price=current_price,
            rsi=current_rsi,
            macd=current_macd,
            macd_signal=current_macd_signal,
            macd_histogram=current_macd_hist,
            sma_20=sma_20.iloc[-1],
            sma_50=sma_50.iloc[-1],
            sma_200=sma_200.iloc[-1] if len(sma_200.dropna()) > 0 else 0,
            bollinger_upper=bb_upper.iloc[-1],
            bollinger_lower=bb_lower.iloc[-1],
            atr=current_atr,
            trend=trend_signal,
            momentum=rsi_signal,
            volatility=volatility,
            overall_signal=overall,
            confidence=confidence,
            reasoning=reasoning,
        )

    def get_entry_timing(self, signals: TechnicalSignals) -> tuple[bool, str]:
        """
        Soll jetzt gekauft werden?

        Returns:
            (should_buy, reason)
        """
        # Nicht kaufen wenn überkauft
        if signals.rsi > 70:
            return False, f"RSI {signals.rsi:.1f} zu hoch - warte auf Pullback"

        # Nicht kaufen in starkem Abwärtstrend
        if signals.trend == Signal.STRONG_SELL:
            return False, "Starker Abwärtstrend - warte auf Stabilisierung"

        # Nicht kaufen bei extrem hoher Volatilität
        if signals.volatility == "HIGH" and signals.momentum != Signal.STRONG_BUY:
            return False, "Hohe Volatilität - warte auf ruhigeren Markt"

        # Gutes Timing
        if signals.rsi < 40 and signals.trend in [Signal.BUY, Signal.STRONG_BUY, Signal.NEUTRAL]:
            return True, f"Gutes Entry: RSI {signals.rsi:.1f} + Trend positiv/neutral"

        if signals.overall_signal in [Signal.BUY, Signal.STRONG_BUY]:
            return True, f"Technische Signale bullish: {signals.reasoning}"

        return True, "Keine negativen Signale - Entry möglich"

    def get_exit_timing(self, signals: TechnicalSignals, entry_price: float) -> tuple[bool, str]:
        """
        Soll jetzt verkauft werden?

        Returns:
            (should_sell, reason)
        """
        current_pnl = (signals.price - entry_price) / entry_price * 100

        # Verkaufen wenn stark überkauft und im Gewinn
        if signals.rsi > 80 and current_pnl > 5:
            return True, f"RSI {signals.rsi:.1f} extrem überkauft + {current_pnl:.1f}% Gewinn"

        # Verkaufen bei bearish MACD crossover und im Gewinn
        if signals.macd_histogram < 0 and signals.momentum == Signal.SELL and current_pnl > 3:
            return True, f"MACD bearish + {current_pnl:.1f}% Gewinn - Gewinne sichern"

        # Verkaufen bei Trendwechsel
        if signals.trend == Signal.STRONG_SELL and current_pnl > 0:
            return True, "Trendwechsel erkannt - Gewinne sichern"

        return False, "Kein Exit-Signal"


def generate_ta_report(signals: TechnicalSignals) -> str:
    """Generiert einen Telegram-freundlichen TA Report"""

    # Emojis für Signale
    signal_emoji = {
        Signal.STRONG_BUY: "🟢🟢",
        Signal.BUY: "🟢",
        Signal.NEUTRAL: "⚪",
        Signal.SELL: "🔴",
        Signal.STRONG_SELL: "🔴🔴",
    }

    return f"""
📊 *TECHNISCHE ANALYSE - {signals.symbol}*

*Preis:* `${signals.price:,.2f}`

*Indikatoren:*
├ RSI(14): `{signals.rsi:.1f}` {signal_emoji[signals.momentum]}
├ MACD: `{signals.macd:.4f}`
├ SMA20: `${signals.sma_20:,.2f}`
├ SMA50: `${signals.sma_50:,.2f}`
└ ATR: `${signals.atr:,.2f}` ({signals.volatility})

*Signale:*
├ Trend: {signal_emoji[signals.trend]} {signals.trend.value}
├ Momentum: {signal_emoji[signals.momentum]} {signals.momentum.value}
└ Overall: {signal_emoji[signals.overall_signal]} *{signals.overall_signal.value}*

*Confidence:* {signals.confidence * 100:.0f}%

_{signals.reasoning}_
"""
