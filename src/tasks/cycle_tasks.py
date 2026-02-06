"""Cycle management tasks."""

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked


@task_locked
def task_cycle_management():
    """Verwaltet Trading-Zyklen (wöchentlich). Läuft Sonntag um 00:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Running cycle management...")

    try:
        from src.core.cycle_manager import CycleManager

        manager = CycleManager.get_instance()

        conn = get_db_connection()
        if not conn:
            logger.error("Cycle Management: Keine DB-Verbindung")
            return

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name FROM cohorts WHERE is_active = TRUE")
                cohorts = cur.fetchall()

            cycle_reports = []

            for cohort in cohorts:
                cohort_id = str(cohort["id"])
                cohort_name = cohort["name"]

                closed_cycle = manager.close_cycle(cohort_id)

                if closed_cycle:
                    logger.info(
                        f"Cycle {closed_cycle['cycle_number']} closed for {cohort_name}: "
                        f"P&L={closed_cycle.get('total_pnl_pct', 0):.2f}%"
                    )
                    cycle_reports.append(
                        {
                            "cohort": cohort_name,
                            "cycle": closed_cycle["cycle_number"],
                            "pnl_pct": closed_cycle.get("total_pnl_pct") or 0,
                            "sharpe": closed_cycle.get("sharpe_ratio") or 0,
                            "trades": closed_cycle.get("trades_count") or 0,
                        }
                    )

                new_cycle = manager.start_cycle(cohort_id, cohort_name)

                if new_cycle:
                    logger.info(f"Cycle {new_cycle.cycle_number} started for {cohort_name}")

            if cycle_reports:
                message = "📅 <b>WÖCHENTLICHER ZYKLUSREPORT</b>\n\n"

                sorted_reports = sorted(cycle_reports, key=lambda x: x["pnl_pct"], reverse=True)

                for report in sorted_reports:
                    emoji = "🏆" if report == sorted_reports[0] else "📊"
                    pnl_emoji = "📈" if report["pnl_pct"] > 0 else "📉"

                    message += f"""
{emoji} <b>{report["cohort"].upper()}</b> (Zyklus {report["cycle"]})
{pnl_emoji} P&L: {report["pnl_pct"]:+.2f}%
📊 Sharpe: {report["sharpe"]:.2f}
🔄 Trades: {report["trades"]}
"""

                if len(sorted_reports) > 1:
                    winner = sorted_reports[0]
                    message += (
                        f"\n🏆 <b>Winner:</b> {winner['cohort'].upper()} "
                        f"mit {winner['pnl_pct']:+.2f}%"
                    )

                telegram = get_telegram()
                telegram.send(message)

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Cycle Management Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Cycle management failed", e, {"task": "cycle_management"})


def task_weekly_rebalance():
    """Wöchentliches Rebalancing (Sonntag 18:00)."""
    from src.notifications.telegram_service import get_telegram

    logger.info("Running weekly rebalance...")

    telegram = get_telegram()
    telegram.send("""
🔄 <b>WÖCHENTLICHES REBALANCING</b>

Analyse läuft...

<i>Details folgen nach Abschluss.</i>
""")


def task_ab_test_check():
    """Prüft laufende A/B Tests auf statistische Signifikanz. Läuft täglich um 23:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Checking A/B tests...")

    try:
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework.get_instance()

        summaries = framework.get_all_experiments_summary()
        running = [s for s in summaries if s.get("status") == "RUNNING"]

        for exp in running:
            exp_id = exp["id"]

            should_stop, reason = framework.check_early_stopping(exp_id)

            if should_stop:
                result = framework.complete_experiment(exp_id, promote_winner=True)

                if result:
                    telegram = get_telegram()
                    telegram.send(f"""
🧪 <b>A/B TEST ABGESCHLOSSEN</b>

<b>{exp["name"]}</b>
Grund: {reason}

<b>Ergebnis:</b>
🏆 Winner: {result.winner}
📊 p-Wert: {result.p_value:.4f}
📈 Verbesserung: {result.winner_improvement:+.1f}%
🎯 Signifikanz: {result.significance.value}
""")
            else:
                logger.info(f"A/B Test '{exp['name']}': {reason}")

    except Exception as e:
        logger.error(f"A/B Test Check Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("A/B test check failed", e, {"task": "ab_test_check"})
