"""
Cycle Manager - Verwaltet wöchentliche Trading-Zyklen

Jeder Zyklus:
- Läuft 7 Tage
- Startet mit definiertem Kapital ($1000)
- Trackt Performance unabhängig
- Ermöglicht Woche-zu-Woche Vergleich

Am Ende jedes Zyklus:
- Berechne alle Metriken (Sharpe, Sortino, etc.)
- Vergleiche mit vorherigen Zyklen
- Identifiziere Verbesserungen/Verschlechterungen
- Update Playbook basierend auf Learnings
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
class TradingCycle:
    """Repräsentiert einen Trading-Zyklus"""

    id: str
    cohort_id: str
    cohort_name: str
    cycle_number: int
    start_date: datetime
    end_date: datetime | None
    status: str  # active, completed, cancelled

    # Capital
    starting_capital: float
    ending_capital: float | None
    trades_count: int = 0

    # Performance (calculated on close)
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown: float | None = None

    # Risk Metrics
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    kelly_fraction: float | None = None
    var_95: float | None = None
    cvar_95: float | None = None

    # Market Context
    avg_fear_greed: float | None = None
    dominant_regime: str | None = None
    btc_performance_pct: float | None = None

    # Playbook
    playbook_version_at_start: int | None = None
    playbook_version_at_end: int | None = None


class CycleManager:
    """
    Verwaltet wöchentliche Trading-Zyklen pro Cohort.

    Features:
    1. Startet neue Zyklen (jeden Sonntag 00:00)
    2. Beendet laufende Zyklen mit Metriken-Berechnung
    3. Vergleicht Zyklen über Zeit
    4. Generiert Lern-Insights
    """

    CYCLE_DURATION_DAYS = 7

    _instance = None

    def __init__(self):
        self.conn = None
        self.active_cycles: dict[str, TradingCycle] = {}  # cohort_id -> cycle
        self._connect()
        self._load_active_cycles()

    @classmethod
    def get_instance(cls) -> "CycleManager":
        """Singleton Pattern"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset für Tests"""
        cls._instance = None

    def _connect(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - CycleManager deaktiviert")
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                logger.warning("DATABASE_URL nicht gesetzt")
                return

            self.conn = psycopg2.connect(database_url)
            logger.info("CycleManager: PostgreSQL verbunden")
        except Exception as e:
            logger.error(f"CycleManager: DB Verbindung fehlgeschlagen: {e}")
            self.conn = None

    def _load_active_cycles(self):
        """Lade alle aktiven Zyklen"""
        if not self.conn:
            return

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tc.*, c.name as cohort_name
                    FROM trading_cycles tc
                    JOIN cohorts c ON tc.cohort_id = c.id
                    WHERE tc.status = 'active'
                """)

                for row in cur.fetchall():
                    cycle = self._row_to_cycle(row)
                    self.active_cycles[cycle.cohort_id] = cycle

                logger.info(f"CycleManager: {len(self.active_cycles)} aktive Zyklen geladen")

        except Exception as e:
            logger.error(f"CycleManager: Fehler beim Laden: {e}")

    def _row_to_cycle(self, row: dict) -> TradingCycle:
        """Konvertiere DB-Row zu TradingCycle"""
        return TradingCycle(
            id=str(row["id"]),
            cohort_id=str(row["cohort_id"]),
            cohort_name=row.get("cohort_name", "unknown"),
            cycle_number=row["cycle_number"],
            start_date=row["start_date"],
            end_date=row.get("end_date"),
            status=row["status"],
            starting_capital=float(row["starting_capital"]),
            ending_capital=float(row["ending_capital"]) if row.get("ending_capital") else None,
            trades_count=row.get("trades_count", 0) or 0,
            total_pnl=float(row["total_pnl"]) if row.get("total_pnl") else None,
            total_pnl_pct=float(row["total_pnl_pct"]) if row.get("total_pnl_pct") else None,
            winning_trades=row.get("winning_trades", 0) or 0,
            losing_trades=row.get("losing_trades", 0) or 0,
            max_drawdown=float(row["max_drawdown"]) if row.get("max_drawdown") else None,
            sharpe_ratio=float(row["sharpe_ratio"]) if row.get("sharpe_ratio") else None,
            sortino_ratio=float(row["sortino_ratio"]) if row.get("sortino_ratio") else None,
            calmar_ratio=float(row["calmar_ratio"]) if row.get("calmar_ratio") else None,
            kelly_fraction=float(row["kelly_fraction"]) if row.get("kelly_fraction") else None,
            var_95=float(row["var_95"]) if row.get("var_95") else None,
            cvar_95=float(row["cvar_95"]) if row.get("cvar_95") else None,
            avg_fear_greed=float(row["avg_fear_greed"]) if row.get("avg_fear_greed") else None,
            dominant_regime=row.get("dominant_regime"),
            btc_performance_pct=float(row["btc_performance_pct"])
            if row.get("btc_performance_pct")
            else None,
            playbook_version_at_start=row.get("playbook_version_at_start"),
            playbook_version_at_end=row.get("playbook_version_at_end"),
        )

    def start_cycle(
        self, cohort_id: str, cohort_name: str, starting_capital: float = 1000.0
    ) -> TradingCycle | None:
        """Starte einen neuen Zyklus für eine Cohort"""
        if not self.conn:
            logger.warning("CycleManager: DB nicht verfügbar")
            return None

        try:
            # Hole aktuellen Playbook-Version
            playbook_version = self._get_current_playbook_version()

            # Ermittle nächste Zyklus-Nummer
            next_cycle_number = self._get_next_cycle_number(cohort_id)

            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO trading_cycles (
                        cohort_id, cycle_number, start_date, status,
                        starting_capital, playbook_version_at_start
                    ) VALUES (%s, %s, NOW(), 'active', %s, %s)
                    RETURNING *
                """,
                    (cohort_id, next_cycle_number, starting_capital, playbook_version),
                )

                row = cur.fetchone()
                self.conn.commit()

                row["cohort_name"] = cohort_name
                cycle = self._row_to_cycle(row)
                self.active_cycles[cohort_id] = cycle

                logger.info(
                    f"CycleManager: Neuer Zyklus #{cycle.cycle_number} für {cohort_name} gestartet"
                )
                return cycle

        except Exception as e:
            logger.error(f"CycleManager: Fehler beim Zyklus-Start: {e}")
            self.conn.rollback()
            return None

    def close_cycle(
        self, cohort_id: str, metrics: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        Beende den aktiven Zyklus einer Cohort.

        Args:
            cohort_id: ID der Cohort
            metrics: Optional vorberechnete Metriken

        Returns:
            Zusammenfassung des geschlossenen Zyklus
        """
        if cohort_id not in self.active_cycles:
            logger.warning(f"CycleManager: Kein aktiver Zyklus für Cohort {cohort_id}")
            return None

        cycle = self.active_cycles[cohort_id]

        if not self.conn:
            logger.warning("CycleManager: DB nicht verfügbar")
            return None

        try:
            # Berechne Metriken falls nicht übergeben
            if metrics is None:
                metrics = self._calculate_cycle_metrics(cycle)

            # Hole aktuellen Playbook-Version
            playbook_version = self._get_current_playbook_version()

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trading_cycles SET
                        end_date = NOW(),
                        status = 'completed',
                        closed_at = NOW(),
                        ending_capital = %s,
                        trades_count = %s,
                        total_pnl = %s,
                        total_pnl_pct = %s,
                        winning_trades = %s,
                        losing_trades = %s,
                        max_drawdown = %s,
                        sharpe_ratio = %s,
                        sortino_ratio = %s,
                        calmar_ratio = %s,
                        kelly_fraction = %s,
                        var_95 = %s,
                        cvar_95 = %s,
                        avg_fear_greed = %s,
                        dominant_regime = %s,
                        btc_performance_pct = %s,
                        signal_performance = %s,
                        best_patterns = %s,
                        worst_patterns = %s,
                        playbook_version_at_end = %s
                    WHERE id = %s
                """,
                    (
                        metrics.get("ending_capital", cycle.starting_capital),
                        metrics.get("trades_count", 0),
                        metrics.get("total_pnl"),
                        metrics.get("total_pnl_pct"),
                        metrics.get("winning_trades", 0),
                        metrics.get("losing_trades", 0),
                        metrics.get("max_drawdown"),
                        metrics.get("sharpe_ratio"),
                        metrics.get("sortino_ratio"),
                        metrics.get("calmar_ratio"),
                        metrics.get("kelly_fraction"),
                        metrics.get("var_95"),
                        metrics.get("cvar_95"),
                        metrics.get("avg_fear_greed"),
                        metrics.get("dominant_regime"),
                        metrics.get("btc_performance_pct"),
                        psycopg2.extras.Json(metrics.get("signal_performance")),
                        psycopg2.extras.Json(metrics.get("best_patterns")),
                        psycopg2.extras.Json(metrics.get("worst_patterns")),
                        playbook_version,
                        cycle.id,
                    ),
                )
                self.conn.commit()

            # Entferne aus aktiven Zyklen
            del self.active_cycles[cohort_id]

            logger.info(
                f"CycleManager: Zyklus #{cycle.cycle_number} für {cycle.cohort_name} geschlossen"
            )

            return {
                "cycle_number": cycle.cycle_number,
                "cohort_name": cycle.cohort_name,
                "duration_days": self.CYCLE_DURATION_DAYS,
                **metrics,
            }

        except Exception as e:
            logger.error(f"CycleManager: Fehler beim Zyklus-Schließen: {e}")
            self.conn.rollback()
            return None

    def _calculate_cycle_metrics(self, cycle: TradingCycle) -> dict[str, Any]:
        """Berechne alle Metriken für einen Zyklus"""
        if not self.conn:
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Trade-Statistiken
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as trades_count,
                        SUM(CASE WHEN was_good_decision THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN was_good_decision = false THEN 1 ELSE 0 END) as losing_trades,
                        AVG(outcome_24h) as avg_return,
                        STDDEV(outcome_24h) as return_std,
                        AVG(fear_greed) as avg_fear_greed,
                        MODE() WITHIN GROUP (ORDER BY market_trend) as dominant_regime
                    FROM trades
                    WHERE cycle_id = %s
                """,
                    (cycle.id,),
                )
                trade_stats = cur.fetchone()

                # BTC Performance im Zeitraum
                cur.execute(
                    """
                    SELECT
                        (SELECT btc_price FROM market_snapshots
                         WHERE timestamp >= %s ORDER BY timestamp LIMIT 1) as start_btc,
                        (SELECT btc_price FROM market_snapshots
                         WHERE timestamp <= NOW() ORDER BY timestamp DESC LIMIT 1) as end_btc
                """,
                    (cycle.start_date,),
                )
                btc_data = cur.fetchone()

                btc_perf = None
                if btc_data and btc_data["start_btc"] and btc_data["end_btc"]:
                    btc_perf = (
                        (btc_data["end_btc"] - btc_data["start_btc"]) / btc_data["start_btc"] * 100
                    )

                # Berechne Sharpe und Sortino
                returns = self._get_daily_returns(cycle.id)
                sharpe = self._calculate_sharpe(returns)
                sortino = self._calculate_sortino(returns)
                var_95, cvar_95 = self._calculate_var(returns)
                max_dd = self._calculate_max_drawdown(cycle.id)

                # Kelly aus Win-Rate
                win_rate = 0
                if trade_stats["trades_count"] and trade_stats["trades_count"] > 0:
                    win_rate = (trade_stats["winning_trades"] or 0) / trade_stats["trades_count"]

                kelly = self._calculate_kelly(win_rate, returns)

                # Calmar = Annual Return / Max Drawdown
                calmar = None
                if max_dd and max_dd != 0:
                    annual_return = (trade_stats.get("avg_return") or 0) * 365 / 7
                    calmar = annual_return / abs(max_dd)

                # Ending Capital (Startkapital + Trades)
                cur.execute(
                    """
                    SELECT SUM(
                        CASE WHEN action = 'SELL' THEN value_usd - fee_usd
                             WHEN action = 'BUY' THEN -(value_usd + fee_usd)
                             ELSE 0 END
                    ) as net_flow
                    FROM trades
                    WHERE cycle_id = %s
                """,
                    (cycle.id,),
                )
                flow_result = cur.fetchone()
                net_flow = float(flow_result["net_flow"] or 0)
                ending_capital = cycle.starting_capital + net_flow

                return {
                    "ending_capital": ending_capital,
                    "trades_count": trade_stats["trades_count"] or 0,
                    "winning_trades": trade_stats["winning_trades"] or 0,
                    "losing_trades": trade_stats["losing_trades"] or 0,
                    "total_pnl": ending_capital - cycle.starting_capital,
                    "total_pnl_pct": (
                        (ending_capital - cycle.starting_capital) / cycle.starting_capital * 100
                    ),
                    "max_drawdown": max_dd,
                    "sharpe_ratio": sharpe,
                    "sortino_ratio": sortino,
                    "calmar_ratio": calmar,
                    "kelly_fraction": kelly,
                    "var_95": var_95,
                    "cvar_95": cvar_95,
                    "avg_fear_greed": trade_stats["avg_fear_greed"],
                    "dominant_regime": trade_stats["dominant_regime"],
                    "btc_performance_pct": btc_perf,
                    "signal_performance": self._get_signal_performance(cycle.id),
                    "best_patterns": self._get_best_patterns(cycle.id),
                    "worst_patterns": self._get_worst_patterns(cycle.id),
                }

        except Exception as e:
            logger.error(f"CycleManager: Fehler bei Metriken-Berechnung: {e}")
            return {}

    def _get_daily_returns(self, cycle_id: str) -> list[float]:
        """Hole tägliche Returns für einen Zyklus"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DATE_TRUNC('day', timestamp) as day,
                           SUM(outcome_24h) as daily_return
                    FROM trades
                    WHERE cycle_id = %s AND outcome_24h IS NOT NULL
                    GROUP BY DATE_TRUNC('day', timestamp)
                    ORDER BY day
                """,
                    (cycle_id,),
                )
                return [float(row["daily_return"]) for row in cur.fetchall() if row["daily_return"]]
        except Exception as e:
            logger.error(f"Error getting daily returns: {e}")
            return []

    def _calculate_sharpe(self, returns: list[float], risk_free: float = 0.05) -> float | None:
        """Berechne Sharpe Ratio"""
        if len(returns) < 2:
            return None

        import numpy as np

        returns_arr = np.array(returns)
        excess = returns_arr - (risk_free / 365)
        if np.std(excess) == 0:
            return None
        return float(np.mean(excess) / np.std(excess) * np.sqrt(365))

    def _calculate_sortino(self, returns: list[float], risk_free: float = 0.05) -> float | None:
        """Berechne Sortino Ratio (nur Downside-Volatilität)"""
        if len(returns) < 2:
            return None

        import numpy as np

        returns_arr = np.array(returns)
        excess = returns_arr - (risk_free / 365)
        downside = excess[excess < 0]

        if len(downside) == 0 or np.std(downside) == 0:
            return None

        return float(np.mean(excess) / np.std(downside) * np.sqrt(365))

    def _calculate_var(
        self, returns: list[float], confidence: float = 0.95
    ) -> tuple[float | None, float | None]:
        """Berechne VaR und CVaR"""
        if len(returns) < 5:
            return None, None

        import numpy as np

        returns_arr = np.array(returns)
        var = float(np.percentile(returns_arr, (1 - confidence) * 100))
        cvar_values = returns_arr[returns_arr <= var]
        cvar = float(np.mean(cvar_values)) if len(cvar_values) > 0 else var

        return var, cvar

    def _calculate_max_drawdown(self, cycle_id: str) -> float | None:
        """Berechne Maximum Drawdown"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH cumulative AS (
                        SELECT timestamp,
                               SUM(CASE WHEN action = 'SELL' THEN value_usd
                                        WHEN action = 'BUY' THEN -value_usd
                                        ELSE 0 END) OVER (ORDER BY timestamp) as cum_pnl
                        FROM trades
                        WHERE cycle_id = %s
                    ),
                    peaks AS (
                        SELECT timestamp, cum_pnl,
                               MAX(cum_pnl) OVER (ORDER BY timestamp) as peak
                        FROM cumulative
                    )
                    SELECT MIN((cum_pnl - peak) / NULLIF(peak, 0) * 100) as max_drawdown
                    FROM peaks
                    WHERE peak > 0
                """,
                    (cycle_id,),
                )
                result = cur.fetchone()
                return float(result["max_drawdown"]) if result and result["max_drawdown"] else None
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return None

    def _calculate_kelly(self, win_rate: float, returns: list[float]) -> float | None:
        """Berechne Kelly Fraction"""
        if win_rate == 0 or len(returns) < 5:
            return None

        import numpy as np

        returns_arr = np.array(returns)
        wins = returns_arr[returns_arr > 0]
        losses = returns_arr[returns_arr < 0]

        if len(wins) == 0 or len(losses) == 0:
            return None

        avg_win = float(np.mean(wins))
        avg_loss = float(np.mean(np.abs(losses)))

        if avg_loss == 0:
            return None

        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        return max(0, min(kelly, 1))  # Bound 0-1

    def _get_signal_performance(self, cycle_id: str) -> dict[str, Any] | None:
        """Hole Signal-Performance für einen Zyklus"""
        if not self.conn:
            return None

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
                        AVG(CASE WHEN ai_direction_signal > 0.3 AND was_correct THEN 1
                                 WHEN ai_direction_signal > 0.3 THEN 0 END) as ai_accuracy
                    FROM signal_components
                    WHERE cycle_id = %s AND was_correct IS NOT NULL
                """,
                    (cycle_id,),
                )
                row = cur.fetchone()
                if row:
                    return {k: float(v) if v else None for k, v in row.items()}
                return None
        except Exception as e:
            logger.error(f"Error getting signal performance: {e}")
            return None

    def _get_best_patterns(self, cycle_id: str) -> list[dict] | None:
        """Hole beste Patterns"""
        # Vereinfachte Implementierung
        return None

    def _get_worst_patterns(self, cycle_id: str) -> list[dict] | None:
        """Hole schlechteste Patterns"""
        return None

    def _get_next_cycle_number(self, cohort_id: str) -> int:
        """Ermittle nächste Zyklus-Nummer"""
        if not self.conn:
            return 1

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(cycle_number), 0) + 1
                    FROM trading_cycles
                    WHERE cohort_id = %s
                """,
                    (cohort_id,),
                )
                result = cur.fetchone()
                return result[0] if result else 1
        except Exception as e:
            logger.error(f"Error getting next cycle number: {e}")
            return 1

    def _get_current_playbook_version(self) -> int | None:
        """Hole aktuelle Playbook-Version"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT MAX(version) FROM playbook_versions")
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting playbook version: {e}")
            return None

    def get_active_cycle(self, cohort_id: str) -> TradingCycle | None:
        """Hole aktiven Zyklus für eine Cohort"""
        return self.active_cycles.get(cohort_id)

    def get_cycle_comparison(self, cohort_id: str, num_cycles: int = 10) -> list[dict[str, Any]]:
        """Vergleiche die letzten N Zyklen einer Cohort"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT tc.*, c.name as cohort_name
                    FROM trading_cycles tc
                    JOIN cohorts c ON tc.cohort_id = c.id
                    WHERE tc.cohort_id = %s AND tc.status = 'completed'
                    ORDER BY tc.cycle_number DESC
                    LIMIT %s
                """,
                    (cohort_id, num_cycles),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting cycle comparison: {e}")
            return []

    def should_start_new_cycle(self, cohort_id: str) -> bool:
        """Prüfe ob ein neuer Zyklus gestartet werden sollte"""
        if cohort_id in self.active_cycles:
            cycle = self.active_cycles[cohort_id]
            elapsed_seconds = (datetime.now() - cycle.start_date).total_seconds()
            return elapsed_seconds >= self.CYCLE_DURATION_DAYS * 86400
        return True

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
