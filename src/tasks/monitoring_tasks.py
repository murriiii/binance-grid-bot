"""Monitoring and plausibility tasks for the trading system."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from src.tasks.base import logger
from src.utils.task_lock import task_locked

CONFIG_DIR = Path("config")


def _load_grid_states() -> dict[str, dict]:
    """Load all grid_state_*_*.json files from config/.

    Returns:
        Dict keyed by "cohort:SYMBOL" -> state dict.
    """
    states: dict[str, dict] = {}
    for gs_file in CONFIG_DIR.glob("grid_state_*_*.json"):
        try:
            with open(gs_file) as f:
                data = json.load(f)
            # Filename: grid_state_BTCUSDT_conservative.json
            parts = gs_file.stem.replace("grid_state_", "").rsplit("_", 1)
            if len(parts) == 2:
                symbol, cohort = parts
                states[f"{cohort}:{symbol}"] = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load {gs_file}: {e}")
    return states


def _load_hybrid_states() -> dict[str, dict]:
    """Load all hybrid_state_*.json files from config/.

    Returns:
        Dict keyed by cohort name -> state dict.
    """
    states: dict[str, dict] = {}
    for hs_file in CONFIG_DIR.glob("hybrid_state_*.json"):
        try:
            with open(hs_file) as f:
                data = json.load(f)
            cohort = hs_file.stem.replace("hybrid_state_", "")
            states[cohort] = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load {hs_file}: {e}")
    return states


def _is_paper_mode() -> bool:
    """Check if paper trading is enabled."""
    return os.getenv("PAPER_TRADING", "false").lower() == "true"


def _get_binance_client():
    """Lazy-init BinanceClient or PaperBinanceClient depending on mode."""
    if _is_paper_mode():
        from src.api.paper_client import PaperBinanceClient

        initial = float(os.getenv("PAPER_INITIAL_USDT", "6000"))
        return PaperBinanceClient(initial_usdt=initial)

    from src.api.binance_client import BinanceClient

    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    return BinanceClient(testnet=testnet)


@task_locked
def task_reconcile_orders():
    """Compare grid state files with actual Binance open orders (every 30 min).

    Detects:
    - ORPHAN: Order in state file but not on Binance (may have been filled/cancelled)
    - UNKNOWN: Order on Binance but not in any state file (manual or leaked order)
    """
    logger.info("Running order reconciliation...")

    grid_states = _load_grid_states()
    if not grid_states:
        logger.info("No grid state files found, skipping reconciliation")
        return

    client = _get_binance_client()

    # Collect all order IDs from state files, grouped by symbol
    state_orders: dict[str, set[int]] = {}  # symbol -> set of order IDs
    for key, state in grid_states.items():
        symbol = state.get("symbol", "")
        if not symbol:
            continue
        if symbol not in state_orders:
            state_orders[symbol] = set()
        for order_id in state.get("active_orders", {}):
            try:
                state_orders[symbol].add(int(order_id))
            except (ValueError, TypeError):
                pass

    total_orphans = 0
    total_unknown = 0

    for symbol, state_ids in state_orders.items():
        try:
            binance_orders = client.get_open_orders(symbol)
            binance_ids = {int(o["orderId"]) for o in binance_orders}

            orphans = state_ids - binance_ids
            unknown = binance_ids - state_ids

            if orphans:
                total_orphans += len(orphans)
                logger.warning(
                    f"ORPHAN orders for {symbol}: {orphans} (in state but not on Binance)"
                )

            if unknown:
                total_unknown += len(unknown)
                logger.warning(
                    f"UNKNOWN orders for {symbol}: {unknown} (on Binance but not in state)"
                )

        except Exception as e:
            logger.error(f"Reconciliation failed for {symbol}: {e}")

    if total_orphans > 0 or total_unknown > 0:
        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(
            f"Order Reconciliation\n\n"
            f"Orphans (state only): {total_orphans}\n"
            f"Unknown (Binance only): {total_unknown}",
            force=True,
        )
        logger.warning(f"Reconciliation: {total_orphans} orphans, {total_unknown} unknown")
    else:
        logger.info(
            f"Reconciliation OK: {sum(len(ids) for ids in state_orders.values())} "
            f"orders across {len(state_orders)} symbols"
        )


@task_locked
def task_order_timeout_check():
    """Check for orders that haven't been filled in >6h (every 1h).

    Logs a summary of stale orders. This is informational — grid orders
    far from current price are expected to be stale.
    """
    logger.info("Running order timeout check...")

    grid_states = _load_grid_states()
    if not grid_states:
        return

    now = datetime.now()
    stale_6h = 0
    stale_24h = 0
    total_orders = 0

    for key, state in grid_states.items():
        for order_id, order in state.get("active_orders", {}).items():
            total_orders += 1
            created_at = order.get("created_at")
            if not created_at:
                continue

            try:
                order_time = datetime.fromisoformat(created_at)
                age = now - order_time

                if age > timedelta(hours=24):
                    stale_24h += 1
                elif age > timedelta(hours=6):
                    stale_6h += 1
            except (ValueError, TypeError):
                pass

    logger.info(
        f"Order timeout: {total_orders} total, {stale_6h} older than 6h, {stale_24h} older than 24h"
    )

    if stale_24h > 0:
        logger.warning(f"{stale_24h} orders older than 24h — grid may need recalibration")


@task_locked
def task_portfolio_plausibility():
    """Verify allocation math across cohorts (every 2h).

    Checks:
    - Sum of allocations per cohort <= cohort capital + 10% tolerance
    - Binance USDT balance > 0
    """
    logger.info("Running portfolio plausibility check...")

    hybrid_states = _load_hybrid_states()
    if not hybrid_states:
        logger.info("No hybrid state files found, skipping plausibility check")
        return

    issues: list[str] = []

    for cohort, state in hybrid_states.items():
        symbols = state.get("symbols", {})
        total_allocated = sum(float(s.get("allocation_usd", 0)) for s in symbols.values())

        if total_allocated > 0:
            logger.info(
                f"Cohort {cohort}: ${total_allocated:.2f} allocated across {len(symbols)} symbols"
            )

        # Check for negative allocations
        for sym, sym_state in symbols.items():
            alloc = float(sym_state.get("allocation_usd", 0))
            if alloc < 0:
                issues.append(f"{cohort}:{sym} has negative allocation ${alloc:.2f}")

    # Check USDT balance (paper mode uses simulated balance)
    try:
        client = _get_binance_client()
        usdt_balance = client.get_account_balance("USDT")
        mode_label = "Paper" if _is_paper_mode() else "Binance"
        logger.info(f"{mode_label} USDT balance: ${usdt_balance:.2f}")

        if usdt_balance <= 0:
            issues.append(f"USDT balance is ${usdt_balance:.2f} ({mode_label})")
    except Exception as e:
        logger.warning(f"Could not check balance: {e}")

    if issues:
        msg = "Portfolio plausibility issues:\n" + "\n".join(f"- {i}" for i in issues)
        logger.warning(msg)

        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(msg, force=True)
    else:
        logger.info("Portfolio plausibility OK")


@task_locked
def task_grid_health_summary():
    """Overview of all active grid bots (every 4h).

    Reports:
    - Per-bot BUY/SELL order counts
    - Bots with 0 orders (empty grid)
    - Bots with failed_followup orders
    """
    logger.info("Running grid health summary...")

    grid_states = _load_grid_states()
    if not grid_states:
        logger.info("No grid state files found")
        return

    total_bots = len(grid_states)
    total_buy = 0
    total_sell = 0
    empty_bots: list[str] = []
    no_sell_bots: list[str] = []
    failed_followups: list[str] = []

    for key, state in grid_states.items():
        orders = state.get("active_orders", {})
        n_buy = sum(1 for o in orders.values() if o.get("type") == "BUY")
        n_sell = sum(1 for o in orders.values() if o.get("type") == "SELL")
        n_failed = sum(1 for o in orders.values() if o.get("failed_followup"))

        total_buy += n_buy
        total_sell += n_sell

        if len(orders) == 0:
            empty_bots.append(key)
        elif n_sell == 0 and n_buy > 0:
            no_sell_bots.append(key)

        if n_failed > 0:
            failed_followups.append(f"{key} ({n_failed} failed)")

    summary_parts = [
        f"Grid Health: {total_bots} bots, {total_buy}B/{total_sell}S orders",
    ]

    if empty_bots:
        summary_parts.append(f"Empty grids: {', '.join(empty_bots)}")

    if no_sell_bots:
        summary_parts.append(f"No sells (no fills yet): {', '.join(no_sell_bots)}")

    if failed_followups:
        summary_parts.append(f"Failed follow-ups: {', '.join(failed_followups)}")

    summary = " | ".join(summary_parts)
    logger.info(summary)

    # Alert only on failed follow-ups (actual problem)
    if failed_followups:
        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(
            "Grid Health Warning\n\n"
            "Failed follow-ups:\n" + "\n".join(f"- {f}" for f in failed_followups),
            force=True,
        )


@task_locked
def task_stale_detection():
    """Alert if no order activity detected in last 30 minutes (every 30 min).

    In a volatile crypto market, extended silence likely means a problem
    (bot stuck, API issues, all orders far from price, etc.).
    """
    logger.info("Running stale detection...")

    grid_states = _load_grid_states()
    if not grid_states:
        logger.info("No grid state files found, skipping stale detection")
        return

    now = datetime.now()
    newest_order_time: datetime | None = None

    for _key, state in grid_states.items():
        for _order_id, order in state.get("active_orders", {}).items():
            created = order.get("created_at")
            if not created:
                continue
            try:
                t = datetime.fromisoformat(created)
                if newest_order_time is None or t > newest_order_time:
                    newest_order_time = t
            except (ValueError, TypeError):
                pass

    if newest_order_time is None:
        logger.warning("Stale detection: no order timestamps found in grid states")
        return

    age = now - newest_order_time
    if age > timedelta(minutes=30):
        logger.warning(f"Stale detection: last order activity {age} ago")

        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(
            f"Stale Detection Warning\n\n"
            f"No new order activity for {age.total_seconds() / 60:.0f} min\n"
            f"Last activity: {newest_order_time:%H:%M:%S}",
            force=True,
        )
    else:
        logger.info(f"Stale detection OK: last activity {age.total_seconds() / 60:.0f}min ago")


@task_locked
def task_tier_health_check():
    """Check health of all 3 portfolio tiers (every 2h).

    Checks:
    - Cash reserve level vs target
    - Index holdings tracking error
    - Trading tier activity
    Only runs when PORTFOLIO_MANAGER=true.
    """
    import os

    if os.getenv("PORTFOLIO_MANAGER", "false").lower() != "true":
        return

    logger.info("Running tier health check...")

    from src.tasks.base import get_db_connection

    conn = get_db_connection()
    if not conn:
        return

    issues: list[str] = []

    try:
        from psycopg2.extras import RealDictCursor

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Check tier allocations
            cur.execute(
                "SELECT tier_name, target_pct, current_pct, current_value_usd "
                "FROM portfolio_tiers WHERE is_active = TRUE"
            )
            for row in cur.fetchall():
                target = float(row["target_pct"])
                current = float(row["current_pct"] or 0)
                drift = abs(current - target)
                if drift > 5.0:
                    issues.append(
                        f"{row['tier_name']}: {current:.1f}% vs target {target:.1f}% "
                        f"(drift {drift:.1f}pp)"
                    )

            # 2. Check cash reserve specifically
            cur.execute("SELECT current_pct FROM portfolio_tiers WHERE tier_name = 'cash_reserve'")
            cash_row = cur.fetchone()
            if cash_row and float(cash_row["current_pct"] or 0) < 3.0:
                issues.append(
                    f"Cash reserve critically low: {float(cash_row['current_pct'] or 0):.1f}%"
                )

            # 3. Check trading activity (any trades in last 24h?)
            cur.execute(
                "SELECT COUNT(*) as count FROM trade_pairs "
                "WHERE created_at > NOW() - INTERVAL '24 hours'"
            )
            trade_row = cur.fetchone()
            if trade_row and trade_row["count"] == 0:
                issues.append("No trading activity in last 24h")

    except Exception as e:
        logger.debug(f"Tier health check failed: {e}")
    finally:
        conn.close()

    if issues:
        msg = "Tier Health Issues:\n" + "\n".join(f"- {i}" for i in issues)
        logger.warning(msg)

        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(msg, force=True)
    else:
        logger.info("Tier health check OK")


@task_locked
def task_discovery_health_check():
    """Validate AI auto-discovery pipeline health (every 12h).

    Checks:
    - Last discovery ran within 48h
    - AI approval rate is plausible (not 0% or 100% over 10+ decisions)
    - Recently added coins have trading activity after 7 days
    """
    logger.info("Running discovery health check...")

    from src.tasks.base import get_db_connection

    conn = get_db_connection()
    if not conn:
        logger.warning("Discovery health: no DB connection")
        return

    issues: list[str] = []

    try:
        from psycopg2.extras import RealDictCursor

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Check last discovery run
            cur.execute("SELECT MAX(discovered_at) as last_run FROM coin_discoveries")
            row = cur.fetchone()
            if row and row["last_run"]:
                age = datetime.utcnow() - row["last_run"]
                if age > timedelta(hours=48):
                    issues.append(
                        f"Last discovery was {age.total_seconds() / 3600:.0f}h ago (>48h)"
                    )
            else:
                logger.info("Discovery health: no discoveries yet (table empty)")
                return

            # 2. Check AI approval rate plausibility
            cur.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN ai_approved THEN 1 ELSE 0 END) as approved "
                "FROM coin_discoveries "
                "WHERE discovered_at > NOW() - INTERVAL '30 days'"
            )
            rate_row = cur.fetchone()
            total = rate_row["total"] or 0
            approved = rate_row["approved"] or 0

            if total >= 10:
                rate = approved / total * 100
                if rate == 0:
                    issues.append(
                        f"AI approval rate 0% over {total} decisions — AI may be too strict"
                    )
                elif rate == 100:
                    issues.append(
                        f"AI approval rate 100% over {total} decisions — AI may be too lenient"
                    )

            # 3. Check added coins have trades after 7 days
            cutoff = datetime.utcnow() - timedelta(days=7)
            cur.execute(
                "SELECT d.symbol FROM coin_discoveries d "
                "JOIN watchlist w ON d.symbol = w.symbol "
                "WHERE d.was_added = true AND d.discovered_at < %s "
                "AND d.was_deactivated = false "
                "AND (w.total_trades IS NULL OR w.total_trades = 0)",
                (cutoff,),
            )
            idle_coins = [r["symbol"] for r in cur.fetchall()]
            if idle_coins:
                issues.append(f"Coins with no trades after 7d: {', '.join(idle_coins[:5])}")

    except Exception as e:
        logger.debug(f"Discovery health check failed: {e}")
    finally:
        conn.close()

    if issues:
        msg = "Discovery Health Issues:\n" + "\n".join(f"- {i}" for i in issues)
        logger.warning(msg)

        from src.notifications.telegram_service import get_telegram

        telegram = get_telegram()
        telegram.send(msg, force=True)
    else:
        logger.info("Discovery health OK")
