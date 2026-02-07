"""Portfolio management tasks."""

import json

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked


def task_update_watchlist():
    """Aktualisiert Marktdaten für alle Coins in der Watchlist. Läuft alle 30 Minuten."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Updating watchlist market data...")

    try:
        from src.data.watchlist import get_watchlist_manager

        manager = get_watchlist_manager()

        updated = manager.update_market_data()
        deactivated = manager.check_liquidity()

        if deactivated:
            telegram = get_telegram()
            telegram.send(f"""
⚠️ <b>WATCHLIST UPDATE</b>

{len(deactivated)} Coins wegen niedriger Liquidität deaktiviert:
{", ".join(deactivated[:5])}{"..." if len(deactivated) > 5 else ""}
""")

        logger.info(f"Watchlist: {updated} coins updated, {len(deactivated)} deactivated")

    except Exception as e:
        logger.error(f"Watchlist Update Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Watchlist update failed", e, {"task": "update_watchlist"})


@task_locked
def task_scan_opportunities():
    """Scannt Watchlist nach Trading-Opportunities. Läuft alle 2 Stunden."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Scanning for trading opportunities...")

    try:
        from src.scanner import OpportunityDirection, get_coin_scanner

        scanner = get_coin_scanner()
        opportunities = scanner.scan_opportunities(force_refresh=True)

        if not opportunities:
            logger.info("No opportunities found")
            return

        stats = scanner.get_scan_stats()
        logger.info(
            f"Opportunities: {stats['total_opportunities']} found, "
            f"avg score={stats.get('average_score', 0):.2f}"
        )

        top_opportunities = scanner.get_top_opportunities(3)

        if top_opportunities and top_opportunities[0].total_score >= 0.6:
            message = "🎯 <b>TRADING OPPORTUNITIES</b>\n\n"

            for opp in top_opportunities:
                direction_emoji = "🟢" if opp.direction == OpportunityDirection.LONG else "🔴"
                risk_emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🔴"}.get(
                    opp.risk_level.value, "⚠️"
                )

                signals_str = ", ".join(opp.signals[:3])

                message += f"""
{direction_emoji} <b>{opp.symbol}</b> ({opp.category})
Score: {opp.total_score:.2f} | Risk: {risk_emoji}
Signals: {signals_str}
"""

            telegram = get_telegram()
            telegram.send(message)

        conn = get_db_connection()
        if conn:
            try:
                from src.core.cohort_manager import CohortManager

                cohort_manager = CohortManager.get_instance()
                trading_cohorts = cohort_manager.get_active_cohorts()
                logger.info(f"Active cohorts: {len(trading_cohorts)}")

            except Exception as e:
                logger.debug(f"Cohort evaluation skipped: {e}")
            finally:
                conn.close()

    except Exception as e:
        logger.error(f"Opportunity Scan Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Opportunity scan failed", e, {"task": "scan_opportunities"})


@task_locked
def task_portfolio_rebalance():
    """Prüft Portfolio-Allocation und schlägt Rebalancing vor. Läuft täglich um 06:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Checking portfolio allocation...")

    try:
        from src.portfolio import get_portfolio_allocator
        from src.scanner import get_coin_scanner

        allocator = get_portfolio_allocator()
        scanner = get_coin_scanner()

        conn = get_db_connection()
        if not conn:
            return

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name FROM cohorts WHERE is_active = TRUE")
                cohorts = cur.fetchall()

            for cohort in cohorts:
                cohort_id = str(cohort["id"])
                cohort_name = cohort["name"]

                stats = allocator.get_portfolio_stats(cohort_id)

                if stats["position_count"] == 0:
                    opportunities = scanner.get_top_opportunities(5)

                    result = allocator.calculate_allocation(
                        opportunities=opportunities,
                        available_capital=1000.0,
                        cohort_id=cohort_id,
                    )

                    if result.allocations:
                        alloc_str = "\n".join(
                            [f"• {s}: ${a:.2f}" for s, a in list(result.allocations.items())[:5]]
                        )

                        telegram = get_telegram()
                        telegram.send(f"""
📊 <b>NEUE ALLOCATION für {cohort_name.upper()}</b>

{alloc_str}

