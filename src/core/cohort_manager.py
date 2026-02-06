"""
Cohort Manager - Verwaltet parallele Strategie-Varianten

Ermöglicht gleichzeitiges Testen mehrerer Strategien:
- Conservative: Enge Grids, hohe Confidence
- Balanced: Standard, Playbook-gesteuert
- Aggressive: Weite Grids, höheres Risiko
- Baseline: Unveränderte Kontrolle

Jede Cohort hat:
- Eigenes Kapital ($1000)
- Eigene Konfiguration
- Eigene Performance-Metriken
- Unabhängige Zyklen
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
    logger.warning("psycopg2 nicht installiert - pip install psycopg2-binary")


@dataclass
class CohortConfig:
    """Konfiguration für eine Cohort"""

    grid_range_pct: float = 5.0
    min_confidence: float = 0.5
    min_fear_greed: int = 0
    max_fear_greed: int = 100
    use_playbook: bool = True
    risk_tolerance: str = "medium"  # low, medium, high
    frozen: bool = False  # True für Baseline (keine Änderungen)

    @classmethod
    def from_json(cls, config_json: dict) -> "CohortConfig":
        """Erstelle CohortConfig aus JSON"""
        return cls(
            grid_range_pct=config_json.get("grid_range_pct", 5.0),
            min_confidence=config_json.get("min_confidence", 0.5),
            min_fear_greed=config_json.get("min_fear_greed", 0),
            max_fear_greed=config_json.get("max_fear_greed", 100),
            use_playbook=config_json.get("use_playbook", True),
            risk_tolerance=config_json.get("risk_tolerance", "medium"),
            frozen=config_json.get("frozen", False),
        )

    def to_json(self) -> dict:
        """Konvertiere zu JSON"""
        return {
            "grid_range_pct": self.grid_range_pct,
            "min_confidence": self.min_confidence,
            "min_fear_greed": self.min_fear_greed,
            "max_fear_greed": self.max_fear_greed,
            "use_playbook": self.use_playbook,
            "risk_tolerance": self.risk_tolerance,
            "frozen": self.frozen,
        }


@dataclass
class Cohort:
    """Repräsentiert eine Strategie-Variante"""

    id: str
    name: str
    description: str
    config: CohortConfig
    starting_capital: float
    current_capital: float
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def should_trade(self, confidence: float, fear_greed: int) -> bool:
        """Prüft ob diese Cohort bei den aktuellen Bedingungen traden sollte"""
        if not self.is_active:
            return False

        if confidence < self.config.min_confidence:
            return False

        if fear_greed < self.config.min_fear_greed:
            return False

        return not fear_greed > self.config.max_fear_greed


class CohortManager(SingletonMixin):
    """
    Verwaltet parallele Strategie-Varianten für A/B/C/D Testing.

    Features:
    1. Lädt Cohorts aus der Datenbank
    2. Entscheidet welche Cohorts traden sollten
    3. Trackt Performance pro Cohort
    4. Ermöglicht Vergleich zwischen Strategien
    """

    def __init__(self):
        self.conn = None
        self.cohorts: dict[str, Cohort] = {}
        self._connect()
        self._load_cohorts()

    def _connect(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - CohortManager deaktiviert")
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                logger.warning("DATABASE_URL nicht gesetzt")
                return

            self.conn = psycopg2.connect(database_url)
            logger.info("CohortManager: PostgreSQL verbunden")
        except Exception as e:
            logger.error(f"CohortManager: DB Verbindung fehlgeschlagen: {e}")
            self.conn = None

    def _load_cohorts(self):
        """Lade alle aktiven Cohorts aus der Datenbank"""
        if not self.conn:
            self._create_default_cohorts()
            return

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, name, description, config, starting_capital,
                           current_capital, is_active, created_at
                    FROM cohorts
                    WHERE is_active = true
                """)
                rows = cur.fetchall()

                for row in rows:
                    cohort = Cohort(
                        id=str(row["id"]),
                        name=row["name"],
                        description=row["description"] or "",
                        config=CohortConfig.from_json(row["config"]),
                        starting_capital=float(row["starting_capital"]),
                        current_capital=float(row["current_capital"]),
                        is_active=row["is_active"],
                        created_at=row["created_at"],
                    )
                    self.cohorts[cohort.name] = cohort

                logger.info(f"CohortManager: {len(self.cohorts)} Cohorts geladen")

        except Exception as e:
            logger.error(f"CohortManager: Fehler beim Laden: {e}")
            self._create_default_cohorts()

    def _create_default_cohorts(self):
        """Erstelle Standard-Cohorts im Memory (falls DB nicht verfügbar)"""
        defaults = [
            (
                "conservative",
                "Konservativ: Enge Grids, hohe Confidence",
                CohortConfig(
                    grid_range_pct=2.0, min_confidence=0.7, max_fear_greed=40, risk_tolerance="low"
                ),
            ),
            (
                "balanced",
                "Ausgewogen: Standard Grids, Playbook-gesteuert",
                CohortConfig(grid_range_pct=5.0, min_confidence=0.5, use_playbook=True),
            ),
            (
                "aggressive",
                "Aggressiv: Weite Grids, höheres Risiko",
                CohortConfig(grid_range_pct=8.0, min_confidence=0.3, risk_tolerance="high"),
            ),
            (
                "baseline",
                "Baseline: Kontrolle ohne Änderungen",
                CohortConfig(grid_range_pct=5.0, min_confidence=0.5, frozen=True),
            ),
        ]

        for name, desc, config in defaults:
            self.cohorts[name] = Cohort(
                id=f"default-{name}",
                name=name,
                description=desc,
                config=config,
                starting_capital=1000.0,
                current_capital=1000.0,
            )

        logger.info("CohortManager: Default Cohorts erstellt (Memory-Mode)")

    def get_cohort(self, name: str) -> Cohort | None:
        """Hole Cohort nach Name"""
        return self.cohorts.get(name)

    def get_active_cohorts(self) -> list[Cohort]:
        """Hole alle aktiven Cohorts"""
        return [c for c in self.cohorts.values() if c.is_active]

    def get_trading_cohorts(self, confidence: float, fear_greed: int) -> list[Cohort]:
        """Hole alle Cohorts die bei den aktuellen Bedingungen traden sollten"""
        return [c for c in self.get_active_cohorts() if c.should_trade(confidence, fear_greed)]

    def update_capital(self, cohort_name: str, new_capital: float):
        """Aktualisiere das Kapital einer Cohort"""
        if cohort_name not in self.cohorts:
            logger.warning(f"Cohort '{cohort_name}' nicht gefunden")
            return

        self.cohorts[cohort_name].current_capital = new_capital

        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cohorts
                    SET current_capital = %s, updated_at = NOW()
                    WHERE name = %s
                """,
                    (new_capital, cohort_name),
                )
                self.conn.commit()
        except Exception as e:
            logger.error(f"CohortManager: Fehler beim Kapital-Update: {e}")
            self.conn.rollback()

    def get_cohort_stats(self, cohort_name: str) -> dict[str, Any] | None:
        """Hole Statistiken für eine Cohort"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        c.name,
                        c.current_capital,
                        c.starting_capital,
                        COUNT(t.id) as total_trades,
                        SUM(CASE WHEN t.was_good_decision THEN 1 ELSE 0 END) as winning_trades,
                        AVG(t.outcome_24h) as avg_return_24h,
                        MAX(tc.sharpe_ratio) as best_sharpe,
                        COUNT(DISTINCT tc.id) as completed_cycles
                    FROM cohorts c
                    LEFT JOIN trades t ON t.cohort_id = c.id
                    LEFT JOIN trading_cycles tc ON tc.cohort_id = c.id AND tc.status = 'completed'
                    WHERE c.name = %s
                    GROUP BY c.id, c.name, c.current_capital, c.starting_capital
                """,
                    (cohort_name,),
                )

                row = cur.fetchone()
                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"CohortManager: Fehler beim Stats-Abruf: {e}")
            return None

    def get_comparison_report(self) -> list[dict[str, Any]]:
        """Erstelle Vergleichsreport aller Cohorts"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM v_cohort_comparison
                    ORDER BY cycle_number DESC, total_pnl_pct DESC
                    LIMIT 50
                """)
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"CohortManager: Fehler beim Comparison Report: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
