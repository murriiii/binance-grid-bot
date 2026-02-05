"""
A/B Testing Framework für Trading-Strategien

Ermöglicht systematischen Vergleich von:
- Signal-Gewichten
- Grid-Parametern
- Risiko-Einstellungen
- Timing-Strategien

Statistische Methoden:
- Welch's t-Test für Mittelwert-Vergleich
- Mann-Whitney U Test für nicht-normale Verteilungen
- Bootstrap Confidence Intervals
- Bayes Factor für Evidenz-Stärke

Features:
- Automatische Experiment-Erstellung
- Multi-Varianten Testing (A/B/C/D)
- Sequential Analysis (frühes Stoppen möglich)
- Automatisches Promoten des Gewinners
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
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
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy nicht verfügbar - eingeschränkte statistische Tests")


class ExperimentStatus(Enum):
    """Status eines Experiments"""

    DRAFT = "DRAFT"  # Noch nicht gestartet
    RUNNING = "RUNNING"  # Aktiv
    PAUSED = "PAUSED"  # Pausiert
    COMPLETED = "COMPLETED"  # Fertig
    TERMINATED = "TERMINATED"  # Vorzeitig beendet


class VariantStatus(Enum):
    """Status einer Variante"""

    ACTIVE = "ACTIVE"
    WINNER = "WINNER"
    LOSER = "LOSER"
    PROMOTED = "PROMOTED"


class SignificanceLevel(Enum):
    """Signifikanz-Level"""

    HIGHLY_SIGNIFICANT = "HIGHLY_SIGNIFICANT"  # p < 0.01
    SIGNIFICANT = "SIGNIFICANT"  # p < 0.05
    MARGINALLY_SIGNIFICANT = "MARGINALLY_SIGNIFICANT"  # p < 0.10
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"  # p >= 0.10


@dataclass
class Variant:
    """Eine Test-Variante"""

    id: str
    name: str
    config: dict[str, Any]  # Zu testende Parameter
    cohort_id: str | None = None  # Optionale Cohort-Zuordnung

    # Performance-Daten
    sample_size: int = 0
    total_pnl: float = 0.0
    mean_pnl: float = 0.0
    std_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    # Status
    status: VariantStatus = VariantStatus.ACTIVE
    trades: list[float] = field(default_factory=list)


@dataclass
class StatisticalResult:
    """Ergebnis eines statistischen Tests"""

    test_name: str
    p_value: float
    significance: SignificanceLevel
    effect_size: float  # Cohen's d oder ähnlich
    confidence_interval: tuple[float, float]
    winner: str | None  # Name der besseren Variante
    winner_improvement: float  # Prozentuale Verbesserung


@dataclass
class Experiment:
    """Ein A/B Test Experiment"""

    id: str
    name: str
    description: str
    hypothesis: str  # Was wir testen wollen

    # Varianten
    control: Variant  # Baseline
    treatments: list[Variant]  # Zu testende Varianten

    # Konfiguration
    metric: str  # Primäre Metrik (pnl, sharpe, win_rate)
    min_sample_size: int  # Minimum pro Variante
    max_duration_days: int  # Maximum Laufzeit
    alpha: float = 0.05  # Signifikanz-Level

    # Status
    status: ExperimentStatus = ExperimentStatus.DRAFT
    start_date: datetime | None = None
    end_date: datetime | None = None

    # Ergebnisse
    results: StatisticalResult | None = None
    winner: str | None = None


# Konfiguration
DEFAULT_MIN_SAMPLE_SIZE = 30  # Minimum für statistische Aussagekraft
DEFAULT_MAX_DURATION = 14  # Tage
DEFAULT_ALPHA = 0.05  # Signifikanz-Level


class ABTestingFramework:
    """
    Framework für A/B Testing von Trading-Strategien.

    Features:
    1. Experiment-Management
    2. Statistische Analyse
    3. Automatische Gewinner-Erkennung
    4. Promotion der besten Variante
    """

    _instance = None

    def __init__(self):
        self.conn = None
        self.experiments: dict[str, Experiment] = {}
        self._connect_db()
        self._load_experiments()

    @classmethod
    def get_instance(cls) -> "ABTestingFramework":
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
                logger.info("ABTestingFramework: DB verbunden")
        except Exception as e:
            logger.error(f"ABTestingFramework: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # EXPERIMENT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def create_experiment(
        self,
        name: str,
        description: str,
        hypothesis: str,
        control_config: dict[str, Any],
        treatment_configs: list[dict[str, Any]],
        metric: str = "pnl",
        min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
        max_duration_days: int = DEFAULT_MAX_DURATION,
        control_cohort_id: str | None = None,
        treatment_cohort_ids: list[str] | None = None,
    ) -> Experiment:
        """
        Erstelle ein neues A/B Test Experiment.

        Args:
            name: Experiment-Name
            description: Beschreibung
            hypothesis: Was wir testen (z.B. "Höhere RSI-Gewichtung verbessert Performance")
            control_config: Baseline-Konfiguration
            treatment_configs: Liste von Test-Konfigurationen
            metric: Primäre Metrik
            min_sample_size: Minimum Trades pro Variante
            max_duration_days: Maximum Laufzeit
            control_cohort_id: Optional - Cohort für Control
            treatment_cohort_ids: Optional - Cohorts für Treatments

        Returns:
            Experiment Objekt
        """
        experiment_id = str(uuid.uuid4())

        # Control Variante
        control = Variant(
            id=str(uuid.uuid4()),
            name="control",
            config=control_config,
            cohort_id=control_cohort_id,
        )

        # Treatment Varianten
        treatments = []
        for i, config in enumerate(treatment_configs):
            cohort_id = (
                treatment_cohort_ids[i]
                if treatment_cohort_ids and i < len(treatment_cohort_ids)
                else None
            )
            treatments.append(
                Variant(
                    id=str(uuid.uuid4()),
                    name=f"treatment_{chr(65 + i)}",  # A, B, C, ...
                    config=config,
                    cohort_id=cohort_id,
                )
            )

        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            hypothesis=hypothesis,
            control=control,
            treatments=treatments,
            metric=metric,
            min_sample_size=min_sample_size,
            max_duration_days=max_duration_days,
        )

        self.experiments[experiment_id] = experiment
        self._store_experiment(experiment)

        logger.info(f"Experiment erstellt: {name} mit {len(treatments)} Treatments")

        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """Starte ein Experiment"""
        if experiment_id not in self.experiments:
            logger.error(f"Experiment {experiment_id} nicht gefunden")
            return False

        exp = self.experiments[experiment_id]

        if exp.status != ExperimentStatus.DRAFT:
            logger.warning(f"Experiment {exp.name} ist nicht im DRAFT Status")
            return False

        exp.status = ExperimentStatus.RUNNING
        exp.start_date = datetime.now()

        self._update_experiment_status(experiment_id, ExperimentStatus.RUNNING)

        logger.info(f"Experiment gestartet: {exp.name}")
        return True

    def pause_experiment(self, experiment_id: str) -> bool:
        """Pausiere ein Experiment"""
        if experiment_id not in self.experiments:
            return False

        exp = self.experiments[experiment_id]
        if exp.status == ExperimentStatus.RUNNING:
            exp.status = ExperimentStatus.PAUSED
            self._update_experiment_status(experiment_id, ExperimentStatus.PAUSED)
            return True

        return False

    def resume_experiment(self, experiment_id: str) -> bool:
        """Setze ein pausiertes Experiment fort"""
        if experiment_id not in self.experiments:
            return False

        exp = self.experiments[experiment_id]
        if exp.status == ExperimentStatus.PAUSED:
            exp.status = ExperimentStatus.RUNNING
            self._update_experiment_status(experiment_id, ExperimentStatus.RUNNING)
            return True

        return False

    def complete_experiment(
        self, experiment_id: str, promote_winner: bool = False
    ) -> StatisticalResult | None:
        """
        Beende ein Experiment und analysiere Ergebnisse.

        Args:
            experiment_id: Experiment ID
            promote_winner: Automatisch Gewinner promoten

        Returns:
            StatisticalResult oder None
        """
        if experiment_id not in self.experiments:
            return None

        exp = self.experiments[experiment_id]

        # Analysiere Ergebnisse
        result = self.analyze_experiment(experiment_id)

        if result:
            exp.results = result
            exp.winner = result.winner
            exp.status = ExperimentStatus.COMPLETED
            exp.end_date = datetime.now()

            self._store_experiment(exp)

            # Optional: Gewinner promoten
            if promote_winner and result.winner:
                self._promote_winner(exp, result.winner)

            logger.info(
                f"Experiment abgeschlossen: {exp.name}, "
                f"Gewinner: {result.winner}, p={result.p_value:.4f}"
            )

        return result

    # ═══════════════════════════════════════════════════════════════
    # DATA COLLECTION
    # ═══════════════════════════════════════════════════════════════

    def record_trade(
        self,
        experiment_id: str,
        variant_name: str,
        pnl: float,
        additional_metrics: dict[str, float] | None = None,
    ):
        """
        Zeichne einen Trade für eine Variante auf.

        Args:
            experiment_id: Experiment ID
            variant_name: "control" oder "treatment_A", "treatment_B", etc.
            pnl: Profit/Loss des Trades
            additional_metrics: Optionale zusätzliche Metriken
        """
        if experiment_id not in self.experiments:
            return

        exp = self.experiments[experiment_id]

        if exp.status != ExperimentStatus.RUNNING:
            return

        # Finde Variante
        variant = None
        if variant_name == "control":
            variant = exp.control
        else:
            for t in exp.treatments:
                if t.name == variant_name:
                    variant = t
                    break

        if variant is None:
            logger.warning(f"Variante {variant_name} nicht gefunden")
            return

        # Aktualisiere Statistiken
        variant.trades.append(pnl)
        variant.sample_size = len(variant.trades)
        variant.total_pnl = sum(variant.trades)
        variant.mean_pnl = np.mean(variant.trades)
        variant.std_pnl = np.std(variant.trades) if len(variant.trades) > 1 else 0
        variant.win_rate = len([t for t in variant.trades if t > 0]) / len(variant.trades)

        # Speichere in DB
        self._store_trade_record(experiment_id, variant.id, pnl, additional_metrics)

    def load_trades_from_db(self, experiment_id: str):
        """Lade Trade-Daten aus DB für ein Experiment"""
        if not self.conn or experiment_id not in self.experiments:
            return

        exp = self.experiments[experiment_id]

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Lade Trades für Control
                cur.execute(
                    """
                    SELECT pnl FROM ab_test_trades
                    WHERE experiment_id = %s AND variant_id = %s
                    ORDER BY created_at
                """,
                    (experiment_id, exp.control.id),
                )
                exp.control.trades = [float(row["pnl"]) for row in cur.fetchall()]
                self._update_variant_stats(exp.control)

                # Lade Trades für Treatments
                for treatment in exp.treatments:
                    cur.execute(
                        """
                        SELECT pnl FROM ab_test_trades
                        WHERE experiment_id = %s AND variant_id = %s
                        ORDER BY created_at
                    """,
                        (experiment_id, treatment.id),
                    )
                    treatment.trades = [float(row["pnl"]) for row in cur.fetchall()]
                    self._update_variant_stats(treatment)

        except Exception as e:
            logger.error(f"Trade Load Fehler: {e}")

    def _update_variant_stats(self, variant: Variant):
        """Aktualisiere Statistiken einer Variante"""
        if not variant.trades:
            return

        variant.sample_size = len(variant.trades)
        variant.total_pnl = sum(variant.trades)
        variant.mean_pnl = np.mean(variant.trades)
        variant.std_pnl = np.std(variant.trades) if len(variant.trades) > 1 else 0
        variant.win_rate = len([t for t in variant.trades if t > 0]) / len(variant.trades)

    # ═══════════════════════════════════════════════════════════════
    # STATISTICAL ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def analyze_experiment(self, experiment_id: str) -> StatisticalResult | None:
        """
        Führe statistische Analyse eines Experiments durch.

        Verwendet:
        - Welch's t-Test (robuster bei ungleichen Varianzen)
        - Cohen's d für Effect Size
        - Bootstrap CI wenn scipy nicht verfügbar
        """
        if experiment_id not in self.experiments:
            return None

        exp = self.experiments[experiment_id]

        # Lade aktuelle Daten
        self.load_trades_from_db(experiment_id)

        # Prüfe Minimum Sample Size
        if exp.control.sample_size < exp.min_sample_size:
            logger.info(
                f"Nicht genug Daten für Analyse "
                f"(Control: {exp.control.sample_size}/{exp.min_sample_size})"
            )
            return None

        # Finde beste Treatment
        best_treatment = None
        best_mean = exp.control.mean_pnl

        for treatment in exp.treatments:
            if treatment.sample_size >= exp.min_sample_size and treatment.mean_pnl > best_mean:
                best_mean = treatment.mean_pnl
                best_treatment = treatment

        if best_treatment is None:
            # Kein Treatment besser als Control
            return StatisticalResult(
                test_name="welch_t_test",
                p_value=1.0,
                significance=SignificanceLevel.NOT_SIGNIFICANT,
                effect_size=0.0,
                confidence_interval=(0.0, 0.0),
                winner="control",
                winner_improvement=0.0,
            )

        # Statistischer Test
        result = self._compare_variants(exp.control, best_treatment, exp.alpha)

        return result

    def _compare_variants(
        self, control: Variant, treatment: Variant, alpha: float
    ) -> StatisticalResult:
        """Vergleiche zwei Varianten statistisch"""

        if SCIPY_AVAILABLE:
            # Welch's t-Test (ungleiche Varianzen)
            _t_stat, p_value = stats.ttest_ind(treatment.trades, control.trades, equal_var=False)

            # Mann-Whitney U als Backup für nicht-normale Daten
            try:
                _u_stat, p_value_mw = stats.mannwhitneyu(
                    treatment.trades, control.trades, alternative="greater"
                )
                # Nehme konservativeren p-Wert
                p_value = max(p_value / 2, p_value_mw)  # one-tailed
            except Exception:
                pass

        else:
            # Fallback: Einfacher z-Test
            p_value = self._simple_z_test(control, treatment)

        # Effect Size (Cohen's d)
        pooled_std = np.sqrt(
            (
                (control.sample_size - 1) * control.std_pnl**2
                + (treatment.sample_size - 1) * treatment.std_pnl**2
            )
            / (control.sample_size + treatment.sample_size - 2)
        )
        effect_size = (treatment.mean_pnl - control.mean_pnl) / pooled_std if pooled_std > 0 else 0

        # Confidence Interval (Bootstrap)
        ci = self._bootstrap_ci(control.trades, treatment.trades)

        # Signifikanz-Level
        if p_value < 0.01:
            significance = SignificanceLevel.HIGHLY_SIGNIFICANT
        elif p_value < 0.05:
            significance = SignificanceLevel.SIGNIFICANT
        elif p_value < 0.10:
            significance = SignificanceLevel.MARGINALLY_SIGNIFICANT
        else:
            significance = SignificanceLevel.NOT_SIGNIFICANT

        # Gewinner bestimmen
        if p_value < alpha and treatment.mean_pnl > control.mean_pnl:
            winner = treatment.name
            improvement = (
                (treatment.mean_pnl - control.mean_pnl) / abs(control.mean_pnl) * 100
                if control.mean_pnl != 0
                else 0
            )
        else:
            winner = "control"
            improvement = 0.0

        return StatisticalResult(
            test_name="welch_t_test",
            p_value=p_value,
            significance=significance,
            effect_size=effect_size,
            confidence_interval=ci,
            winner=winner,
            winner_improvement=improvement,
        )

    def _simple_z_test(self, control: Variant, treatment: Variant) -> float:
        """Einfacher z-Test als Fallback"""
        mean_diff = treatment.mean_pnl - control.mean_pnl

        se = np.sqrt(
            (control.std_pnl**2 / control.sample_size)
            + (treatment.std_pnl**2 / treatment.sample_size)
        )

        if se == 0:
            return 1.0

        z = mean_diff / se

        # Approximation der p-Value (two-tailed)
        p_value = 2 * (1 - self._normal_cdf(abs(z)))

        return p_value

    def _normal_cdf(self, x: float) -> float:
        """Approximation der Normal CDF"""
        # Abramowitz and Stegun approximation
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911

        sign = 1 if x >= 0 else -1
        x = abs(x) / np.sqrt(2)

        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * np.exp(-x * x)

        return 0.5 * (1.0 + sign * y)

    def _bootstrap_ci(
        self,
        control_trades: list[float],
        treatment_trades: list[float],
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """Bootstrap Confidence Interval für Mean-Differenz"""
        differences = []

        for _ in range(n_bootstrap):
            control_sample = np.random.choice(
                control_trades, size=len(control_trades), replace=True
            )
            treatment_sample = np.random.choice(
                treatment_trades, size=len(treatment_trades), replace=True
            )
            differences.append(np.mean(treatment_sample) - np.mean(control_sample))

        alpha = 1 - confidence
        lower = np.percentile(differences, alpha / 2 * 100)
        upper = np.percentile(differences, (1 - alpha / 2) * 100)

        return (lower, upper)

    # ═══════════════════════════════════════════════════════════════
    # SEQUENTIAL ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def check_early_stopping(
        self, experiment_id: str, min_effect_size: float = 0.5
    ) -> tuple[bool, str]:
        """
        Prüfe ob Experiment früh beendet werden kann.

        Sequential Analysis ermöglicht:
        - Frühes Stoppen bei klarem Gewinner
        - Frühes Stoppen bei Futility (kein Unterschied erkennbar)

        Returns:
            (should_stop, reason)
        """
        if experiment_id not in self.experiments:
            return False, "Experiment nicht gefunden"

        exp = self.experiments[experiment_id]
        self.load_trades_from_db(experiment_id)

        # Minimum Samples erreicht?
        if exp.control.sample_size < exp.min_sample_size // 2:
            return False, "Nicht genug Daten"

        # Analyse
        result = self.analyze_experiment(experiment_id)

        if result is None:
            return False, "Analyse nicht möglich"

        # Frühes Stoppen bei sehr hoher Signifikanz
        if result.p_value < 0.001 and abs(result.effect_size) > min_effect_size:
            return True, f"Klarer Gewinner: {result.winner} (p={result.p_value:.4f})"

        # Futility Check: Kein Effekt erkennbar
        if (
            exp.control.sample_size >= exp.min_sample_size
            and result.p_value > 0.5
            and abs(result.effect_size) < 0.1
        ):
            return True, "Futility: Kein signifikanter Unterschied erkennbar"

        # Maximum Duration erreicht
        if exp.start_date:
            days_running = (datetime.now() - exp.start_date).days
            if days_running >= exp.max_duration_days:
                return True, f"Maximum Duration erreicht ({days_running} Tage)"

        return False, "Weiter laufen lassen"

    # ═══════════════════════════════════════════════════════════════
    # WINNER PROMOTION
    # ═══════════════════════════════════════════════════════════════

    def _promote_winner(self, experiment: Experiment, winner_name: str):
        """
        Promote die gewinnende Variante zur neuen Baseline.

        Dies aktualisiert die Cohort-Konfiguration.
        """
        # Finde Gewinner-Variante
        winner_config = None
        if winner_name == "control":
            winner_config = experiment.control.config
        else:
            for t in experiment.treatments:
                if t.name == winner_name:
                    winner_config = t.config
                    t.status = VariantStatus.PROMOTED
                    break

        if winner_config is None:
            logger.error(f"Gewinner {winner_name} nicht gefunden")
            return

        # Speichere als neue Baseline
        self._store_promoted_config(experiment.id, winner_name, winner_config)

        logger.info(f"Gewinner {winner_name} promoted mit Config: {winner_config}")

    def _store_promoted_config(self, experiment_id: str, winner_name: str, config: dict[str, Any]):
        """Speichere promovierte Konfiguration"""
        if not self.conn:
            return

        try:
            import json

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO promoted_configs (
                        experiment_id, winner_name, config, promoted_at
                    ) VALUES (%s, %s, %s, NOW())
                """,
                    (experiment_id, winner_name, json.dumps(config)),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Config Promotion Fehler (table may not exist): {e}")
            self.conn.rollback()

    # ═══════════════════════════════════════════════════════════════
    # REPORTING
    # ═══════════════════════════════════════════════════════════════

    def get_experiment_summary(self, experiment_id: str) -> dict[str, Any]:
        """Hole Zusammenfassung eines Experiments"""
        if experiment_id not in self.experiments:
            return {}

        exp = self.experiments[experiment_id]
        self.load_trades_from_db(experiment_id)

        summary = {
            "id": exp.id,
            "name": exp.name,
            "status": exp.status.value,
            "hypothesis": exp.hypothesis,
            "metric": exp.metric,
            "start_date": exp.start_date.isoformat() if exp.start_date else None,
            "duration_days": ((datetime.now() - exp.start_date).days if exp.start_date else 0),
            "variants": {},
        }

        # Control
        summary["variants"]["control"] = {
            "sample_size": exp.control.sample_size,
            "mean_pnl": exp.control.mean_pnl,
            "std_pnl": exp.control.std_pnl,
            "win_rate": exp.control.win_rate,
            "total_pnl": exp.control.total_pnl,
        }

        # Treatments
        for t in exp.treatments:
            summary["variants"][t.name] = {
                "sample_size": t.sample_size,
                "mean_pnl": t.mean_pnl,
                "std_pnl": t.std_pnl,
                "win_rate": t.win_rate,
                "total_pnl": t.total_pnl,
                "vs_control": (
                    (t.mean_pnl - exp.control.mean_pnl) / abs(exp.control.mean_pnl) * 100
                    if exp.control.mean_pnl != 0
                    else 0
                ),
            }

        # Ergebnisse
        if exp.results:
            summary["results"] = {
                "winner": exp.results.winner,
                "p_value": exp.results.p_value,
                "significance": exp.results.significance.value,
                "effect_size": exp.results.effect_size,
                "improvement_pct": exp.results.winner_improvement,
            }

        return summary

    def get_all_experiments_summary(self) -> list[dict[str, Any]]:
        """Hole Zusammenfassung aller Experimente"""
        return [self.get_experiment_summary(exp_id) for exp_id in self.experiments]

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def _load_experiments(self):
        """Lade Experimente aus DB"""
        if not self.conn:
            return

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM ab_experiments
                    WHERE status != 'TERMINATED'
                    ORDER BY created_at DESC
                """
                )

                for row in cur.fetchall():
                    # Rekonstruiere Experiment
                    exp = self._row_to_experiment(row)
                    if exp:
                        self.experiments[exp.id] = exp

            logger.info(f"ABTesting: {len(self.experiments)} Experimente geladen")

        except Exception as e:
            logger.debug(f"Experiment Load Fehler (table may not exist): {e}")

    def _row_to_experiment(self, row: dict) -> Experiment | None:
        """Konvertiere DB Row zu Experiment"""
        try:
            import json

            control_config = row.get("control_config", {})
            if isinstance(control_config, str):
                control_config = json.loads(control_config)

            treatment_configs = row.get("treatment_configs", [])
            if isinstance(treatment_configs, str):
                treatment_configs = json.loads(treatment_configs)

            control = Variant(
                id=row.get("control_id", str(uuid.uuid4())),
                name="control",
                config=control_config,
            )

            treatments = []
            for i, config in enumerate(treatment_configs):
                treatments.append(
                    Variant(
                        id=str(uuid.uuid4()),
                        name=f"treatment_{chr(65 + i)}",
                        config=config,
                    )
                )

            return Experiment(
                id=row["id"],
                name=row["name"],
                description=row.get("description", ""),
                hypothesis=row.get("hypothesis", ""),
                control=control,
                treatments=treatments,
                metric=row.get("metric", "pnl"),
                min_sample_size=row.get("min_sample_size", DEFAULT_MIN_SAMPLE_SIZE),
                max_duration_days=row.get("max_duration_days", DEFAULT_MAX_DURATION),
                status=ExperimentStatus(row.get("status", "DRAFT")),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
            )

        except Exception as e:
            logger.error(f"Experiment Parse Fehler: {e}")
            return None

    def _store_experiment(self, experiment: Experiment):
        """Speichere Experiment in DB"""
        if not self.conn:
            return

        try:
            import json

            treatment_configs = [t.config for t in experiment.treatments]

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ab_experiments (
                        id, name, description, hypothesis,
                        control_id, control_config, treatment_configs,
                        metric, min_sample_size, max_duration_days,
                        status, start_date, end_date, winner
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        winner = EXCLUDED.winner
                """,
                    (
                        experiment.id,
                        experiment.name,
                        experiment.description,
                        experiment.hypothesis,
                        experiment.control.id,
                        json.dumps(experiment.control.config),
                        json.dumps(treatment_configs),
                        experiment.metric,
                        experiment.min_sample_size,
                        experiment.max_duration_days,
                        experiment.status.value,
                        experiment.start_date,
                        experiment.end_date,
                        experiment.winner,
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Experiment Store Fehler (table may not exist): {e}")
            self.conn.rollback()

    def _update_experiment_status(self, experiment_id: str, status: ExperimentStatus):
        """Update nur den Status eines Experiments"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ab_experiments
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                """,
                    (status.value, experiment_id),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Status Update Fehler: {e}")
            self.conn.rollback()

    def _store_trade_record(
        self,
        experiment_id: str,
        variant_id: str,
        pnl: float,
        additional_metrics: dict[str, float] | None,
    ):
        """Speichere Trade-Record für A/B Test"""
        if not self.conn:
            return

        try:
            import json

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ab_test_trades (
                        experiment_id, variant_id, pnl, additional_metrics
                    ) VALUES (%s, %s, %s, %s)
                """,
                    (
                        experiment_id,
                        variant_id,
                        pnl,
                        json.dumps(additional_metrics) if additional_metrics else None,
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Trade Record Fehler (table may not exist): {e}")
            self.conn.rollback()

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
