#!/usr/bin/env python3
"""
Trading Bot Scheduler
Registriert alle periodischen Tasks und führt sie aus.
"""

import logging
import signal
import sys
import time

import schedule

_shutdown = False

sys.path.insert(0, "/app")

from dotenv import load_dotenv

load_dotenv()

from src.notifications.telegram_service import get_telegram
from src.tasks.analysis_tasks import (
    task_divergence_scan,
    task_learn_patterns,
    task_regime_detection,
    task_update_signal_weights,
)
from src.tasks.cycle_tasks import (
    task_ab_test_check,
    task_cycle_management,
    task_weekly_rebalance,
)
from src.tasks.data_tasks import (
    task_fetch_etf_flows,
    task_fetch_social_sentiment,
    task_fetch_token_unlocks,
    task_whale_check,
)
from src.tasks.hybrid_tasks import task_hybrid_rebalance, task_mode_evaluation
from src.tasks.market_tasks import task_market_snapshot, task_sentiment_check
from src.tasks.monitoring_tasks import (
    task_discovery_health_check,
    task_grid_health_summary,
    task_order_timeout_check,
    task_portfolio_plausibility,
    task_reconcile_orders,
    task_stale_detection,
    task_tier_health_check,
)
from src.tasks.portfolio_tasks import (
    task_auto_discovery,
    task_coin_performance_update,
    task_portfolio_rebalance,
    task_portfolio_snapshot,
    task_scan_opportunities,
    task_update_watchlist,
)
from src.tasks.reporting_tasks import (
    task_daily_summary,
    task_update_playbook,
    task_weekly_export,
)
from src.tasks.system_tasks import (
    task_check_stops,
    task_evaluate_signal_correctness,
    task_evaluate_trade_decisions,
    task_macro_check,
    task_reset_daily_drawdown,
    task_system_health_check,
    task_update_outcomes,
    task_update_outcomes_1h,
    task_update_outcomes_4h,
    task_update_outcomes_7d,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def _task_profit_redistribution():
    """Weekly profit redistribution (only when PORTFOLIO_MANAGER=true)."""
    import os

    if os.getenv("PORTFOLIO_MANAGER", "false").lower() != "true":
        return

    logger.info("Running profit redistribution...")
    try:
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        # Create a lightweight context — we only need the value query
        engine = ProfitRedistributionEngine(portfolio_manager=None)

        # Check if rebalance needed by querying DB directly
        from src.tasks.base import get_db_connection

        conn = get_db_connection()
        if not conn:
            return

        from psycopg2.extras import RealDictCursor

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT tier_name, target_pct, current_pct "
                "FROM portfolio_tiers WHERE is_active = TRUE"
            )
            tiers = cur.fetchall()

        conn.close()

        needs_rebalance = any(
            abs(float(t["current_pct"] or 0) - float(t["target_pct"]))
            > engine.REBALANCE_THRESHOLD_PCT
            for t in tiers
        )

        if needs_rebalance:
            logger.info("Tier drift detected — rebalance recommended")
            from src.notifications.telegram_service import get_telegram

            telegram = get_telegram()
            drift_lines = []
            for t in tiers:
                drift = float(t["current_pct"] or 0) - float(t["target_pct"])
                drift_lines.append(
                    f"  {t['tier_name']}: {float(t['current_pct'] or 0):.1f}% "
                    f"(target {float(t['target_pct']):.1f}%, drift {drift:+.1f}pp)"
                )
            telegram.send(
                "Tier Rebalance Check\n\n" + "\n".join(drift_lines) + "\n\nRebalance recommended.",
                force=True,
            )
        else:
            logger.info("Profit redistribution: no rebalance needed")

    except Exception as e:
        logger.error(f"Profit redistribution error: {e}")


def _task_production_validation():
    """Daily production readiness check — logs progress toward go-live."""
    logger.info("Running production validation...")
    try:
        from src.portfolio.validation import ProductionValidator

        validator = ProductionValidator()
        report = validator.validate_detailed()

        logger.info(
            f"Production validation: {report.passed_count}/{report.total_count} "
            f"({report.progress_pct:.0f}%)"
        )

        # Only send Telegram when newly ready or significant progress
        if report.is_ready:
            from src.notifications.telegram_service import get_telegram

            telegram = get_telegram()
            telegram.send(
                "Production Validation: READY\n\n"
                f"All {report.total_count} criteria met.\n"
                "System is ready for live trading.",
                force=True,
            )

    except Exception as e:
        logger.error(f"Production validation error: {e}")


