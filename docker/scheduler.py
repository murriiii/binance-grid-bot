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
    task_grid_health_summary,
    task_order_timeout_check,
    task_portfolio_plausibility,
    task_reconcile_orders,
)
from src.tasks.portfolio_tasks import (
    task_coin_performance_update,
    task_portfolio_rebalance,
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
    task_macro_check,
    task_reset_daily_drawdown,
    task_system_health_check,
    task_update_outcomes,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Hauptfunktion - Scheduler Setup"""
    logger.info("Starting Trading Bot Scheduler...")

    telegram = get_telegram()
    telegram.send("🚀 <b>Trading Bot Scheduler gestartet</b>\n\n<i>Alle Jobs aktiv.</i>")

    # ═══════════════════════════════════════════════════════════════
    # CORE JOBS
    # ═══════════════════════════════════════════════════════════════

    # Tägliche Summary um 20:00
    schedule.every().day.at("20:00").do(task_daily_summary)

    # Stündliche Market Snapshots
    schedule.every().hour.at(":00").do(task_market_snapshot)

    # Stop-Loss Check alle 5 Minuten
    schedule.every(5).minutes.do(task_check_stops)

    # Outcome Updates alle 6 Stunden
    schedule.every(6).hours.do(task_update_outcomes)

    # Wöchentliches Rebalancing (Sonntag 18:00)
    schedule.every().sunday.at("18:00").do(task_weekly_rebalance)

    # Macro Check täglich um 8:00
    schedule.every().day.at("08:00").do(task_macro_check)

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
