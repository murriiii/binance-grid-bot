"""
Signal Analyzer - Berechnet und speichert Signal-Komponenten

Für jeden Trade wird gespeichert:
- Welche Signale wurden verwendet?
- Welche Gewichte hatten sie?
- Wie stark war jedes Signal?
- War das Signal korrekt?

Ermöglicht:
- Nachvollziehen welche Signale zur Entscheidung beigetragen haben
- Lernen welche Signale gut/schlecht performen
- Optimierung der Signal-Gewichte über Zeit
- Divergenz-Erkennung (widersprüchliche Signale)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


@dataclass
class SignalBreakdown:
    """Aufschlüsselung aller Signale für eine Entscheidung"""

    # Einzelne Signale (-1 bis +1)
    # Negativ = SELL/BEARISH, Positiv = BUY/BULLISH
    fear_greed_signal: float  # Contrarian: Fear=Buy, Greed=Sell
    rsi_signal: float  # <30=Buy, >70=Sell
    macd_signal: float  # Crossover-basiert
    trend_signal: float  # SMA Alignment
    volume_signal: float  # Volume Confirmation
    whale_signal: float  # Large transactions
    sentiment_signal: float  # Social/News
    macro_signal: float  # Economic events

    # AI Signale
    ai_direction_signal: float
    ai_confidence: float
    ai_risk_level: str  # LOW, MEDIUM, HIGH
    playbook_alignment: float  # Wie gut passt zur Playbook-Empfehlung?

    # Gewichte
    weights: dict[str, float]

    # Kombinierte Scores
    math_composite: float
    ai_composite: float
    final_score: float

    # Divergenz
    has_divergence: bool = False
    divergence_type: str | None = None
    divergence_strength: float = 0.0


# Default Gewichte (werden durch Bayesian Learning aktualisiert)
DEFAULT_WEIGHTS = {
    "fear_greed": 0.15,
    "rsi": 0.15,
    "macd": 0.10,
    "trend": 0.15,
    "volume": 0.05,
    "whale": 0.05,
    "sentiment": 0.10,
    "macro": 0.05,
    "ai": 0.20,
}


class SignalAnalyzer(SingletonMixin):
    """
    Analysiert und speichert Signal-Komponenten für jeden Trade.

    Features:
    1. Berechnet einzelne Signal-Scores aus Rohdaten
    2. Kombiniert Signale mit konfigurierbaren Gewichten
    3. Erkennt Divergenzen (widersprüchliche Signale)
    4. Speichert alles für spätere Analyse
    """

    def __init__(self):
        self.conn = None
        self.current_weights = DEFAULT_WEIGHTS.copy()
        self._connect()
        self._load_latest_weights()

    def _connect(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("SignalAnalyzer: PostgreSQL verbunden")
        except Exception as e:
            logger.error(f"SignalAnalyzer: DB Verbindung fehlgeschlagen: {e}")

    def _load_latest_weights(self):
        """Lade neueste Gewichte aus der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT fear_greed_weight, rsi_weight, macd_weight, trend_weight,
                           volume_weight, whale_weight, sentiment_weight, macro_weight, ai_weight
                    FROM signal_weights
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    self.current_weights = {
                        "fear_greed": float(row["fear_greed_weight"])
                        if row["fear_greed_weight"]
                        else 0.15,
                        "rsi": float(row["rsi_weight"]) if row["rsi_weight"] else 0.15,
                        "macd": float(row["macd_weight"]) if row["macd_weight"] else 0.10,
                        "trend": float(row["trend_weight"]) if row["trend_weight"] else 0.15,
                        "volume": float(row["volume_weight"]) if row["volume_weight"] else 0.05,
                        "whale": float(row["whale_weight"]) if row["whale_weight"] else 0.05,
                        "sentiment": float(row["sentiment_weight"])
                        if row["sentiment_weight"]
                        else 0.10,
                        "macro": float(row["macro_weight"]) if row["macro_weight"] else 0.05,
                        "ai": float(row["ai_weight"]) if row["ai_weight"] else 0.20,
                    }
                    logger.info("SignalAnalyzer: Gewichte aus DB geladen")
        except Exception as e:
            logger.debug(f"SignalAnalyzer: Keine Gewichte in DB: {e}")

    # ═══════════════════════════════════════════════════════════════
    # SIGNAL CALCULATIONS
    # ═══════════════════════════════════════════════════════════════

    def calculate_fear_greed_signal(self, fear_greed: int) -> float:
        """
        Berechne Fear & Greed Signal (Contrarian).

        0-24 (Extreme Fear) → +1.0 (Strong Buy)
        25-44 (Fear) → +0.5
        45-55 (Neutral) → 0.0
        56-74 (Greed) → -0.5
        75-100 (Extreme Greed) → -1.0 (Strong Sell)
        """
        if fear_greed <= 24:
            return 1.0
        elif fear_greed <= 44:
            return 0.5
        elif fear_greed <= 55:
            return 0.0
        elif fear_greed <= 74:
            return -0.5
        else:
            return -1.0

    def calculate_rsi_signal(self, rsi: float) -> float:
        """
        Berechne RSI Signal.

        <20 → +1.0 (Heavily Oversold)
        20-30 → +0.7 (Oversold)
        30-40 → +0.3 (Slightly Oversold)
        40-60 → 0.0 (Neutral)
        60-70 → -0.3 (Slightly Overbought)
        70-80 → -0.7 (Overbought)
        >80 → -1.0 (Heavily Overbought)
        """
        if rsi < 20:
            return 1.0
        elif rsi < 30:
            return 0.7
        elif rsi < 40:
            return 0.3
        elif rsi < 60:
            return 0.0
        elif rsi < 70:
            return -0.3
        elif rsi < 80:
            return -0.7
        else:
            return -1.0

    def calculate_macd_signal(
        self,
        macd_line: float,
        macd_signal: float,
        macd_histogram: float,
        prev_histogram: float | None = None,
    ) -> float:
        """
        Berechne MACD Signal.

        Basiert auf:
        - Crossover (MACD über/unter Signal Line)
        - Histogram Richtung
        - Divergenz vom Nullpunkt
        """
        signal = 0.0

        # Crossover-Richtung
        if macd_line > macd_signal:
            signal += 0.3
        else:
            signal -= 0.3

        # Histogram-Richtung
        if prev_histogram is not None:
            if macd_histogram > prev_histogram:
                signal += 0.4
            else:
                signal -= 0.4
        elif macd_histogram > 0:
            signal += 0.2
        else:
            signal -= 0.2

        # Über/unter Nulllinie
        if macd_line > 0:
            signal += 0.3
        else:
            signal -= 0.3

        return max(-1.0, min(1.0, signal))

    def calculate_trend_signal(
        self,
        price: float,
        sma_20: float,
        sma_50: float,
        sma_200: float | None = None,
    ) -> float:
        """
        Berechne Trend Signal basierend auf SMA Alignment.

        Price > SMA20 > SMA50 > SMA200 → Strong Uptrend (+1.0)
        Price < SMA20 < SMA50 < SMA200 → Strong Downtrend (-1.0)
        """
        signal = 0.0

        # Price vs SMA20
        if price > sma_20:
            signal += 0.3
        else:
            signal -= 0.3

        # SMA20 vs SMA50
        if sma_20 > sma_50:
            signal += 0.4
        else:
            signal -= 0.4

        # SMA50 vs SMA200 (wenn verfügbar)
        if sma_200:
            if sma_50 > sma_200:
                signal += 0.3
            else:
                signal -= 0.3

        return max(-1.0, min(1.0, signal))

    def calculate_volume_signal(
        self,
        current_volume: float,
        avg_volume: float,
        price_change: float,
    ) -> float:
        """
        Berechne Volume Signal.

        Hohe Volume + Price Up → Bullish Confirmation
        Hohe Volume + Price Down → Bearish Confirmation
        Niedrige Volume → Weak Signal
        """
        if avg_volume == 0:
            return 0.0

        volume_ratio = current_volume / avg_volume

        # Volume Confirmation
        if volume_ratio > 1.5:  # High volume
            if price_change > 0:
                return min(1.0, volume_ratio - 1)  # Bullish
            else:
                return max(-1.0, -(volume_ratio - 1))  # Bearish
        elif volume_ratio < 0.5:  # Low volume
            return 0.0  # No signal
        else:
            return price_change / 10  # Weak signal proportional to price change

    def calculate_whale_signal(
        self,
        recent_whale_buys_usd: float,
        recent_whale_sells_usd: float,
    ) -> float:
        """
        Berechne Whale Signal.

        Accumulation (mehr Buys) → Bullish
        Distribution (mehr Sells) → Bearish
        """
        net_flow = recent_whale_buys_usd - recent_whale_sells_usd
        total_flow = recent_whale_buys_usd + recent_whale_sells_usd

        if total_flow == 0:
            return 0.0

        # Normalisieren auf -1 bis +1
        signal = net_flow / total_flow
        return max(-1.0, min(1.0, signal))

    def calculate_sentiment_signal(
        self,
        social_score: float,  # 0-100
        news_sentiment: float | None = None,  # -1 to +1
    ) -> float:
        """
        Berechne Sentiment Signal.

        Kombiniert Social Sentiment und News Sentiment.
        """
        # Social Score auf -1 bis +1 normalisieren
        social_signal = (social_score - 50) / 50

        if news_sentiment is not None:
            return social_signal * 0.6 + news_sentiment * 0.4
        else:
            return social_signal

    def calculate_macro_signal(
        self,
        upcoming_events: list[dict] | None = None,
        etf_flow_7d: float = 0,
        fed_sentiment: str | None = None,  # HAWKISH, DOVISH, NEUTRAL
    ) -> float:
        """
        Berechne Macro Signal.

        Kombiniert:
        - Anstehende High-Impact Events
        - ETF Flows
        - Fed Sentiment
        """
        signal = 0.0

        # ETF Flows
        if etf_flow_7d > 500_000_000:  # >$500M inflow
            signal += 0.5
        elif etf_flow_7d > 0:
            signal += 0.2
        elif etf_flow_7d < -500_000_000:  # >$500M outflow
            signal -= 0.5
        elif etf_flow_7d < 0:
            signal -= 0.2

        # Fed Sentiment
        if fed_sentiment == "DOVISH":
            signal += 0.3
        elif fed_sentiment == "HAWKISH":
            signal -= 0.3

        # Upcoming High-Impact Events (Vorsicht angebracht)
        if upcoming_events:
            high_impact_count = sum(1 for e in upcoming_events if e.get("impact") == "HIGH")
            if high_impact_count > 0:
                signal *= 0.5  # Reduziere Signalstärke vor Events

        return max(-1.0, min(1.0, signal))

    def calculate_ai_signal(
        self,
        ai_direction: str,  # BULLISH, BEARISH, NEUTRAL
        ai_confidence: float,  # 0-1
        ai_risk_level: str,  # LOW, MEDIUM, HIGH
    ) -> tuple[float, float, str]:
        """
        Konvertiere AI Output zu Signal.

        Returns: (direction_signal, confidence, risk_level)
        """
        direction_signal = 0.0
        if ai_direction == "BULLISH":
            direction_signal = 1.0
        elif ai_direction == "BEARISH":
            direction_signal = -1.0

        # Skaliere mit Confidence
        scaled_signal = direction_signal * ai_confidence

        return scaled_signal, ai_confidence, ai_risk_level

    # ═══════════════════════════════════════════════════════════════
    # COMPOSITE CALCULATIONS
    # ═══════════════════════════════════════════════════════════════

    def compute_all_signals(self, market_data: dict) -> SignalBreakdown:
        """
        Berechne alle Signale aus Marktdaten.

        Args:
            market_data: Dict mit allen benötigten Daten

        Returns:
            SignalBreakdown mit allen berechneten Werten
        """
        # Einzelne Signale
        fg_signal = self.calculate_fear_greed_signal(market_data.get("fear_greed", 50))
        rsi_signal = self.calculate_rsi_signal(market_data.get("rsi", 50))
        macd_signal = self.calculate_macd_signal(
            market_data.get("macd_line", 0),
            market_data.get("macd_signal", 0),
            market_data.get("macd_histogram", 0),
            market_data.get("prev_macd_histogram"),
        )
        trend_signal = self.calculate_trend_signal(
            market_data.get("price", 0),
            market_data.get("sma_20", 0),
            market_data.get("sma_50", 0),
            market_data.get("sma_200"),
        )
        volume_signal = self.calculate_volume_signal(
            market_data.get("volume", 0),
            market_data.get("avg_volume", 1),
            market_data.get("price_change_24h", 0),
        )
        whale_signal = self.calculate_whale_signal(
            market_data.get("whale_buys_usd", 0),
            market_data.get("whale_sells_usd", 0),
        )
        sentiment_signal = self.calculate_sentiment_signal(
            market_data.get("social_score", 50),
            market_data.get("news_sentiment"),
        )
        macro_signal = self.calculate_macro_signal(
            market_data.get("upcoming_events"),
            market_data.get("etf_flow_7d", 0),
            market_data.get("fed_sentiment"),
        )

        # AI Signal
        ai_dir_signal, ai_conf, ai_risk = self.calculate_ai_signal(
            market_data.get("ai_direction", "NEUTRAL"),
            market_data.get("ai_confidence", 0.5),
            market_data.get("ai_risk_level", "MEDIUM"),
        )

        # Playbook Alignment
        playbook_alignment = market_data.get("playbook_alignment", 0.5)

        # Math Composite (ohne AI)
        math_signals = {
            "fear_greed": fg_signal,
            "rsi": rsi_signal,
            "macd": macd_signal,
            "trend": trend_signal,
            "volume": volume_signal,
            "whale": whale_signal,
            "sentiment": sentiment_signal,
            "macro": macro_signal,
        }

        math_composite = sum(
            signal * self.current_weights.get(name, 0) for name, signal in math_signals.items()
        )

        # AI Composite
        ai_composite = ai_dir_signal * self.current_weights.get("ai", 0.20)

        # Final Score
        final_score = math_composite + ai_composite

        # Divergenz-Erkennung
        has_divergence, div_type, div_strength = self._detect_divergence(
            math_signals, ai_dir_signal
        )

        return SignalBreakdown(
            fear_greed_signal=fg_signal,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            trend_signal=trend_signal,
            volume_signal=volume_signal,
            whale_signal=whale_signal,
            sentiment_signal=sentiment_signal,
            macro_signal=macro_signal,
            ai_direction_signal=ai_dir_signal,
            ai_confidence=ai_conf,
            ai_risk_level=ai_risk,
            playbook_alignment=playbook_alignment,
            weights=self.current_weights.copy(),
            math_composite=math_composite,
            ai_composite=ai_composite,
            final_score=final_score,
            has_divergence=has_divergence,
            divergence_type=div_type,
            divergence_strength=div_strength,
        )

    def _detect_divergence(
        self,
        math_signals: dict[str, float],
        ai_signal: float,
    ) -> tuple[bool, str | None, float]:
        """
        Erkenne Divergenzen zwischen Signalen.

        Divergenz = Signale zeigen in verschiedene Richtungen
        """
        # Zähle bullish vs bearish Signale
        bullish_count = sum(1 for s in math_signals.values() if s > 0.3)
        bearish_count = sum(1 for s in math_signals.values() if s < -0.3)

        # AI vs Math Divergenz
        math_direction = sum(math_signals.values())
        ai_direction = ai_signal

        has_divergence = False
        div_type = None
        div_strength = 0.0

        # Starke Divergenz: Math und AI zeigen in verschiedene Richtungen
        if (math_direction > 0.5 and ai_direction < -0.3) or (
            math_direction < -0.5 and ai_direction > 0.3
        ):
            has_divergence = True
            div_type = "math_ai_divergence"
            div_strength = abs(math_direction - ai_direction) / 2

        # Interne Math-Divergenz: Signale widersprechen sich stark
        elif bullish_count >= 3 and bearish_count >= 3:
            has_divergence = True
            div_type = "internal_divergence"
            div_strength = min(bullish_count, bearish_count) / len(math_signals)

        return has_divergence, div_type, div_strength

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_signals(
        self,
        trade_id: str,
        signals: SignalBreakdown,
        cycle_id: str | None = None,
        cohort_id: str | None = None,
    ):
        """Speichere Signal-Breakdown für einen Trade"""
        if not self.conn:
            logger.debug("SignalAnalyzer: DB nicht verfügbar")
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signal_components (
                        trade_id, cycle_id, cohort_id,
                        fear_greed_signal, rsi_signal, macd_signal, trend_signal,
                        volume_signal, whale_signal, sentiment_signal, macro_signal,
                        ai_direction_signal, ai_confidence, ai_risk_level,
                        playbook_alignment_score, weights_applied,
                        math_composite_score, ai_composite_score, final_score,
                        has_divergence, divergence_type, divergence_strength
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                """,
                    (
                        trade_id,
                        cycle_id,
                        cohort_id,
                        signals.fear_greed_signal,
                        signals.rsi_signal,
                        signals.macd_signal,
                        signals.trend_signal,
                        signals.volume_signal,
                        signals.whale_signal,
                        signals.sentiment_signal,
                        signals.macro_signal,
                        signals.ai_direction_signal,
                        signals.ai_confidence,
                        signals.ai_risk_level,
                        signals.playbook_alignment,
                        Json(signals.weights),
                        signals.math_composite,
                        signals.ai_composite,
                        signals.final_score,
                        signals.has_divergence,
                        signals.divergence_type,
                        signals.divergence_strength,
                    ),
                )
                self.conn.commit()
                logger.debug(f"SignalAnalyzer: Signals für Trade {trade_id} gespeichert")

        except Exception as e:
            logger.error(f"SignalAnalyzer: Fehler beim Speichern: {e}")
            self.conn.rollback()

    def update_signal_outcome(self, trade_id: str, was_correct: bool):
        """Update ob Signal korrekt war (nach Trade-Outcome bekannt)"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE signal_components
                    SET was_correct = %s
                    WHERE trade_id = %s
                """,
                    (was_correct, trade_id),
                )
                self.conn.commit()
        except Exception as e:
            logger.error(f"SignalAnalyzer: Fehler beim Update: {e}")
            self.conn.rollback()

    def get_signal_performance(self, days: int = 30) -> dict[str, Any]:
        """Evaluiere Signal-Performance der letzten N Tage"""
        if not self.conn:
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        AVG(CASE WHEN fear_greed_signal > 0.3 AND was_correct THEN 1
                                 WHEN fear_greed_signal > 0.3 THEN 0 END) as fear_greed_accuracy,
                        AVG(CASE WHEN rsi_signal > 0.3 AND was_correct THEN 1
                                 WHEN rsi_signal > 0.3 THEN 0 END) as rsi_accuracy,
                        AVG(CASE WHEN macd_signal > 0.3 AND was_correct THEN 1
                                 WHEN macd_signal > 0.3 THEN 0 END) as macd_accuracy,
                        AVG(CASE WHEN trend_signal > 0.3 AND was_correct THEN 1
                                 WHEN trend_signal > 0.3 THEN 0 END) as trend_accuracy,
                        AVG(CASE WHEN ai_direction_signal > 0.3 AND was_correct THEN 1
                                 WHEN ai_direction_signal > 0.3 THEN 0 END) as ai_accuracy,
                        COUNT(*) as total_signals,
                        SUM(CASE WHEN was_correct THEN 1 ELSE 0 END) as correct_signals
                    FROM signal_components
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                      AND was_correct IS NOT NULL
                """,
                    (days,),
                )

                row = cur.fetchone()
                if row:
                    return {k: float(v) if v is not None else None for k, v in row.items()}
                return {}

        except Exception as e:
            logger.error(f"SignalAnalyzer: Fehler bei Performance-Abfrage: {e}")
            return {}

    def update_weights(self, new_weights: dict[str, float]):
        """Update Signal-Gewichte"""
        self.current_weights.update(new_weights)

        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signal_weights (
                        fear_greed_weight, rsi_weight, macd_weight, trend_weight,
                        volume_weight, whale_weight, sentiment_weight, macro_weight, ai_weight
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        new_weights.get("fear_greed", self.current_weights["fear_greed"]),
                        new_weights.get("rsi", self.current_weights["rsi"]),
                        new_weights.get("macd", self.current_weights["macd"]),
                        new_weights.get("trend", self.current_weights["trend"]),
                        new_weights.get("volume", self.current_weights["volume"]),
                        new_weights.get("whale", self.current_weights["whale"]),
                        new_weights.get("sentiment", self.current_weights["sentiment"]),
                        new_weights.get("macro", self.current_weights["macro"]),
                        new_weights.get("ai", self.current_weights["ai"]),
                    ),
                )
                self.conn.commit()
                logger.info("SignalAnalyzer: Gewichte aktualisiert")

        except Exception as e:
            logger.error(f"SignalAnalyzer: Fehler beim Weight-Update: {e}")
            self.conn.rollback()

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
