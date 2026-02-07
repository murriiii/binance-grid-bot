"""Reporting and export tasks."""

import os

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger

COHORT_EMOJIS = {
    "conservative": "🛡️",
    "balanced": "⚖️",
    "aggressive": "⚔️",
    "baseline": "🧊",
    "defi_explorer": "🔬",
    "meme_hunter": "🎰",
}


def _format_price(price: float) -> str:
    """Format price compactly: $97.3K, $2.7K, $0.145, $0.00000857."""
    if price >= 100_000:
        return f"${price / 1000:,.0f}K"
    if price >= 1_000:
        return f"${price / 1000:,.1f}K"
    if price >= 1:
        return f"${price:,.2f}"
    if price >= 0.01:
        return f"${price:.4f}"
    if price >= 0.0001:
        return f"${price:.6f}"
    return f"${price:.8f}"


def _status_emoji(realized_pnl: float, trade_count: int) -> str:
    """Return status circle based on P&L."""
    if trade_count == 0:
        return "⚪"
    return "🟢" if realized_pnl >= 0 else "🔴"


def check_data_sources_status() -> dict[str, bool]:
    """Prüft welche Datenquellen verfügbar sind."""
    return {
        "lunarcrush": bool(os.getenv("LUNARCRUSH_API_KEY")),
        "reddit": bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET")),
        "token_unlocks": bool(os.getenv("TOKEN_UNLOCKS_API_KEY")),
        "deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    }


def format_data_sources_report() -> str:
    """Formatiert Datenquellen-Status für Telegram Report."""
    status = check_data_sources_status()

    unavailable = [name for name, available in status.items() if not available]

    if not unavailable:
        return ""

    labels = {
        "lunarcrush": "LunarCrush (kein API Key, $90/Mon)",
        "reddit": "Reddit (REDDIT_CLIENT_ID/SECRET fehlt)",
        "token_unlocks": "Token Unlocks (kein API Key)",
        "deepseek": "DeepSeek AI (kein API Key)",
        "telegram": "Telegram (Token/ChatID fehlt)",
    }

    report = "\n\n⚠️ *Inaktive Datenquellen:*\n"
    for name in unavailable:
        report += f"• {labels.get(name, name)}\n"

    return report


def generate_performance_chart():
    """Generiert und sendet Performance-Chart."""
    from src.notifications.telegram_service import get_telegram

    try:
        import io

        import matplotlib
        import matplotlib.pyplot as plt

        matplotlib.use("Agg")

        conn = get_db_connection()
        if not conn:
            return

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp::date as date, total_value_usd
                FROM portfolio_snapshots
                WHERE timestamp > NOW() - INTERVAL '30 days'
                ORDER BY timestamp
            """)
            data = cur.fetchall()

        conn.close()

        if len(data) < 2:
            logger.debug("Performance Chart: Nicht genug Daten (min. 2 Tage benötigt)")
            return

        else:
            dates = [d["date"] for d in data]
            values = [d["total_value_usd"] for d in data]

        plt.style.use("dark_background")
        _fig, ax = plt.subplots(figsize=(10, 6), facecolor="#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.plot(range(len(values)), values, color="#00ff88", linewidth=2)
        ax.fill_between(range(len(values)), values, alpha=0.3, color="#00ff88")
        ax.set_title("Portfolio Performance (30 Tage)", color="white", fontsize=14)
        ax.tick_params(colors="gray")
        ax.grid(True, alpha=0.3)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, facecolor="#1a1a2e", bbox_inches="tight")
        buf.seek(0)
        plt.close()

        telegram = get_telegram()
        telegram.send_photo(buf.getvalue(), "📈 <b>30-Tage Performance</b>")

    except Exception as e:
        logger.error(f"Chart Generation Error: {e}")


def _build_tier_report() -> str:
    """Build 3-tier portfolio report for daily summary.

    Only generates output when PORTFOLIO_MANAGER=true and tier data exists.
    """
    import os

    if os.getenv("PORTFOLIO_MANAGER", "false").lower() != "true":
        return ""

    conn = get_db_connection()
    if not conn:
        return ""

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT tier_name, target_pct, current_pct, current_value_usd "
                "FROM portfolio_tiers WHERE is_active = TRUE ORDER BY tier_name"
            )
            tiers = cur.fetchall()
    except Exception:
        return ""
    finally:
        conn.close()

    if not tiers:
        return ""

    total = sum(float(t["current_value_usd"] or 0) for t in tiers)
    emojis = {"cash_reserve": "💵", "index_holdings": "📊", "trading": "⚡"}

    lines = ["<b>🏦 TIER BREAKDOWN</b>", "━━━━━━━━━━━━━━━━━━━━━"]

    for t in tiers:
        name = t["tier_name"]
        target = float(t["target_pct"])
        current = float(t["current_pct"] or 0)
        value = float(t["current_value_usd"] or 0)
        drift = current - target
        emoji = emojis.get(name, "📋")

        drift_indicator = ""
        if abs(drift) > 3:
            drift_indicator = " ⚠️"

        lines.append(
            f"{emoji} {name}: <b>{current:.1f}%</b> (→{target:.0f}%) ${value:,.0f}{drift_indicator}"
        )

    lines.append(f"\n💰 <b>Total: ${total:,.2f}</b>")
    return "\n".join(lines)


def _build_cohort_status() -> str:
    """Build per-cohort dashboard for Telegram.

    Reads hybrid_state_{cohort}.json files and shows per-cohort
    performance with coins, orders, and P&L in a visual dashboard format.
    """
    import json
    from pathlib import Path

    config_dir = Path("config")
    if not config_dir.exists():
        return ""

    state_files = sorted(config_dir.glob("hybrid_state_*.json"))
    if not state_files:
        single = config_dir / "hybrid_state.json"
        if single.exists():
            state_files = [single]
        else:
            return ""

    try:
        paper_mode = os.getenv("PAPER_TRADING", "false").lower() == "true"
        if paper_mode:
            from src.api.paper_client import PaperBinanceClient

            initial = float(os.getenv("PAPER_INITIAL_USDT", "6000"))
            client = PaperBinanceClient(initial_usdt=initial)
        else:
            from src.api.binance_client import BinanceClient

            testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
            client = BinanceClient(testnet=testnet)
    except Exception:
        client = None

    # Load cohort info + realized P&L from DB
    cohort_info = {}
    open_pairs_by_cohort: dict[str, dict] = {}
    conn = get_db_connection()
    if conn:
        try:
            from psycopg2.extras import RealDictCursor as RDC

            with conn.cursor(cursor_factory=RDC) as cur:
                cur.execute(
                    "SELECT id, name, starting_capital, current_capital, config "
                    "FROM cohorts WHERE is_active = true"
                )
                for row in cur.fetchall():
                    cohort_info[row["name"]] = row

                # Per-cohort: realized P&L + open positions for unrealized P&L
                open_pairs_by_cohort: dict[str, dict] = {}
                for name, info in cohort_info.items():
                    try:
                        cur.execute(
                            "SELECT COALESCE(SUM(net_pnl), 0) as realized_pnl, "
                            "COUNT(*) as trade_count "
                            "FROM trade_pairs "
                            "WHERE cohort_id = %s AND status = 'closed'",
                            (info["id"],),
                        )
                        pnl_row = cur.fetchone()
                        info["realized_pnl"] = float(pnl_row["realized_pnl"])
                        info["trade_count"] = pnl_row["trade_count"]
                    except Exception:
                        info["realized_pnl"] = 0.0
                        info["trade_count"] = 0

                    # Open trade pairs for per-coin unrealized P&L
                    try:
                        cur.execute(
                            "SELECT symbol, "
                            "COALESCE(SUM(entry_value_usd), 0) as cost_basis, "
                            "COALESCE(SUM(remaining_quantity), 0) as total_qty "
                            "FROM trade_pairs "
                            "WHERE cohort_id = %s AND status = 'open' "
                            "GROUP BY symbol",
                            (info["id"],),
                        )
                        pairs = {}
                        for row in cur.fetchall():
                            pairs[row["symbol"]] = {
                                "cost_basis": float(row["cost_basis"]),
                                "total_qty": float(row["total_qty"]),
                            }
                        open_pairs_by_cohort[name] = pairs
                    except Exception:
                        open_pairs_by_cohort[name] = {}
        except Exception as e:
            logger.debug(f"Cohort info query failed: {e}")
        finally:
            conn.close()

    # Pre-load all grid state files to get actual held quantities per cohort+symbol.
    # SELL orders in grid state = coins the bot bought and is holding.
    # Using account balance would include pre-loaded testnet balances.
    grid_states: dict[str, dict] = {}  # key: "{cohort}:{symbol}" -> grid state
    for gs_file in config_dir.glob("grid_state_*_*.json"):
        try:
            with open(gs_file) as gf:
                gs = json.load(gf)
            # filename: grid_state_BTCUSDT_conservative.json
            parts = gs_file.stem.replace("grid_state_", "").rsplit("_", 1)
            if len(parts) == 2:
                grid_sym, grid_cohort = parts
                grid_states[f"{grid_cohort}:{grid_sym}"] = gs
        except Exception:
            pass

    lines = ["<b>📊 PORTFOLIO DASHBOARD</b>", "━━━━━━━━━━━━━━━━━━━━━"]

    # Totals for footer
    total_starting = 0.0
    total_current = 0.0
    total_closed_trades = 0
    total_open_orders = 0
    total_buy_orders = 0
    total_sell_orders = 0
    total_coins = 0

    for sf in state_files:
        try:
            with open(sf) as f:
                state = json.load(f)

            fname = sf.stem
            cohort_name = fname.replace("hybrid_state_", "") if "_" in fname else "default"

            db_info = cohort_info.get(cohort_name, {})
            starting = float(db_info.get("starting_capital", 1000)) if db_info else 1000.0
            config_data = db_info.get("config", {}) if db_info else {}
            grid_pct = config_data.get("grid_range_pct", "?") if config_data else "?"

            total_investment = state.get("config", {}).get("total_investment", starting)
            total_allocated = 0.0
            cohort_market_value = 0.0
            coin_rows = []

            for sym, sdata in state.get("symbols", {}).items():
                alloc = sdata.get("allocation_usd", 0)
                total_allocated += alloc
                base = sym.replace("USDT", "")

                price_str = "—"
                order_str = "—"
                mkt_val = 0.0
                n_buy = 0
                n_sell = 0
                if client:
                    try:
                        price = client.get_current_price(sym)
                        orders = client.get_open_orders(sym)
                        n_buy = sum(1 for o in orders if o["side"] == "BUY")
                        n_sell = sum(1 for o in orders if o["side"] == "SELL")
                        price_str = _format_price(price) if price else "—"
                        order_str = f"{n_buy}B/{n_sell}S"

                        # Calculate market value from grid state:
                        # - SELL orders = coins the bot bought and holds
                        #   → valued at current market price (unrealized P&L)
                        # - BUY orders = USDT locked, no P&L swing
                        #   → use their cost basis (price * qty)
                        # Remaining alloc not in any order stays at face value
                        gs_key = f"{cohort_name}:{sym}"
                        gs = grid_states.get(gs_key, {})
                        active = gs.get("active_orders", {})
                        buy_cost = sum(
                            float(o.get("price", 0)) * float(o.get("quantity", 0))
                            for o in active.values()
                            if o.get("type") == "BUY"
                        )
                        sell_cost = sum(
                            float(o.get("price", 0)) * float(o.get("quantity", 0))
                            for o in active.values()
                            if o.get("type") == "SELL"
                        )
                        held_value = (
                            sum(
                                float(o.get("quantity", 0)) * price
                                for o in active.values()
                                if o.get("type") == "SELL"
                            )
                            if price
                            else sell_cost
                        )
                        # Total order cost = what was originally allocated to orders
                        order_cost = buy_cost + sell_cost
                        # Unallocated remainder stays at face value
                        remainder = max(0, alloc - order_cost)
                        if active:
                            mkt_val = buy_cost + held_value + remainder
                    except Exception:
                        pass
                total_open_orders += n_buy + n_sell
                total_buy_orders += n_buy
                total_sell_orders += n_sell

                # Show market value if holding, otherwise allocation
                val_str = f"${mkt_val:.0f}" if mkt_val >= 1 else f"${alloc:.0f}"
                cohort_market_value += mkt_val if mkt_val >= 1 else alloc

                # Per-coin unrealized P&L from open trade pairs
                coin_pnl_str = ""
                op = open_pairs_by_cohort.get(cohort_name, {}).get(sym)
                if op and price and op["cost_basis"] > 0:
                    coin_upnl = op["total_qty"] * price - op["cost_basis"]
                    coin_upnl_pct = coin_upnl / op["cost_basis"] * 100
                    coin_pnl_str = f" {coin_upnl:+.1f}$({coin_upnl_pct:+.1f}%)"

                coin_rows.append(
                    f"  {base:<5s} {price_str:>8s} {val_str:>5s}{coin_pnl_str} {order_str}"
                )

            cash_reserve = total_investment - total_allocated
            # Total current value = cash reserve + market value of positions
            current_value = cash_reserve + cohort_market_value

            realized_pnl = db_info.get("realized_pnl", 0.0) if db_info else 0.0
            trade_count = db_info.get("trade_count", 0) if db_info else 0

            # Unrealized P&L = market value vs allocation cost
            unrealized_pnl = cohort_market_value - total_allocated
            total_pnl = realized_pnl + unrealized_pnl

            # Accumulate totals
            total_starting += starting
            total_current += current_value
            total_closed_trades += trade_count
            total_coins += len(coin_rows)

            # P&L percentage based on total (realized + unrealized)
            if starting > 0 and total_pnl != 0:
                pnl_pct = total_pnl / starting * 100
                value_str = f"${starting:,.0f} → ${current_value:,.0f} ({pnl_pct:+.1f}%)"
            else:
                value_str = f"${starting:,.0f} → ${current_value:,.0f} (±0.0%)"

            emoji = COHORT_EMOJIS.get(cohort_name, "🤖")
            status = _status_emoji(total_pnl, 1 if total_allocated > 0 else 0)
            mode = state.get("current_mode", "?")

            lines.append(f"\n{emoji} <b>{cohort_name.upper()}</b>  {status}")
            lines.append(f"<code>{value_str}</code>")
            lines.append(f"⚙️ Grid {grid_pct}% | Mode: {mode}")

            alloc_pct = total_allocated / total_investment * 100 if total_investment else 0
            lines.append(
                f"💰 ${total_allocated:,.0f} inv. ({alloc_pct:.0f}%) · 💵 ${cash_reserve:,.0f} cash"
            )

            if unrealized_pnl != 0:
                lines.append(f"📊 uP&L: <b>{unrealized_pnl:+.2f}$</b>")
            if trade_count > 0:
                lines.append(f"📈 rP&L: <b>{realized_pnl:+.2f}$</b> · {trade_count} Trades")

            if coin_rows:
                lines.append("<code>" + "\n".join(coin_rows) + "</code>")

        except Exception as e:
            logger.debug(f"Failed to read {sf}: {e}")

    if len(lines) <= 2:
        return ""

    # Footer
    if total_starting > 0:
        total_pnl_pct = (total_current - total_starting) / total_starting * 100
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"📈 <b>Total:</b> ${total_starting:,.0f} → "
            f"${total_current:,.0f} ({total_pnl_pct:+.1f}%)"
        )
        n_bots = len(state_files)
        orders_str = f"📋 {total_open_orders} Orders ({total_buy_orders}B/{total_sell_orders}S)"
        if total_closed_trades > 0:
            orders_str += f" · ✅ {total_closed_trades} Closed"
        lines.append(f"🤖 {n_bots} Bots · {total_coins} Coins · {orders_str}")

    return "\n".join(lines)


def _build_cohort_comparison() -> str:
    """Build cohort comparison ranking for Telegram.

    Compares all active cohorts by realized P&L, win rate, and trade count.
    Uses trade_pairs table for live data (not trading_cycles which need completed cycles).
    """
    conn = get_db_connection()
    if not conn:
        return ""

    try:
        from psycopg2.extras import RealDictCursor as RDC

        with conn.cursor(cursor_factory=RDC) as cur:
            cur.execute("SELECT id, name, starting_capital FROM cohorts WHERE is_active = true")
            cohorts = cur.fetchall()

            if len(cohorts) < 2:
                return ""

            rows = []
            for c in cohorts:
                cur.execute(
                    "SELECT "
                    "COALESCE(SUM(net_pnl), 0) as total_pnl, "
                    "COUNT(*) as trades, "
                    "SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins "
                    "FROM trade_pairs "
                    "WHERE cohort_id = %s AND status = 'closed'",
                    (c["id"],),
                )
                tp = cur.fetchone()
                total_pnl = float(tp["total_pnl"])
                trades = tp["trades"]
                wins = tp["wins"] or 0
                starting = float(c["starting_capital"])
                pnl_pct = total_pnl / starting * 100 if starting > 0 else 0.0
                win_rate = wins / trades * 100 if trades > 0 else 0.0

                rows.append(
                    {
                        "name": c["name"],
                        "pnl": total_pnl,
                        "pnl_pct": pnl_pct,
                        "trades": trades,
                        "win_rate": win_rate,
                    }
                )

            # Rank by P&L% descending
            rows.sort(key=lambda r: r["pnl_pct"], reverse=True)

            lines = [
                "<b>🏆 COHORT COMPARISON</b>",
                "━━━━━━━━━━━━━━━━━━━━━",
                "<code>#  Cohort         P&L%  WinR Trades</code>",
            ]

            for i, r in enumerate(rows, 1):
                emoji = COHORT_EMOJIS.get(r["name"], "🤖")
                name = f"{emoji}{r['name']}"
                lines.append(
                    f"<code>{i}  {name:<14s} {r['pnl_pct']:+5.1f}% "
                    f"{r['win_rate']:4.0f}%  {r['trades']:4d}</code>"
                )

            # Spread: best vs worst
            if len(rows) >= 2:
                spread = rows[0]["pnl_pct"] - rows[-1]["pnl_pct"]
                lines.append(f"📊 Spread: {spread:.1f}pp ({rows[0]['name']} vs {rows[-1]['name']})")

            return "\n".join(lines)

    except Exception as e:
        logger.debug(f"Cohort comparison failed: {e}")
        return ""
    finally:
        conn.close()


def task_daily_summary():
    """Tägliche Portfolio-Zusammenfassung um 20:00."""
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram

    logger.info("Running daily summary...")

    conn = get_db_connection()
    if not conn:
        telegram = get_telegram()
        telegram.send("Daily Summary: DB nicht erreichbar")
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN outcome_24h > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(outcome_24h) as avg_return
                FROM trades
                WHERE timestamp::date = CURRENT_DATE
            """)
            today_stats = cur.fetchone()

            cur.execute("""
                SELECT total_value_usd, daily_pnl_pct
                FROM portfolio_snapshots
                ORDER BY timestamp DESC LIMIT 1
            """)
            portfolio = cur.fetchone() or {"total_value_usd": 10, "daily_pnl_pct": 0}

        conn.close()

        market_data = get_market_data()
        fear_greed = market_data.get_fear_greed()

        trade_count = today_stats["trade_count"] or 0
        wins = today_stats["wins"] or 0
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0

        telegram = get_telegram()
        telegram.send_daily_summary(
            portfolio_value=portfolio["total_value_usd"],
            daily_change=portfolio["daily_pnl_pct"],
            trades_today=trade_count,
            win_rate=win_rate,
            fear_greed=fear_greed.value,
        )

        # Tier breakdown (if PORTFOLIO_MANAGER mode)
        tier_report = _build_tier_report()
        if tier_report:
            telegram.send(tier_report, disable_notification=True)

        # Per-cohort details
        cohort_status = _build_cohort_status()
        if cohort_status:
            telegram.send(cohort_status, disable_notification=True)

        # Cohort comparison ranking
        comparison = _build_cohort_comparison()
        if comparison:
            telegram.send(comparison, disable_notification=True)

        data_sources_report = format_data_sources_report()
        if data_sources_report:
            telegram.send(data_sources_report, disable_notification=True)

        generate_performance_chart()

        # Store metrics snapshot for portfolio_snapshots tracking
        try:
            from src.analysis.metrics_calculator import MetricsCalculator

            mc = MetricsCalculator.get_instance()
            metrics_conn = get_db_connection()
            if metrics_conn:
                try:
                    with metrics_conn.cursor() as mcur:
                        mcur.execute(
                            "SELECT outcome_24h FROM trades "
                            "WHERE timestamp > NOW() - INTERVAL '30 days' "
                            "AND outcome_24h IS NOT NULL ORDER BY timestamp"
                        )
                        returns = [float(r[0]) for r in mcur.fetchall()]
                finally:
                    metrics_conn.close()

                if len(returns) >= 2:
                    metrics = mc.calculate_all_metrics(returns)
                    mc.store_snapshot(
                        metrics,
                        portfolio_value=portfolio.get("total_value_usd"),
                        fear_greed=fear_greed.value if fear_greed else None,
                    )
                    logger.info("Metrics snapshot stored")
        except Exception as me:
            logger.debug(f"Metrics snapshot failed (non-critical): {me}")

    except Exception as e:
        logger.error(f"Daily Summary Error: {e}")
        telegram = get_telegram()
        telegram.send_error(str(e), context="Daily Summary")