def _task_ai_portfolio_optimizer():
    """Monthly AI portfolio optimization (1st of month, PORTFOLIO_MANAGER=true)."""
    import os
    from datetime import datetime

    if os.getenv("PORTFOLIO_MANAGER", "false").lower() != "true":
        return

    # Only run on the 1st of the month
    if datetime.now().day != 1:
        return

    logger.info("Running AI portfolio optimizer...")
    try:
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        recommendation = optimizer.get_recommendation()

        if not recommendation:
            logger.warning("AI Optimizer: no recommendation generated")
            return

        allocations = recommendation.get("allocations", {})
        confidence = recommendation.get("confidence", 0)
        reasoning = recommendation.get("reasoning", "")

        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        msg = (
            "AI Portfolio Recommendation\n\n"
            f"Cash: {allocations.get('cash_reserve', 0):.1f}%\n"
            f"Index: {allocations.get('index_holdings', 0):.1f}%\n"
            f"Trading: {allocations.get('trading', 0):.1f}%\n"
            f"Confidence: {confidence:.0%}\n\n"
            f"{reasoning}"
        )

        if optimizer.should_auto_apply(recommendation):
            optimizer.apply_recommendation(recommendation)
            msg += "\n\nAuto-applied."
        else:
            msg += "\n\nLogged only (learning mode)."

        telegram.send(msg, force=True)

    except Exception as e:
        logger.error(f"AI Optimizer error: {e}")