Total: ${result.total_allocated:.2f}
Cash: ${result.cash_remaining:.2f}
""")

                else:
                    logger.info(
                        f"Portfolio {cohort_name}: "
                        f"{stats['position_count']} positions, "
                        f"${stats['total_value']:.2f}"
                    )

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Portfolio Rebalance Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Portfolio rebalance failed", e, {"task": "portfolio_rebalance"})


def task_coin_performance_update():
    """Aktualisiert Performance-Metriken pro Coin. Läuft täglich um 21:30."""
    from src.core.logging_system import get_logger

    logger.info("Updating coin performance metrics...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        from src.data.watchlist import get_watchlist_manager

        manager = get_watchlist_manager()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN outcome_24h > 0 THEN 1 END) as winning_trades,
                    AVG(outcome_24h) as avg_return
                FROM trades
                WHERE timestamp > NOW() - INTERVAL '7 days'
                AND outcome_24h IS NOT NULL
                GROUP BY symbol
                HAVING COUNT(*) >= 3
            """)
            coin_stats = cur.fetchall()

            for stat in coin_stats:
                symbol = stat["symbol"]
                total = stat["total_trades"]
                wins = stat["winning_trades"] or 0
                avg_return = stat["avg_return"] or 0

                win_rate = (wins / total * 100) if total > 0 else 0

                manager.update_coin_performance(
                    symbol=symbol,
                    total_trades=total,
                    win_rate=win_rate,
                    avg_return_pct=avg_return,
                )

                logger.info(
                    f"Coin {symbol}: {total} trades, "
                    f"{win_rate:.1f}% win rate, "
                    f"{avg_return:+.2f}% avg return"
                )

            cur.execute("""
                INSERT INTO coin_performance (
                    symbol, period_start, period_end, period_type,
                    total_trades, winning_trades, win_rate,
                    gross_return_pct
                )
                SELECT
                    symbol,
                    NOW() - INTERVAL '7 days',
                    NOW(),
                    'WEEKLY',
                    COUNT(*),
                    COUNT(CASE WHEN outcome_24h > 0 THEN 1 END),
                    ROUND(COUNT(CASE WHEN outcome_24h > 0 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2),
                    ROUND(AVG(outcome_24h)::numeric, 4)
                FROM trades
                WHERE timestamp > NOW() - INTERVAL '7 days'
                AND outcome_24h IS NOT NULL
                GROUP BY symbol
                HAVING COUNT(*) >= 3
                ON CONFLICT (symbol, period_start, period_type)
                DO UPDATE SET
                    total_trades = EXCLUDED.total_trades,
                    winning_trades = EXCLUDED.winning_trades,
                    win_rate = EXCLUDED.win_rate,
                    gross_return_pct = EXCLUDED.gross_return_pct
            """)
            conn.commit()

    except Exception as e:
        logger.error(f"Coin Performance Update Error: {e}")
        trading_logger = get_logger()
        trading_logger.error(
            "Coin performance update failed", e, {"task": "coin_performance_update"}
        )

    finally:
        conn.close()


@task_locked
def task_portfolio_snapshot():
    """Stündlicher Portfolio-Snapshot für Equity-Kurve und Drawdown-Erkennung.

    Berechnet Gesamtwert aus offenen trade_pairs + USDT-Positionen.
    Speichert in portfolio_snapshots Tabelle.
    """
    from src.data.market_data import get_market_data

    logger.info("Taking portfolio snapshot...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        market_data = get_market_data()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all open positions from trade_pairs
            cur.execute("""
                SELECT tp.symbol,
                    SUM(tp.remaining_quantity) as total_qty,
                    SUM(tp.entry_value_usd) as cost_basis,
                    tp.cohort_id
                FROM trade_pairs tp
                WHERE tp.status = 'open'
                GROUP BY tp.symbol, tp.cohort_id
            """)
            positions = cur.fetchall()

            total_position_value = 0.0
            total_cost_basis = 0.0
            positions_json = {}

            for pos in positions:
                symbol = pos["symbol"]
                qty = float(pos["total_qty"] or 0)
                cost = float(pos["cost_basis"] or 0)

                if qty <= 0:
                    continue

                current_price = market_data.get_price(symbol)
                if not current_price or current_price <= 0:
                    continue

                value = qty * current_price
                total_position_value += value
                total_cost_basis += cost

                positions_json[symbol] = {
                    "qty": qty,
                    "value": round(value, 2),
                    "cost_basis": round(cost, 2),
                    "current_price": current_price,
                }

            # Get previous snapshot for daily P&L calculation
            cur.execute("""
                SELECT total_value_usd FROM portfolio_snapshots
                ORDER BY timestamp DESC LIMIT 1
            """)
            prev = cur.fetchone()
            prev_value = float(prev["total_value_usd"]) if prev else None

            total_value = total_position_value
            unrealized_pnl = total_position_value - total_cost_basis
            unrealized_pnl_pct = (
                (unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
            )

            daily_pnl = (total_value - prev_value) if prev_value else None
            daily_pnl_pct = (
                (daily_pnl / prev_value * 100) if prev_value and prev_value > 0 else None
            )

            cur.execute(
                """
                INSERT INTO portfolio_snapshots
                    (total_value_usd, daily_pnl, daily_pnl_pct,
                     total_pnl, total_pnl_pct, positions)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    total_value,
                    daily_pnl,
                    daily_pnl_pct,
                    unrealized_pnl,
                    unrealized_pnl_pct,
                    json.dumps(positions_json),
                ),
            )
            conn.commit()

        logger.info(f"Portfolio snapshot: ${total_value:.2f} (uP&L: {unrealized_pnl:+.2f})")

    except Exception as e:
        logger.error(f"Portfolio Snapshot Error: {e}")
    finally:
        conn.close()


def task_auto_discovery():
    """AI-gesteuerte Coin-Entdeckung mit Lernfeedback. Läuft täglich um 07:00."""
    from src.notifications.telegram_service import get_telegram

    logger.info("Running AI auto-discovery...")

    try:
        from src.scanner.coin_discovery import CoinDiscovery

        discovery = CoinDiscovery.get_instance()
        result = discovery.run_discovery()

        telegram = get_telegram()

        if result.get("errors"):
            for err in result["errors"]:
                logger.error(f"Discovery error: {err}")

        if result["added"] > 0 or result["approved"] > 0:
            msg = (
                f"🔍 <b>AUTO-DISCOVERY</b>\n\n"
                f"Kandidaten: {result['candidates']}\n"
                f"AI-bewertet: {result['evaluated']}\n"
                f"Genehmigt: {result['approved']}\n"
                f"Hinzugefügt: {result['added']}"
            )
            telegram.send(msg)
        else:
            logger.info(f"Discovery: {result['candidates']} candidates, none approved")

    except Exception as e:
        logger.error(f"Auto-discovery task failed: {e}")