def task_update_playbook():
    """Aktualisiert das Trading Playbook. Läuft wöchentlich (Sonntag 19:00)."""
    from src.notifications.telegram_service import get_telegram

    logger.info("Updating Trading Playbook...")

    conn = get_db_connection()
    if not conn:
        logger.error("Playbook Update: Keine DB-Verbindung")
        telegram = get_telegram()
        telegram.send("⚠️ Playbook Update: DB nicht erreichbar")
        return

    try:
        from src.data.playbook import TradingPlaybook

        playbook = TradingPlaybook(db_connection=conn)
        result = playbook.analyze_and_update()

        telegram = get_telegram()

        if "error" in result:
            logger.error(f"Playbook Update Fehler: {result['error']}")
            telegram.send(f"⚠️ Playbook Update Fehler: {result['error']}")
        else:
            version = result.get("version", 0)
            changes = result.get("changes", [])
            metrics = result.get("metrics", {})

            message = f"""📚 <b>PLAYBOOK AKTUALISIERT</b>

Version: <b>{version}</b>
Basiert auf: <b>{metrics.get("total_trades", 0)} Trades</b>
Erfolgsrate: <b>{metrics.get("success_rate", 0):.1f}%</b>

<b>Änderungen:</b>
"""
            for change in changes[:5]:
                message += f"• {change}\n"

            fg_patterns = metrics.get("fear_greed_patterns", [])
            if fg_patterns:
                best_pattern = max(fg_patterns, key=lambda x: x["success_rate"])
                message += f"""
<b>Beste Strategie:</b>
{best_pattern["action"]} bei {best_pattern["range"]}: {best_pattern["success_rate"]:.0f}% Erfolg
"""

            anti_patterns = metrics.get("anti_patterns", [])
            if anti_patterns:
                worst = anti_patterns[0]
                message += f"""
<b>Zu vermeiden:</b>
{worst["action"]} {worst["symbol"]} bei F&G={worst["fear_greed"]}: {worst["avg_return"]:+.1f}%
"""

            telegram.send(message)
            logger.info(f"Playbook v{version} erfolgreich aktualisiert")

    except Exception as e:
        logger.exception(f"Playbook Update Error: {e}")
        telegram = get_telegram()
        telegram.send_error(str(e), context="Playbook Update")

    finally:
        if conn:
            conn.close()


