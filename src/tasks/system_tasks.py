"""System operation tasks."""

import os

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked


def task_system_health_check():
    """Prüft Systemgesundheit und loggt Metriken. Läuft alle 6 Stunden."""
    from src.core.logging_system import get_logger
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram

    logger.info("Running system health check...")

    try:
        import psutil

        memory = psutil.virtual_memory()
        memory_usage_mb = memory.used / (1024 * 1024)

        conn = get_db_connection()
        db_status = "healthy" if conn else "unavailable"
        if conn:
            conn.close()

        try:
            market_data = get_market_data()
            btc_price = market_data.get_price("BTCUSDT")
            api_status = "healthy" if btc_price > 0 else "degraded"
        except Exception:
            api_status = "unavailable"

        overall_status = "healthy"
        if db_status != "healthy" or api_status != "healthy":
            overall_status = "degraded"

        trading_logger = get_logger()
        trading_logger.system_health(
            status=overall_status,
            api_status=api_status,
            db_status=db_status,
            memory_usage_mb=memory_usage_mb,
        )

        if overall_status != "healthy":
            telegram = get_telegram()
            telegram.send(f"⚠️ <b>System Health Warning</b>\n\nDB: {db_status}\nAPI: {api_status}")

    except ImportError:
        trading_logger = get_logger()
        trading_logger.system_health(
            status="unknown",
            api_status="unknown",
            db_status="unknown",
        )
    except Exception as e:
        logger.error(f"Health Check Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Health check failed", e, {"task": "health_check"})


@task_locked
def task_check_stops():
    """Prüft Stop-Loss Orders alle 5 Minuten (Safety-Net bei Bot-Downtime)."""
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram
    from src.risk.stop_loss_executor import execute_stop_loss_sell

    logger.info("Checking stop-loss orders...")

    conn = get_db_connection()
    if not conn:
        return

    client = None

    try:
        market_data = get_market_data()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, symbol, entry_price, stop_price, quantity,
                       stop_type, highest_price, trailing_distance
                FROM stop_loss_orders
                WHERE is_active = true
            """)
            stops = cur.fetchall()

        for stop in stops:
            current_price = market_data.get_price(stop["symbol"])
            if not current_price or current_price <= 0:
                continue

            # Update trailing stop if price went higher
            if stop["stop_type"] == "trailing" and stop.get("highest_price"):
                highest = float(stop["highest_price"])
                trailing_dist = float(stop.get("trailing_distance") or 3.0)
                if current_price > highest:
                    new_stop = current_price * (1 - trailing_dist / 100)
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE stop_loss_orders
                            SET highest_price = %s,
                                stop_price = GREATEST(stop_price, %s)
                            WHERE id = %s AND is_active = true
                            """,
                            (current_price, new_stop, stop["id"]),
                        )
                    conn.commit()
                    continue  # Price above stop, no trigger

            if current_price <= float(stop["stop_price"]):
                logger.warning(f"STOP TRIGGERED (scheduler): {stop['symbol']} @ {current_price}")

                # Lazy-init BinanceClient
                if client is None:
                    from src.api.binance_client import BinanceClient

                    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
                    client = BinanceClient(testnet=testnet)

                telegram = get_telegram()
                result = execute_stop_loss_sell(
                    client,
                    stop["symbol"],
                    float(stop["quantity"]),
                    telegram=telegram,
                )

                if result["success"]:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE stop_loss_orders
                            SET is_active = false, triggered_at = NOW(),
                                triggered_price = %s
                            WHERE id = %s
                            """,
                            (current_price, stop["id"]),
                        )
                    conn.commit()

                    telegram.send_stop_loss_alert(
                        symbol=stop["symbol"],
                        trigger_price=current_price,
                        stop_price=float(stop["stop_price"]),
                        quantity=float(stop["quantity"]),
                    )
                else:
                    logger.critical(f"Scheduler stop-loss sell FAILED for {stop['symbol']}")

    except Exception as e:
        logger.error(f"Stop Check Error: {e}")
    finally:
        conn.close()


@task_locked
def task_reset_daily_drawdown():
    """Reset daily drawdown baseline at midnight."""
    logger.info("Resetting daily drawdown baseline...")

    try:
        from src.api.binance_client import BinanceClient

        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        client = BinanceClient(testnet=testnet)
        portfolio_value = client.get_account_balance("USDT")

        if portfolio_value <= 0:
            logger.warning("Daily drawdown reset: could not get portfolio value")
            return

        logger.info(f"Daily drawdown reset: baseline set to ${portfolio_value:.2f}")

    except Exception as e:
        logger.error(f"Daily Drawdown Reset Error: {e}")


def _update_outcomes_for_window(window_hours: int, column: str):
    """Generic outcome calculation for any time window.

    Finds trades that are exactly window_hours old (±1h window)
    and calculates the price change percentage.
    """
    from src.data.market_data import get_market_data

    conn = get_db_connection()
    if not conn:
        return

    try:
        market_data = get_market_data()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, symbol, price, action
                FROM trades
                WHERE timestamp < NOW() - INTERVAL '{window_hours} hours'
                AND timestamp > NOW() - INTERVAL '{window_hours + 1} hours'
                AND {column} IS NULL
                """,
            )
            trades = cur.fetchall()

            updated = 0
            for trade in trades:
                current_price = market_data.get_price(trade["symbol"])
                if not current_price or current_price <= 0:
                    continue

                pct_change = ((current_price - trade["price"]) / trade["price"]) * 100
                if trade["action"] == "SELL":
                    pct_change = -pct_change

                # For 24h window, also set was_good_decision (approximate)
                if column == "outcome_24h":
                    is_good = (trade["action"] == "BUY" and pct_change > 0) or (
                        trade["action"] == "SELL" and pct_change < 0
                    )
                    cur.execute(
                        f"""
                        UPDATE trades SET {column} = %s,
                            was_good_decision = COALESCE(was_good_decision, %s)
                        WHERE id = %s
                        """,
                        (pct_change, is_good, trade["id"]),
                    )
                else:
                    cur.execute(
                        f"UPDATE trades SET {column} = %s WHERE id = %s",
                        (pct_change, trade["id"]),
                    )
                updated += 1

            conn.commit()
            if updated:
                logger.info(f"Updated {column} for {updated} trades")

    except Exception as e:
        logger.error(f"Outcome Update Error ({column}): {e}")
    finally:
        conn.close()


