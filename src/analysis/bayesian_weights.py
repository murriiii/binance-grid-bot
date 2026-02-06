"""
Bayesian Signal Weight Learning

Verwendet Dirichlet-Verteilung für adaptives Signal-Gewichts-Learning:
- Prior: Gleichverteilte Gewichte (uninformativer Prior)
- Likelihood: Signal-Accuracy aus historischen Trades
- Posterior: Gewichtete Kombination von Prior und Daten

Die Gewichte werden wöchentlich aktualisiert basierend auf:
1. Wie oft war ein Signal korrekt?
2. Wie stark war die Korrelation mit positivem Outcome?
3. Regime-spezifische Performance

Mathematik:
- Dirichlet(α₁, α₂, ..., αₖ) wobei αᵢ = α₀ + Σ(accuracy_i * count_i)
- α₀ = Prior Stärke (höher = mehr Vertrauen in Prior)
- Posterior Mean: αᵢ / Σαⱼ
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass
class SignalPerformance:
    """Performance-Metriken für ein einzelnes Signal"""

    signal_name: str
    total_trades: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    avg_contribution: float = 0.0  # Durchschnittlicher Beitrag zum Gesamtsignal
    correlation_with_pnl: float = 0.0  # Korrelation mit Trade-PnL
    regime_performance: dict[str, float] = field(default_factory=dict)


@dataclass
class BayesianWeights:
    """Aktueller Zustand der Bayesian Weights"""

    weights: dict[str, float]
    alpha_values: dict[str, float]  # Dirichlet Parameter
    confidence: float  # Wie sicher sind wir über die Weights
    last_updated: datetime
    sample_size: int
    regime: str | None = None


# Standard Signal-Namen
SIGNAL_NAMES = [
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

# Default Gewichte (gleichverteilt)
DEFAULT_WEIGHTS = {name: 1.0 / len(SIGNAL_NAMES) for name in SIGNAL_NAMES}

# Prior Stärke - höher = mehr Vertrauen in Prior (weniger reaktiv auf neue Daten)
PRIOR_STRENGTH = 10.0

# Minimum Anzahl Trades für Weight-Update
MIN_TRADES_FOR_UPDATE = 20

# Minimum Weight (verhindert dass ein Signal komplett ignoriert wird)
MIN_WEIGHT = 0.02

# Maximum Weight (verhindert Übergewichtung)
MAX_WEIGHT = 0.30


class BayesianWeightLearner:
    """
    Lernt optimale Signal-Gewichte aus historischen Trade-Daten.

    Features:
    1. Dirichlet-basiertes Bayesian Learning
    2. Regime-spezifische Gewichte
    3. Decay für ältere Daten (neuere Daten zählen mehr)
    4. Confidence-basierte Weight-Updates
    """

    _instance = None

    def __init__(self):
        self.conn = None
        self._connect_db()

        # Aktuelle Gewichte
        self.current_weights: dict[str, float] = DEFAULT_WEIGHTS.copy()
        self.alpha_values: dict[str, float] = dict.fromkeys(SIGNAL_NAMES, PRIOR_STRENGTH)

        # Lade gespeicherte Weights
        self._load_weights_from_db()

    @classmethod
    def get_instance(cls) -> "BayesianWeightLearner":
        """Singleton Pattern"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset für Tests"""
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
        cls._instance = None

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("BayesianWeightLearner: DB verbunden")
        except Exception as e:
            logger.error(f"BayesianWeightLearner: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # WEIGHT CALCULATION
    # ═══════════════════════════════════════════════════════════════

    def get_weights(self, regime: str | None = None) -> dict[str, float]:
        """
        Hole aktuelle Gewichte, optional Regime-spezifisch.

        Args:
            regime: Optional Markt-Regime (BULL, BEAR, SIDEWAYS)

        Returns:
            Dictionary mit Signal-Gewichten (summieren zu 1)
        """
        if regime:
            regime_weights = self._get_regime_weights(regime)
            if regime_weights:
                return regime_weights

        return self.current_weights.copy()

    def _get_regime_weights(self, regime: str) -> dict[str, float] | None:
        """Hole Regime-spezifische Gewichte aus DB"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT weights FROM signal_weights
                    WHERE regime = %s AND is_active = TRUE
                    ORDER BY created_at DESC LIMIT 1
                """,
                    (regime,),
                )
                row = cur.fetchone()
                if row and row["weights"]:
                    return dict(row["weights"])

        except Exception as e:
            logger.debug(f"Regime weights fetch error: {e}")

        return None

    def update_weights(
        self,
        cohort_id: str | None = None,
        lookback_days: int = 30,
        regime: str | None = None,
    ) -> BayesianWeights:
        """
        Aktualisiere Gewichte basierend auf Signal-Performance.

        Args:
            cohort_id: Optional - nur Trades dieser Cohort
            lookback_days: Anzahl Tage für Analyse
            regime: Optional - nur Trades in diesem Regime

        Returns:
            BayesianWeights mit aktualisierten Werten
        """
        # 1. Hole Signal Performance aus DB
        performance = self._calculate_signal_performance(cohort_id, lookback_days, regime)

        if (
            not performance
            or sum(p.total_trades for p in performance.values()) < MIN_TRADES_FOR_UPDATE
        ):
            logger.info(f"Nicht genug Trades für Weight-Update (min: {MIN_TRADES_FOR_UPDATE})")
            return BayesianWeights(
                weights=self.current_weights,
                alpha_values=self.alpha_values,
                confidence=0.0,
                last_updated=datetime.now(),
                sample_size=0,
                regime=regime,
            )

        # 2. Berechne neue Alpha-Werte (Dirichlet Parameter)
        new_alphas = self._compute_posterior_alphas(performance)

        # 3. Normalisiere zu Gewichten
        new_weights = self._normalize_weights(new_alphas)

        # 4. Berechne Confidence
        total_trades = sum(p.total_trades for p in performance.values())
        confidence = min(1.0, total_trades / 100)  # Max confidence bei 100+ Trades

        # 5. Update interne State
        self.alpha_values = new_alphas
        self.current_weights = new_weights

        # 6. Speichere in DB
        result = BayesianWeights(
            weights=new_weights,
            alpha_values=new_alphas,
            confidence=confidence,
            last_updated=datetime.now(),
            sample_size=total_trades,
            regime=regime,
        )

        self._store_weights(result, cohort_id)

        logger.info(
            f"Bayesian Weights aktualisiert: {total_trades} Trades, Confidence: {confidence:.2f}"
        )

        return result

    def _calculate_signal_performance(
        self,
        cohort_id: str | None,
        lookback_days: int,
        regime: str | None,
    ) -> dict[str, SignalPerformance]:
        """Berechne Performance für jedes Signal"""
        if not self.conn:
            return {}

        performance = {name: SignalPerformance(signal_name=name) for name in SIGNAL_NAMES}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query für Signal Components mit Outcome
                query = """
                    SELECT
                        sc.*,
                        tp.pnl_pct,
                        rh.regime
                    FROM signal_components sc
                    LEFT JOIN trade_pairs tp ON sc.trade_id = tp.entry_trade_id
                    LEFT JOIN regime_history rh ON DATE(sc.created_at) = DATE(rh.timestamp)
                    WHERE sc.created_at >= NOW() - INTERVAL '%s days'
                    AND tp.status = 'closed'
                """

                params = [lookback_days]

                if cohort_id:
                    query += " AND sc.cohort_id = %s"
                    params.append(cohort_id)

                if regime:
                    query += " AND rh.regime = %s"
                    params.append(regime)

                cur.execute(query, params)
                rows = cur.fetchall()

                if not rows:
                    return performance

                # Verarbeite jeden Trade
                signal_values: dict[str, list[tuple[float, float]]] = {
                    name: [] for name in SIGNAL_NAMES
                }

                for row in rows:
                    pnl = float(row.get("pnl_pct") or 0)
                    was_profitable = pnl > 0

                    for signal_name in SIGNAL_NAMES:
                        col_name = f"{signal_name}_signal"
                        if col_name in row and row[col_name] is not None:
                            signal_val = float(row[col_name])
                            signal_values[signal_name].append((signal_val, pnl))

                            # War die Vorhersage korrekt?
                            # Positives Signal + Profit ODER Negatives Signal + Loss
                            signal_correct = (signal_val > 0 and was_profitable) or (
                                signal_val < 0 and not was_profitable
                            )

                            performance[signal_name].total_trades += 1
                            if signal_correct:
                                performance[signal_name].correct_predictions += 1

                # Berechne finale Metriken
                for name, perf in performance.items():
                    if perf.total_trades > 0:
                        perf.accuracy = perf.correct_predictions / perf.total_trades

                        # Korrelation berechnen
                        if len(signal_values[name]) >= 3:
                            signals = np.array([v[0] for v in signal_values[name]])
                            pnls = np.array([v[1] for v in signal_values[name]])

                            if np.std(signals) > 0 and np.std(pnls) > 0:
                                perf.correlation_with_pnl = float(np.corrcoef(signals, pnls)[0, 1])

        except Exception as e:
            logger.error(f"Signal Performance Berechnung fehlgeschlagen: {e}")

        return performance

    def _compute_posterior_alphas(
        self, performance: dict[str, SignalPerformance]
    ) -> dict[str, float]:
        """
        Berechne Posterior Dirichlet Alpha-Werte.

        Formel: alpha_posterior = alpha_prior + accuracy_score * sqrt(n_trades)
        """
        new_alphas = {}

        for name in SIGNAL_NAMES:
            perf = performance.get(name)

            if perf and perf.total_trades > 0:
                # Kombiniere Accuracy und Korrelation
                accuracy_score = perf.accuracy
                correlation_bonus = max(0, perf.correlation_with_pnl) * 0.5

                # Gewichte basierend auf Sample Size (sqrt für diminishing returns)
                sample_weight = np.sqrt(perf.total_trades)

                # Posterior Update
                alpha_update = (accuracy_score + correlation_bonus) * sample_weight
                new_alphas[name] = PRIOR_STRENGTH + alpha_update
            else:
                # Kein Update, behalte Prior
                new_alphas[name] = PRIOR_STRENGTH

        return new_alphas

    def _normalize_weights(self, alphas: dict[str, float]) -> dict[str, float]:
        """
        Normalisiere Alpha-Werte zu Gewichten mit Min/Max Constraints.

        Verwendet Dirichlet Mean: E[θᵢ] = αᵢ / Σαⱼ
        """
        total_alpha = sum(alphas.values())

        if total_alpha == 0:
            return DEFAULT_WEIGHTS.copy()

        # Berechne Raw Weights
        raw_weights = {name: alpha / total_alpha for name, alpha in alphas.items()}

        # Apply Constraints
        constrained = {}
        for name, weight in raw_weights.items():
            constrained[name] = max(MIN_WEIGHT, min(MAX_WEIGHT, weight))

        # Re-Normalisiere
        total = sum(constrained.values())
        return {name: w / total for name, w in constrained.items()}

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def _load_weights_from_db(self):
        """Lade letzte Gewichte aus DB"""
        if not self.conn:
            return

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT weights, alpha_values FROM signal_weights
                    WHERE is_active = TRUE AND regime IS NULL
                    ORDER BY created_at DESC LIMIT 1
                """
                )
                row = cur.fetchone()

                if row:
                    if row["weights"]:
                        self.current_weights = dict(row["weights"])
                    if row["alpha_values"]:
                        self.alpha_values = dict(row["alpha_values"])

                    logger.info("Bayesian Weights aus DB geladen")

        except Exception as e:
            logger.debug(f"Weights load error (using defaults): {e}")

    def _store_weights(self, weights: BayesianWeights, cohort_id: str | None = None):
        """Speichere Gewichte in DB"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                # Deaktiviere alte Weights für dieses Regime
                cur.execute(
                    """
                    UPDATE signal_weights
                    SET is_active = FALSE
                    WHERE regime IS NOT DISTINCT FROM %s
                    AND cohort_id IS NOT DISTINCT FROM %s
                """,
                    (weights.regime, cohort_id),
                )

                # Füge neue ein
                import json

                cur.execute(
                    """
                    INSERT INTO signal_weights (
                        cohort_id, regime, weights, alpha_values,
                        confidence, sample_size, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                """,
                    (
                        cohort_id,
                        weights.regime,
                        json.dumps(weights.weights),
                        json.dumps(weights.alpha_values),
                        weights.confidence,
                        weights.sample_size,
                    ),
                )

                self.conn.commit()
                logger.info("Bayesian Weights gespeichert")

        except Exception as e:
            logger.error(f"Weights Speicherfehler: {e}")
            self.conn.rollback()

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS & REPORTING
    # ═══════════════════════════════════════════════════════════════

    def get_weight_history(self, days: int = 90, regime: str | None = None) -> list[dict[str, Any]]:
        """Hole Weight-Historie für Analyse"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT created_at, weights, confidence, sample_size, regime
                    FROM signal_weights
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                """
                params = [days]

                if regime:
                    query += " AND regime = %s"
                    params.append(regime)

                query += " ORDER BY created_at"

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Weight History Fehler: {e}")
            return []

    def get_weight_evolution(
        self, signal_name: str, days: int = 90
    ) -> list[tuple[datetime, float]]:
        """Hole Evolution eines einzelnen Signals"""
        history = self.get_weight_history(days)

        evolution = []
        for entry in history:
            weights = entry.get("weights", {})
            if signal_name in weights:
                evolution.append((entry["created_at"], weights[signal_name]))

        return evolution

    def compare_regimes(self) -> dict[str, dict[str, float]]:
        """Vergleiche Gewichte zwischen Regimes"""
        regimes = ["BULL", "BEAR", "SIDEWAYS"]
        comparison = {}

        for regime in regimes:
            weights = self._get_regime_weights(regime)
            if weights:
                comparison[regime] = weights

        # Füge Global hinzu
        comparison["GLOBAL"] = self.current_weights

        return comparison

    def get_signal_ranking(self, regime: str | None = None) -> list[tuple[str, float]]:
        """Ranking der Signale nach Gewicht"""
        weights = self.get_weights(regime)
        return sorted(weights.items(), key=lambda x: x[1], reverse=True)

    def calculate_expected_accuracy(self) -> float:
        """
        Berechne erwartete Accuracy basierend auf gewichteten Signalen.

        Diese Metrik zeigt wie gut die Gewichte die Accuracy widerspiegeln.
        """
        if not self.conn:
            return 0.0

        performance = self._calculate_signal_performance(None, 30, None)

        if not performance:
            return 0.0

        # Gewichtete Durchschnitts-Accuracy
        weighted_accuracy = 0.0
        for name, weight in self.current_weights.items():
            if name in performance:
                weighted_accuracy += weight * performance[name].accuracy

        return weighted_accuracy

    # ═══════════════════════════════════════════════════════════════
    # WEEKLY UPDATE TASK
    # ═══════════════════════════════════════════════════════════════

    def weekly_update(self) -> dict[str, Any]:
        """
        Wöchentliches Weight Update für alle Cohorts und Regimes.

        Wird vom Scheduler aufgerufen.
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "updates": [],
            "errors": [],
        }

        # 1. Globales Update
        try:
            global_weights = self.update_weights(lookback_days=30)
            results["updates"].append(
                {
                    "type": "global",
                    "weights": global_weights.weights,
                    "confidence": global_weights.confidence,
                    "sample_size": global_weights.sample_size,
                }
            )
        except Exception as e:
            results["errors"].append(f"Global update failed: {e}")

        # 2. Regime-spezifische Updates
        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            try:
                regime_weights = self.update_weights(lookback_days=60, regime=regime)
                if regime_weights.sample_size >= MIN_TRADES_FOR_UPDATE:
                    results["updates"].append(
                        {
                            "type": f"regime_{regime}",
                            "weights": regime_weights.weights,
                            "confidence": regime_weights.confidence,
                            "sample_size": regime_weights.sample_size,
                        }
                    )
            except Exception as e:
                results["errors"].append(f"Regime {regime} update failed: {e}")

        # 3. Cohort-spezifische Updates
        cohort_ids = self._get_active_cohort_ids()
        for cohort_id in cohort_ids:
            try:
                cohort_weights = self.update_weights(cohort_id=cohort_id, lookback_days=30)
                if cohort_weights.sample_size >= MIN_TRADES_FOR_UPDATE:
                    results["updates"].append(
                        {
                            "type": f"cohort_{cohort_id[:8]}",
                            "weights": cohort_weights.weights,
                            "confidence": cohort_weights.confidence,
                            "sample_size": cohort_weights.sample_size,
                        }
                    )
            except Exception as e:
                results["errors"].append(f"Cohort {cohort_id[:8]} update failed: {e}")

        logger.info(
            f"Weekly Bayesian Update: {len(results['updates'])} updates, "
            f"{len(results['errors'])} errors"
        )

        return results

    def _get_active_cohort_ids(self) -> list[str]:
        """Hole IDs aller aktiven Cohorts"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT id::text FROM cohorts WHERE is_active = TRUE")
                return [row[0] for row in cur.fetchall()]

        except Exception as e:
            logger.debug(f"Cohort IDs fetch error: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════
    # SIGNAL COMBINATION
    # ═══════════════════════════════════════════════════════════════

    def combine_signals(
        self,
        signals: dict[str, float],
        regime: str | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        Kombiniere mehrere Signale mit Bayesian Weights.

        Args:
            signals: Dict mit Signal-Namen und Werten (-1 bis +1)
            regime: Optional Markt-Regime

        Returns:
            (combined_score, weighted_contributions)
        """
        weights = self.get_weights(regime)

        combined = 0.0
        contributions = {}

        for name, weight in weights.items():
            signal_value = signals.get(name, 0.0)
            contribution = weight * signal_value

            combined += contribution
            contributions[name] = contribution

        # Normalisiere auf -1 bis +1
        combined = max(-1.0, min(1.0, combined))

        return combined, contributions

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