def task_weekly_export():
    """Erstellt wöchentlichen Export. Läuft Samstag 23:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Running weekly export for Claude Code analysis...")

    try:
        from src.analysis.weekly_export import WeeklyExporter

        exporter = WeeklyExporter()
        result = exporter.export_weekly_analysis()

        trading_logger = get_logger()
        trading_logger.playbook_updated(
            version=0,
            changes=["Weekly export generated"],
            patterns_found=result["summary"]["total_trades"],
            anti_patterns_found=result["summary"]["error_count"],
        )

        summary = result["summary"]
        message = f"""📊 <b>WEEKLY EXPORT READY</b>

Export für Claude Code Analyse erstellt:

<b>Performance:</b>
• Trades: {summary["total_trades"]}
• Win Rate: {summary["win_rate"]:.1%}
• Total P&L: ${summary["total_pnl"]:.2f}

<b>System:</b>
• Errors: {summary["error_count"]}

<b>Export-Pfad:</b>
<code>{result["export_path"]}</code>

<i>Bereit für wöchentliche Claude Code Analyse.</i>
"""
        telegram = get_telegram()
        telegram.send(message)
        logger.info(f"Weekly export completed: {result['export_path']}")

    except Exception as e:
        logger.exception(f"Weekly Export Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Weekly export failed", e, {"task": "weekly_export"})
        telegram = get_telegram()
        telegram.send_error(str(e), context="Weekly Export")