def task_update_outcomes():
    """Aktualisiert Trade-Outcomes (24h). Alle 6 Stunden."""
    logger.info("Updating trade outcomes (24h)...")
    _update_outcomes_for_window(24, "outcome_24h")


@task_locked
def task_update_outcomes_1h():
    """Aktualisiert 1h Trade-Outcomes. Stündlich."""
    _update_outcomes_for_window(1, "outcome_1h")


@task_locked
def task_update_outcomes_4h():
    """Aktualisiert 4h Trade-Outcomes. Alle 4 Stunden."""
    _update_outcomes_for_window(4, "outcome_4h")


@task_locked
def task_update_outcomes_7d():
    """Aktualisiert 7d Trade-Outcomes. Täglich."""
    _update_outcomes_for_window(168, "outcome_7d")


@task_locked
def task_evaluate_signal_correctness():
    """Bewertet ob Signale korrekt waren basierend auf outcome_24h.

    Compares signal direction (final_score) against actual price movement.
    Signals with |final_score| <= 0.1 are considered neutral and skipped.
    Runs every 6h after task_update_outcomes.
    """
    logger.info("Evaluating signal correctness...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE signal_components sc SET was_correct = CASE
                    WHEN sc.final_score > 0.1 AND t.outcome_24h > 0 THEN TRUE
                    WHEN sc.final_score < -0.1 AND t.outcome_24h < 0 THEN TRUE
                    WHEN ABS(sc.final_score) <= 0.1 THEN NULL
                    ELSE FALSE
                END
                FROM trades t
                WHERE sc.trade_id = t.id
                AND sc.was_correct IS NULL
                AND t.outcome_24h IS NOT NULL
            """)
            updated = cur.rowcount
            conn.commit()

        if updated:
            logger.info(f"Evaluated signal correctness for {updated} signals")

    except Exception as e:
        logger.error(f"Signal Correctness Error: {e}")
    finally:
        conn.close()


@task_locked
def task_evaluate_trade_decisions():
    """Bewertet Trade-Qualität basierend auf realisiertem P&L aus trade_pairs.

    More precise than the outcome_24h approximation in task_update_outcomes.
    Runs daily. Overwrites the approximate was_good_decision with actual P&L data.
    """
    logger.info("Evaluating trade decisions from trade_pairs...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cur:
            # BUY trades: link via entry_trade_id
            cur.execute("""
                UPDATE trades t
                SET was_good_decision = (tp.net_pnl > 0)
                FROM trade_pairs tp
                WHERE tp.entry_trade_id::text = t.id::text
                AND tp.status = 'closed'
                AND tp.net_pnl IS NOT NULL
            """)
            buy_updated = cur.rowcount

            # SELL trades: link via exit_trade_id
            cur.execute("""
                UPDATE trades t
                SET was_good_decision = (tp.net_pnl > 0)
                FROM trade_pairs tp
                WHERE tp.exit_trade_id::text = t.id::text
                AND tp.status = 'closed'
                AND tp.net_pnl IS NOT NULL
            """)
            sell_updated = cur.rowcount

            conn.commit()

        total = buy_updated + sell_updated
        if total:
            logger.info(f"Evaluated trade decisions: {buy_updated} BUY + {sell_updated} SELL")

    except Exception as e:
        logger.error(f"Trade Decision Evaluation Error: {e}")
    finally:
        conn.close()


def task_macro_check():
    """Prüft anstehende Makro-Events (täglich 8:00)."""
    from src.notifications.telegram_service import get_telegram

    logger.info("Checking macro events...")

    try:
        from src.data.economic_events import EconomicCalendar

        calendar = EconomicCalendar()
        events = calendar.fetch_upcoming_events(days=2)
        high_impact = [e for e in events if e.impact == "HIGH"]

        if high_impact:
            telegram = get_telegram()
            telegram.send_macro_alert(
                [{"date": e.date.strftime("%d.%m %H:%M"), "name": e.name} for e in high_impact[:5]]
            )
        else:
            logger.info("Keine High-Impact Events in den nächsten 48h")

    except Exception as e:
        logger.error(f"Macro Check Error: {e}")
