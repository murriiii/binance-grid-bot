"""Production Validator - Checks if the system meets go-live criteria.

Validates trading performance, signal quality, portfolio health,
and system maturity before transitioning from paper to live trading.
"""

import logging
from dataclasses import dataclass, field

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection

logger = logging.getLogger("trading_bot")


# Minimum criteria for production readiness
PRODUCTION_CRITERIA = {
    "min_trades": 5000,  # ~6 weeks at 120/day
    "min_sharpe": 0.5,  # Annualized, across all cohorts
    "min_playbook_version": 4,  # At least 4 iterations
    "min_signal_evaluations": 1000,  # was_correct populated
    "min_regime_changes": 2,  # BULL→BEAR or reverse observed
    "max_drawdown_pct": -15.0,  # No tier > 15% drawdown
    "min_win_rate": 45.0,  # Across all cohorts
    "index_tracking_error_max": 5.0,  # Index tier < 5% from benchmark
    "min_ai_recommendations": 2,  # AI has given 2+ portfolio recommendations
}


@dataclass
class ValidationResult:
    """Result of a production validation check."""

    name: str
    passed: bool
    current_value: float | str | None = None
    required_value: float | str | None = None
    message: str = ""


@dataclass
class ValidationReport:
    """Full validation report."""

    is_ready: bool = False
    passed_count: int = 0
    total_count: int = 0
    results: list[ValidationResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def progress_pct(self) -> float:
        return (self.passed_count / self.total_count * 100) if self.total_count > 0 else 0


class ProductionValidator:
    """Validates if the trading system is ready for production.

    Checks all criteria defined in PRODUCTION_CRITERIA against
    actual system data from the database.
    """

    def __init__(self, criteria: dict | None = None):
        self.criteria = criteria or PRODUCTION_CRITERIA

    def validate(self) -> tuple[bool, list[str]]:
        """Run all validation checks.

        Returns:
            Tuple of (is_ready: bool, failure_messages: list[str])
        """
        report = self.validate_detailed()
        return report.is_ready, report.failures

    def validate_detailed(self) -> ValidationReport:
        """Run all validation checks with detailed results."""
        conn = get_db_connection()
        if not conn:
            return ValidationReport(
                failures=["Cannot connect to database"],
                total_count=len(self.criteria),
            )

        results = []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                results.append(self._check_min_trades(cur))
                results.append(self._check_sharpe_ratio(cur))
                results.append(self._check_playbook_version())
                results.append(self._check_signal_evaluations(cur))
                results.append(self._check_regime_changes(cur))
                results.append(self._check_max_drawdown(cur))
                results.append(self._check_win_rate(cur))
                results.append(self._check_index_tracking_error(cur))
                results.append(self._check_ai_recommendations(cur))
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationReport(
                failures=[f"Validation error: {e}"],
                total_count=len(self.criteria),
            )
        finally:
            conn.close()

        passed = [r for r in results if r.passed]
        failures = [r.message for r in results if not r.passed]

        report = ValidationReport(
            is_ready=len(failures) == 0,
            passed_count=len(passed),
            total_count=len(results),
            results=results,
            failures=failures,
        )

        logger.info(
            f"Production validation: {report.passed_count}/{report.total_count} "
            f"({report.progress_pct:.0f}%) — {'READY' if report.is_ready else 'NOT READY'}"
        )

        return report

    def _check_min_trades(self, cur) -> ValidationResult:
        """Check minimum number of closed trade pairs."""
        required = self.criteria["min_trades"]
        cur.execute("SELECT COUNT(*) as count FROM trade_pairs WHERE status = 'closed'")
        row = cur.fetchone()
        count = row["count"] if row else 0

        return ValidationResult(
            name="min_trades",
            passed=count >= required,
            current_value=count,
            required_value=required,
            message=f"Trades: {count}/{required}"
            if count >= required
            else f"Need {required - count} more trades ({count}/{required})",
        )

    def _check_sharpe_ratio(self, cur) -> ValidationResult:
        """Check annualized Sharpe ratio from portfolio snapshots."""
        required = self.criteria["min_sharpe"]

        cur.execute("""
            SELECT sharpe_ratio FROM portfolio_snapshots
            WHERE sharpe_ratio IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()
        sharpe = float(row["sharpe_ratio"]) if row and row["sharpe_ratio"] else 0.0

        return ValidationResult(
            name="min_sharpe",
            passed=sharpe >= required,
            current_value=round(sharpe, 3),
            required_value=required,
            message=f"Sharpe: {sharpe:.3f} (min {required})"
            if sharpe >= required
            else f"Sharpe too low: {sharpe:.3f} < {required}",
        )

    def _check_playbook_version(self) -> ValidationResult:
        """Check playbook has been updated enough times."""
        required = self.criteria["min_playbook_version"]

        try:
            from src.data.playbook import get_playbook

            playbook = get_playbook()
            version = playbook.current_version
        except Exception:
            version = 0

        return ValidationResult(
            name="min_playbook_version",
            passed=version >= required,
            current_value=version,
            required_value=required,
            message=f"Playbook v{version} (min v{required})"
            if version >= required
            else f"Playbook v{version} < v{required} — needs {required - version} more updates",
        )

    def _check_signal_evaluations(self, cur) -> ValidationResult:
        """Check enough signals have been evaluated for correctness."""
        required = self.criteria["min_signal_evaluations"]

        cur.execute("SELECT COUNT(*) as count FROM signal_components WHERE was_correct IS NOT NULL")
        row = cur.fetchone()
        count = row["count"] if row else 0

        return ValidationResult(
            name="min_signal_evaluations",
            passed=count >= required,
            current_value=count,
            required_value=required,
            message=f"Signal evaluations: {count}/{required}"
            if count >= required
            else f"Need {required - count} more signal evaluations ({count}/{required})",
        )

    def _check_regime_changes(self, cur) -> ValidationResult:
        """Check that the system has observed enough regime transitions."""
        required = self.criteria["min_regime_changes"]

        cur.execute("""
            SELECT COUNT(*) as count FROM regime_history
            WHERE previous_regime IS NOT NULL
            AND previous_regime != regime
        """)
        row = cur.fetchone()
        count = row["count"] if row else 0

        return ValidationResult(
            name="min_regime_changes",
            passed=count >= required,
            current_value=count,
            required_value=required,
            message=f"Regime changes: {count} (min {required})"
            if count >= required
            else f"Only {count} regime changes observed (need {required})",
        )

    def _check_max_drawdown(self, cur) -> ValidationResult:
        """Check no tier has exceeded max drawdown threshold."""
        limit = self.criteria["max_drawdown_pct"]  # Negative, e.g. -15.0

        cur.execute("""
            SELECT COALESCE(MIN(max_drawdown), 0) as worst_drawdown
            FROM portfolio_snapshots
            WHERE max_drawdown IS NOT NULL
            AND timestamp > NOW() - INTERVAL '60 days'
        """)
        row = cur.fetchone()
        worst_dd = float(row["worst_drawdown"]) if row and row["worst_drawdown"] else 0.0

        # worst_dd is negative (e.g., -12.5). limit is negative (e.g., -15.0).
        # Passed if worst_dd >= limit (less severe than limit)
        passed = worst_dd >= limit

        return ValidationResult(
            name="max_drawdown",
            passed=passed,
            current_value=round(worst_dd, 2),
            required_value=limit,
            message=f"Max drawdown: {worst_dd:.1f}% (limit {limit:.1f}%)"
            if passed
            else f"Drawdown {worst_dd:.1f}% exceeds limit {limit:.1f}%",
        )

    def _check_win_rate(self, cur) -> ValidationResult:
        """Check overall win rate across all cohorts."""
        required = self.criteria["min_win_rate"]

        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trade_pairs
            WHERE status = 'closed' AND net_pnl IS NOT NULL
        """)
        row = cur.fetchone()
        total = row["total"] if row else 0
        wins = row["wins"] if row else 0
        win_rate = (wins / total * 100) if total > 0 else 0.0

        return ValidationResult(
            name="min_win_rate",
            passed=win_rate >= required,
            current_value=round(win_rate, 1),
            required_value=required,
            message=f"Win rate: {win_rate:.1f}% ({wins}/{total})"
            if win_rate >= required
            else f"Win rate {win_rate:.1f}% < {required}% ({wins}/{total})",
        )

    def _check_index_tracking_error(self, cur) -> ValidationResult:
        """Check index tier tracking error is within bounds.

        Tracking error = difference between actual index allocation %
        and target allocation %.
        """
        max_error = self.criteria["index_tracking_error_max"]

        cur.execute("""
            SELECT target_pct, current_pct
            FROM portfolio_tiers
            WHERE tier_name = 'index_holdings' AND is_active = TRUE
        """)
        row = cur.fetchone()

        if not row or row["current_pct"] is None:
            return ValidationResult(
                name="index_tracking_error",
                passed=False,
                current_value=None,
                required_value=max_error,
                message="No index tier data available",
            )

        target = float(row["target_pct"])
        current = float(row["current_pct"])
        error = abs(current - target)

        return ValidationResult(
            name="index_tracking_error",
            passed=error <= max_error,
            current_value=round(error, 2),
            required_value=max_error,
            message=f"Index tracking error: {error:.1f}pp (max {max_error}pp)"
            if error <= max_error
            else f"Index tracking error {error:.1f}pp > {max_error}pp",
        )

    def _check_ai_recommendations(self, cur) -> ValidationResult:
        """Check AI portfolio optimizer has generated enough recommendations."""
        required = self.criteria["min_ai_recommendations"]

        cur.execute("SELECT COUNT(*) as count FROM ai_portfolio_recommendations")
        row = cur.fetchone()
        count = row["count"] if row else 0

        return ValidationResult(
            name="min_ai_recommendations",
            passed=count >= required,
            current_value=count,
            required_value=required,
            message=f"AI recommendations: {count} (min {required})"
            if count >= required
            else f"Need {required - count} more AI recommendations ({count}/{required})",
        )