def main():
    """Hauptfunktion - Scheduler Setup"""
    logger.info("Starting Trading Bot Scheduler...")

    # Load scheduler config (reads from env vars with sensible defaults)
    from src.core.config import get_config

    sc = get_config().scheduler

    telegram = get_telegram()
    telegram.send("🚀 <b>Trading Bot Scheduler gestartet</b>\n\n<i>Alle Jobs aktiv.</i>")

    # ═══════════════════════════════════════════════════════════════
    # CORE JOBS
    # ═══════════════════════════════════════════════════════════════

    # Tägliche Summary (default 20:00)
    schedule.every().day.at(sc.daily_summary_time).do(task_daily_summary)

    # Market Snapshots (default every 60 min)
    schedule.every(sc.market_snapshot_interval).minutes.do(task_market_snapshot)

    # Stop-Loss Check (default every 5 min)
    schedule.every(sc.stop_loss_check_interval).minutes.do(task_check_stops)

    # Outcome Updates (multi-timeframe)
    schedule.every().hour.at(":05").do(task_update_outcomes_1h)
    schedule.every(4).hours.do(task_update_outcomes_4h)
    schedule.every(6).hours.do(task_update_outcomes)
    schedule.every().day.at("12:00").do(task_update_outcomes_7d)

    # Signal correctness evaluation (after outcomes)
    schedule.every(6).hours.do(task_evaluate_signal_correctness)

    # Trade decision quality (precise, from trade_pairs)
    schedule.every().day.at("22:30").do(task_evaluate_trade_decisions)

    # Wöchentliches Rebalancing (default Sonntag 18:00)
    schedule.every().sunday.at(sc.weekly_rebalance_time).do(task_weekly_rebalance)

    # Macro Check (default 08:00)
    schedule.every().day.at(sc.macro_check_time).do(task_macro_check)

    # Sentiment Check alle 4 Stunden
    schedule.every(4).hours.do(task_sentiment_check)

    # Whale Check stündlich
    schedule.every().hour.at(":30").do(task_whale_check)

    # Pattern Learning täglich um 21:00
    schedule.every().day.at("21:00").do(task_learn_patterns)

    # Playbook Update wöchentlich Sonntag 19:00
    schedule.every().sunday.at("19:00").do(task_update_playbook)

    # Weekly Export Samstag 23:00
    schedule.every().saturday.at("23:00").do(task_weekly_export)

    # System Health Check alle 6 Stunden
    schedule.every(6).hours.do(task_system_health_check)

    # Daily Drawdown Reset um Mitternacht
    schedule.every().day.at("00:00").do(task_reset_daily_drawdown)

    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS JOBS
    # ═══════════════════════════════════════════════════════════════

    # ETF Flow Daten täglich um 10:00
    schedule.every().day.at("10:00").do(task_fetch_etf_flows)

    # Social Sentiment alle 4 Stunden
    schedule.every(4).hours.do(task_fetch_social_sentiment)

    # Token Unlocks täglich um 08:00
    schedule.every().day.at("08:00").do(task_fetch_token_unlocks)

    # Regime Detection alle 4 Stunden
    schedule.every(4).hours.do(task_regime_detection)

    # Bayesian Signal Weights täglich um 22:00
    schedule.every().day.at("22:00").do(task_update_signal_weights)

    # Cycle Management wöchentlich Sonntag 00:00
    schedule.every().sunday.at("00:00").do(task_cycle_management)

    # A/B Test Check täglich um 23:00
    schedule.every().day.at("23:00").do(task_ab_test_check)

    # Divergence Scan alle 2 Stunden
    schedule.every(2).hours.do(task_divergence_scan)

    # ═══════════════════════════════════════════════════════════════
    # MULTI-COIN JOBS
    # ═══════════════════════════════════════════════════════════════

    # Watchlist Market Data alle 30 Minuten
    schedule.every(30).minutes.do(task_update_watchlist)

    # Opportunity Scan alle 2 Stunden
    schedule.every(2).hours.do(task_scan_opportunities)

    # Portfolio Rebalance Check täglich um 06:00
    schedule.every().day.at("06:00").do(task_portfolio_rebalance)

    # Coin Performance Update täglich um 21:30
    schedule.every().day.at("21:30").do(task_coin_performance_update)

    # AI Auto-Discovery täglich um 07:00
    schedule.every().day.at("07:00").do(task_auto_discovery)

    # Portfolio Snapshot stündlich (Equity-Kurve)
    schedule.every().hour.at(":10").do(task_portfolio_snapshot)

    # ═══════════════════════════════════════════════════════════════
    # HYBRID ORCHESTRATOR JOBS
    # ═══════════════════════════════════════════════════════════════

    # Mode Evaluation every hour
    schedule.every().hour.at(":15").do(task_mode_evaluation)

    # Hybrid Rebalance Check every 6 hours
    schedule.every(6).hours.do(task_hybrid_rebalance)

    # ═══════════════════════════════════════════════════════════════
    # MONITORING JOBS
    # ═══════════════════════════════════════════════════════════════

    # Order reconciliation every 30 minutes
    schedule.every(30).minutes.do(task_reconcile_orders)

    # Order timeout check every hour
    schedule.every().hour.at(":45").do(task_order_timeout_check)

    # Portfolio plausibility every 2 hours
    schedule.every(2).hours.do(task_portfolio_plausibility)

    # Grid health summary every 4 hours
    schedule.every(4).hours.do(task_grid_health_summary)

    # Stale detection every 30 minutes
    schedule.every(30).minutes.do(task_stale_detection)

    # Discovery pipeline health (12h)
    schedule.every(12).hours.do(task_discovery_health_check)

    # ═══════════════════════════════════════════════════════════════
    # PORTFOLIO TIER JOBS (only active when PORTFOLIO_MANAGER=true)
    # ═══════════════════════════════════════════════════════════════

    # Tier health check every 2 hours
    schedule.every(2).hours.do(task_tier_health_check)

    # Profit redistribution: weekly Sunday 17:00
    schedule.every().sunday.at("17:00").do(_task_profit_redistribution)

    # AI Portfolio Optimizer: monthly (1st of month at 08:00)
    schedule.every().day.at("08:00").do(_task_ai_portfolio_optimizer)

    # Production readiness check: daily at 09:00
    schedule.every().day.at("09:00").do(_task_production_validation)

    logger.info("Scheduled jobs:")
    for job in schedule.get_jobs():
        logger.info(f"  - {job}")

    def _handle_sigterm(_signum, _frame):
        global _shutdown
        _shutdown = True
        logger.info("SIGTERM received, shutting down scheduler...")

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Run loop
    while not _shutdown:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Scheduler Error: {e}")
        time.sleep(60)

    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
