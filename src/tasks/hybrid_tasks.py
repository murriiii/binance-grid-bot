"""Hybrid orchestrator tasks."""

from datetime import datetime

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked


@task_locked
def task_mode_evaluation():
    """Evaluates current market regime and logs mode recommendation. Runs every hour."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Running mode evaluation...")

    try:
        from src.analysis.regime_detection import RegimeDetector

        detector = RegimeDetector.get_instance()
        regime_state = detector.detect_regime("BTCUSDT")

        if not regime_state:
            logger.warning("Mode evaluation: no regime data, skipping")
            return

        from src.core.hybrid_config import HybridConfig
        from src.core.mode_manager import ModeManager

        hybrid_config = HybridConfig.from_env()
        manager = ModeManager.get_instance(hybrid_config)

        manager.update_regime_info(regime_state.regime.value, regime_state.probability)

        # Get regime duration from DB
        regime_duration_days = 0
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT MIN(timestamp) as first_seen
                        FROM regime_history
                        WHERE regime = %s
                        AND timestamp > (
                            SELECT COALESCE(MAX(timestamp), '1970-01-01')
                            FROM regime_history
                            WHERE regime != %s
                        )
                    """,
                        (regime_state.regime.value, regime_state.regime.value),
                    )
                    row = cur.fetchone()
                    if row and row["first_seen"]:
                        regime_duration_days = (datetime.now() - row["first_seen"]).days
            except Exception as e:
                logger.debug(f"Regime duration query failed: {e}")
            finally:
                conn.close()

        recommended_mode, reason = manager.evaluate_mode(
            regime_state.regime.value,
            regime_state.probability,
            regime_duration_days,
        )

        current_mode = manager.get_current_mode()
        logger.info(
            f"Mode evaluation: regime={regime_state.regime.value} "
            f"(prob={regime_state.probability:.2f}, dur={regime_duration_days}d) "
            f"-> recommended={recommended_mode.value} (reason: {reason})"
        )

        # Store evaluation in trading_mode_history
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO trading_mode_history (
                            mode, previous_mode, regime, regime_probability,
                            regime_duration_days, transition_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            recommended_mode.value,
                            current_mode.current_mode.value,
                            regime_state.regime.value,
                            regime_state.probability,
                            regime_duration_days,
                            reason,
                        ),
                    )
                    conn.commit()
            except Exception as e:
                logger.debug(f"Mode history insert failed: {e}")
            finally:
                conn.close()

        # Notify on mode change recommendation
        if recommended_mode != current_mode.current_mode:
            telegram = get_telegram()
            telegram.send(f"""
<b>MODE EVALUATION</b>

Regime: {regime_state.regime.value} ({regime_state.probability:.1%})
Duration: {regime_duration_days}d

Current: {current_mode.current_mode.value}
Recommended: <b>{recommended_mode.value}</b>

Reason: {reason}

<i>Orchestrator will apply if running.</i>
""")

    except Exception as e:
        logger.error(f"Mode Evaluation Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Mode evaluation failed", e, {"task": "mode_evaluation"})


@task_locked
def task_hybrid_rebalance():
    """Checks portfolio allocation drift for the hybrid system. Runs every 6 hours."""
    from src.core.logging_system import get_logger
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram

    logger.info("Running hybrid rebalance check...")

    try:
        import json
        from pathlib import Path

        state_file = Path("/app/config/hybrid_state.json")
        if not state_file.exists():
            logger.info("Hybrid rebalance: no state file, orchestrator not active")
            return

        with open(state_file) as f:
            state = json.load(f)

        symbols = state.get("symbols", {})
        if not symbols:
            logger.info("Hybrid rebalance: no active symbols")
            return

        market_data = get_market_data()

        drift_report = []
        for symbol, sdata in symbols.items():
            allocation = sdata.get("allocation_usd", 0)
            if allocation <= 0:
                continue

            try:
                price = market_data.get_price(symbol)
                if not price or price <= 0:
                    continue

                hold_qty = sdata.get("hold_quantity", 0)
                current_value = hold_qty * price if hold_qty > 0 else allocation

                drift_pct = abs(current_value - allocation) / allocation * 100
                if drift_pct > 5.0:
                    drift_report.append(
                        {
                            "symbol": symbol,
                            "target": allocation,
                            "current": current_value,
                            "drift_pct": drift_pct,
                        }
                    )
            except Exception:
                continue

        if drift_report:
            report_lines = []
            for d in drift_report[:5]:
                direction = "over" if d["current"] > d["target"] else "under"
                report_lines.append(
                    f"  {d['symbol']}: ${d['current']:.2f} vs ${d['target']:.2f} "
                    f"({direction}, {d['drift_pct']:.1f}% drift)"
                )

            logger.info(f"Hybrid rebalance: {len(drift_report)} symbols drifted")
            telegram = get_telegram()
            telegram.send(
                f"<b>REBALANCE CHECK</b>\n\n"
                f"{len(drift_report)} Symbols mit >5% Drift:\n\n"
                + "\n".join(report_lines)
                + "\n\n<i>Orchestrator rebalanciert automatisch.</i>"
            )
        else:
            logger.info("Hybrid rebalance: no significant drift detected")

    except Exception as e:
        logger.error(f"Hybrid Rebalance Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Hybrid rebalance failed", e, {"task": "hybrid_rebalance"})
