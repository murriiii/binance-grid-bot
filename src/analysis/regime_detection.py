"""
Regime Detection - Erkennt Markt-Regimes mit Hidden Markov Model

Regimes:
- BULL: Steigender Trend, moderate Volatilität
- BEAR: Fallender Trend, hohe Volatilität
- SIDEWAYS: Seitwärts, niedrige Volatilität

Warum wichtig:
- Unterschiedliche Strategien pro Regime
- Bull: Trend folgen, aggressiver
- Bear: Vorsichtiger, mehr Cash
- Sideways: Grid Trading optimal
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

try:
    from hmmlearn import hmm

    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    logger.debug("hmmlearn nicht installiert - pip install hmmlearn")


class MarketRegime(Enum):
    """Markt-Regimes"""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    TRANSITION = "TRANSITION"


@dataclass
class RegimeState:
    """Aktueller Regime-Zustand"""

    current_regime: MarketRegime
    regime_probability: float  # Konfidenz (0-1)
    transition_probability: float  # Wahrscheinlichkeit für Regime-Wechsel
    regime_duration_days: int
    previous_regime: MarketRegime | None

    # Features die zur Erkennung verwendet wurden
    return_7d: float
    volatility_7d: float
    volume_trend: float
    fear_greed_avg: float

    # Model Confidence
    model_confidence: float


class RegimeDetector:
    """
    Hidden Markov Model für Markt-Regime Erkennung.

    Features:
    - 7-Tage Returns
    - 7-Tage Volatilität
    - Volume Trend
    - Fear & Greed Durchschnitt

    Zustände:
    - BULL: Positiver Return, moderate Vol
    - BEAR: Negativer Return, hohe Vol
    - SIDEWAYS: Flacher Return, niedrige Vol
    """

    NUM_STATES = 3
    REGIME_MAPPING = {0: MarketRegime.BULL, 1: MarketRegime.BEAR, 2: MarketRegime.SIDEWAYS}

    _instance = None

    def __init__(self):
        self.conn = None
        self.model = None
        self.is_fitted = False
        self.current_regime = MarketRegime.SIDEWAYS
        self.regime_start_date = datetime.now()

        self._connect_db()
        self._initialize_model()

    @classmethod
    def get_instance(cls) -> "RegimeDetector":
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
                logger.info("RegimeDetector: DB verbunden")
        except Exception as e:
            logger.error(f"RegimeDetector: DB Fehler: {e}")

    def _initialize_model(self):
        """Initialisiere HMM"""
        if not HMM_AVAILABLE:
            logger.warning(
                "RegimeDetector: hmmlearn nicht verfügbar, verwende regelbasierte Erkennung"
            )
            return

        try:
            self.model = hmm.GaussianHMM(
                n_components=self.NUM_STATES,
                covariance_type="full",
                n_iter=100,
                random_state=42,
            )

            # Initiale Parameter (werden durch fit() überschrieben)
            # Start-Wahrscheinlichkeiten: Gleichverteilt
            self.model.startprob_ = np.array([1 / 3, 1 / 3, 1 / 3])

            # Übergangs-Matrix: Regime-Persistenz
            self.model.transmat_ = np.array(
                [
                    [0.90, 0.05, 0.05],  # BULL bleibt meist BULL
                    [0.05, 0.90, 0.05],  # BEAR bleibt meist BEAR
                    [0.10, 0.10, 0.80],  # SIDEWAYS wechselt öfter
                ]
            )

            logger.info("RegimeDetector: HMM initialisiert")

        except Exception as e:
            logger.error(f"RegimeDetector: HMM Init Fehler: {e}")
            self.model = None

    # ═══════════════════════════════════════════════════════════════
    # FEATURE EXTRACTION
    # ═══════════════════════════════════════════════════════════════

    def _extract_features(
        self, prices: list[float], volumes: list[float], fear_greed: list[int]
    ) -> np.ndarray:
        """
        Extrahiere Features für HMM.

        Features:
        1. 7-Tage Return (log)
        2. 7-Tage Volatilität
        3. Volume Trend (aktuell vs Durchschnitt)
        4. Fear & Greed Niveau
        """
        if len(prices) < 8:
            return np.array([])

        features_list = []

        for i in range(7, len(prices)):
            # 7-Tage Return
            return_7d = np.log(prices[i] / prices[i - 7]) * 100  # In Prozent

            # 7-Tage Volatilität
            daily_returns = np.diff(np.log(prices[i - 7 : i + 1])) * 100
            volatility_7d = np.std(daily_returns)

            # Volume Trend
            if len(volumes) > i and np.mean(volumes[i - 7 : i]) > 0:
                volume_trend = volumes[i] / np.mean(volumes[i - 7 : i]) - 1
            else:
                volume_trend = 0

            # Fear & Greed
            fg_avg = np.mean(fear_greed[i - 7 : i + 1]) if len(fear_greed) > i else 50

            features_list.append([return_7d, volatility_7d, volume_trend, fg_avg])

        return np.array(features_list)

    def _get_historical_data(self, days: int = 365) -> tuple[list, list, list]:
        """Hole historische Daten aus der Datenbank"""
        if not self.conn:
            return [], [], []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        DATE_TRUNC('day', timestamp) as day,
                        AVG(btc_price) as price,
                        AVG(volume_24h) as volume,
                        AVG(fear_greed) as fear_greed
                    FROM market_snapshots
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                      AND btc_price IS NOT NULL
                    GROUP BY DATE_TRUNC('day', timestamp)
                    ORDER BY day
                """,
                    (days,),
                )

                rows = cur.fetchall()

                prices = [float(r["price"]) for r in rows if r["price"]]
                volumes = [float(r["volume"] or 0) for r in rows]
                fear_greed = [int(r["fear_greed"] or 50) for r in rows]

                return prices, volumes, fear_greed

        except Exception as e:
            logger.error(f"RegimeDetector: Daten-Abruf Fehler: {e}")
            return [], [], []

    # ═══════════════════════════════════════════════════════════════
    # MODEL TRAINING
    # ═══════════════════════════════════════════════════════════════

    def fit(
        self,
        prices: list[float] | None = None,
        volumes: list[float] | None = None,
        fear_greed: list[int] | None = None,
    ):
        """
        Trainiere HMM auf historischen Daten.

        Wenn keine Daten übergeben, hole aus DB.
        """
        if not HMM_AVAILABLE or not self.model:
            logger.warning("RegimeDetector: HMM nicht verfügbar")
            return

        # Hole Daten falls nicht übergeben
        if prices is None:
            prices, volumes, fear_greed = self._get_historical_data(365)

        if len(prices) < 30:
            logger.warning("RegimeDetector: Nicht genug Daten zum Trainieren")
            return

        try:
            # Feature Extraction
            features = self._extract_features(prices, volumes or [], fear_greed or [])

            if len(features) < 20:
                logger.warning("RegimeDetector: Nicht genug Features")
                return

            # Trainiere Model
            self.model.fit(features)
            self.is_fitted = True

            logger.info(f"RegimeDetector: HMM trainiert auf {len(features)} Datenpunkten")

        except Exception as e:
            logger.error(f"RegimeDetector: Training Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PREDICTION
    # ═══════════════════════════════════════════════════════════════

    def predict_regime(self, market_data: dict | None = None) -> RegimeState:
        """
        Sage aktuelles Markt-Regime voraus.

        Args:
            market_data: Dict mit aktuellen Marktdaten
                         Wenn None, hole aus DB

        Returns:
            RegimeState mit aktuellem Regime und Metriken
        """
        # Hole aktuelle Daten falls nicht übergeben
        if market_data is None:
            market_data = self._get_current_market_data()

        # Keine Daten verfügbar -> kann Regime nicht bestimmen
        if market_data is None:
            logger.warning("Regime Detection: Keine Marktdaten - überspringe Erkennung")
            return None

        # Extrahiere Features für Prediction
        return_7d = market_data.get("return_7d", 0)
        volatility_7d = market_data.get("volatility_7d", 2)
        volume_trend = market_data.get("volume_trend", 0)
        fear_greed_avg = market_data.get("fear_greed_avg", 50)

        # Wenn HMM verfügbar und trainiert, nutze es
        if HMM_AVAILABLE and self.model and self.is_fitted:
            regime, prob, transition = self._predict_with_hmm(
                return_7d, volatility_7d, volume_trend, fear_greed_avg
            )
        else:
            # Fallback: Regelbasierte Erkennung
            regime, prob, transition = self._predict_rule_based(
                return_7d, volatility_7d, fear_greed_avg
            )

        # Berechne Regime-Dauer
        if regime != self.current_regime:
            self.regime_start_date = datetime.now()

        regime_duration = (datetime.now() - self.regime_start_date).days

        previous = self.current_regime if regime != self.current_regime else None
        self.current_regime = regime

        return RegimeState(
            current_regime=regime,
            regime_probability=prob,
            transition_probability=transition,
            regime_duration_days=regime_duration,
            previous_regime=previous,
            return_7d=return_7d,
            volatility_7d=volatility_7d,
            volume_trend=volume_trend,
            fear_greed_avg=fear_greed_avg,
            model_confidence=prob,
        )

    def _predict_with_hmm(
        self,
        return_7d: float,
        volatility_7d: float,
        volume_trend: float,
        fear_greed_avg: float,
    ) -> tuple[MarketRegime, float, float]:
        """Prediction mit HMM"""
        features = np.array([[return_7d, volatility_7d, volume_trend, fear_greed_avg]])

        try:
            # Predict
            state = self.model.predict(features)[0]
            probs = self.model.predict_proba(features)[0]

            regime = self.REGIME_MAPPING.get(state, MarketRegime.SIDEWAYS)
            probability = float(probs[state])

            # Transition probability
            current_state_idx = list(self.REGIME_MAPPING.keys())[
                list(self.REGIME_MAPPING.values()).index(self.current_regime)
            ]
            transition_prob = 1 - self.model.transmat_[current_state_idx, current_state_idx]

            return regime, probability, transition_prob

        except Exception as e:
            logger.debug(f"HMM Prediction Fehler: {e}")
            return self._predict_rule_based(return_7d, volatility_7d, fear_greed_avg)

    def _predict_rule_based(
        self,
        return_7d: float,
        volatility_7d: float,
        fear_greed_avg: float,
    ) -> tuple[MarketRegime, float, float]:
        """
        Regelbasierte Regime-Erkennung (Fallback).

        Regeln:
        - BULL: Return > 5% ODER (Return > 0 UND F&G > 55)
        - BEAR: Return < -5% ODER (Return < 0 UND F&G < 30)
        - SIDEWAYS: Sonst
        """
        confidence = 0.7

        if return_7d > 5 or (return_7d > 0 and fear_greed_avg > 55):
            if return_7d > 10:
                confidence = 0.9
            return MarketRegime.BULL, confidence, 0.1

        elif return_7d < -5 or (return_7d < 0 and fear_greed_avg < 30):
            if return_7d < -10:
                confidence = 0.9
            return MarketRegime.BEAR, confidence, 0.1

        else:
            if abs(return_7d) < 2 and volatility_7d < 2:
                confidence = 0.8
            return MarketRegime.SIDEWAYS, confidence, 0.2

    def _get_current_market_data(self) -> dict | None:
        """Hole aktuelle Marktdaten aus DB"""
        if not self.conn:
            logger.debug("Regime Detection: Keine DB-Verbindung")
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    WITH recent AS (
                        SELECT
                            btc_price,
                            volume_24h,
                            fear_greed,
                            timestamp
                        FROM market_snapshots
                        WHERE timestamp > NOW() - INTERVAL '8 days'
                        ORDER BY timestamp DESC
                    )
                    SELECT
                        (SELECT btc_price FROM recent ORDER BY timestamp DESC LIMIT 1) as current_price,
                        (SELECT btc_price FROM recent ORDER BY timestamp LIMIT 1) as price_7d_ago,
                        AVG(fear_greed) as fear_greed_avg,
                        STDDEV(btc_price) / AVG(btc_price) * 100 as volatility
                    FROM recent
                """)

                row = cur.fetchone()
                if row and row["current_price"] and row["price_7d_ago"]:
                    return_7d = (
                        (float(row["current_price"]) - float(row["price_7d_ago"]))
                        / float(row["price_7d_ago"])
                        * 100
                    )
                    return {
                        "return_7d": return_7d,
                        "volatility_7d": float(row["volatility"] or 2),
                        "volume_trend": 0,
                        "fear_greed_avg": float(row["fear_greed_avg"] or 50),
                    }

        except Exception as e:
            logger.debug(f"Market data fetch error: {e}")

        logger.debug("Regime Detection: Keine Marktdaten in DB verfügbar")
        return None

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY ADJUSTMENT
    # ═══════════════════════════════════════════════════════════════

    def get_regime_adjusted_weights(self, regime: MarketRegime | None = None) -> dict[str, float]:
        """
        Hole Regime-angepasste Signal-Gewichte.

        BULL: Folge Trend, Momentum wichtiger
        BEAR: Contrarian, Sentiment wichtiger
        SIDEWAYS: Mean Reversion, RSI wichtiger
        """
        if regime is None:
            regime = self.current_regime

        weights = {
            MarketRegime.BULL: {
                "fear_greed": 0.10,
                "rsi": 0.10,
                "macd": 0.15,
                "trend": 0.25,  # Trend folgen!
                "volume": 0.10,
                "whale": 0.05,
                "sentiment": 0.05,
                "macro": 0.05,
                "ai": 0.15,
            },
            MarketRegime.BEAR: {
                "fear_greed": 0.25,  # Buy fear!
                "rsi": 0.15,
                "macd": 0.10,
                "trend": 0.05,
                "volume": 0.05,
                "whale": 0.10,
                "sentiment": 0.10,
                "macro": 0.05,
                "ai": 0.15,
            },
            MarketRegime.SIDEWAYS: {
                "fear_greed": 0.10,
                "rsi": 0.25,  # Mean reversion!
                "macd": 0.15,
                "trend": 0.05,
                "volume": 0.05,
                "whale": 0.05,
                "sentiment": 0.10,
                "macro": 0.05,
                "ai": 0.20,
            },
        }

        return weights.get(regime, weights[MarketRegime.SIDEWAYS])

    def get_regime_trading_rules(self, regime: MarketRegime | None = None) -> dict[str, Any]:
        """Hole Regime-spezifische Trading-Regeln"""
        if regime is None:
            regime = self.current_regime

        rules = {
            MarketRegime.BULL: {
                "position_size_multiplier": 1.2,
                "stop_loss_pct": 7,
                "take_profit_pct": 15,
                "grid_bias": "buy_heavy",  # Mehr Buy-Levels
                "min_confidence": 0.4,
            },
            MarketRegime.BEAR: {
                "position_size_multiplier": 0.7,
                "stop_loss_pct": 5,
                "take_profit_pct": 8,
                "grid_bias": "sell_heavy",
                "min_confidence": 0.6,
            },
            MarketRegime.SIDEWAYS: {
                "position_size_multiplier": 1.0,
                "stop_loss_pct": 5,
                "take_profit_pct": 10,
                "grid_bias": "balanced",
                "min_confidence": 0.5,
            },
        }

        return rules.get(regime, rules[MarketRegime.SIDEWAYS])

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_regime(self, state: RegimeState):
        """Speichere Regime-State in DB"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO regime_history (
                        regime, regime_probability, transition_probability,
                        return_7d, volatility_7d, volume_trend, fear_greed_avg,
                        model_confidence, previous_regime, regime_duration_hours
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        state.current_regime.value,
                        state.regime_probability,
                        state.transition_probability,
                        state.return_7d,
                        state.volatility_7d,
                        state.volume_trend,
                        state.fear_greed_avg,
                        state.model_confidence,
                        state.previous_regime.value if state.previous_regime else None,
                        state.regime_duration_days * 24,
                    ),
                )
                self.conn.commit()
                logger.debug(f"Regime {state.current_regime.value} gespeichert")

        except Exception as e:
            logger.error(f"Regime Speicherfehler: {e}")
            self.conn.rollback()

    def get_regime_history(self, days: int = 30) -> list[dict[str, Any]]:
        """Hole Regime-History"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM regime_history
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                    ORDER BY timestamp DESC
                """,
                    (days,),
                )
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Regime History Fehler: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
