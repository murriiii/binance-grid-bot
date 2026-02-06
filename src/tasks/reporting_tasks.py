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
    """Format price compactly: $97.3K, $2.7K, $0.145."""
    if price >= 100_000:
        return f"${price / 1000:,.0f}K"
    if price >= 1_000:
        return f"${price / 1000:,.1f}K"
    if price >= 1:
        return f"${price:,.2f}"
    return f"${price:.4f}"


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
        from src.api.binance_client import BinanceClient

        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        client = BinanceClient(testnet=testnet)
    except Exception:
        client = None

    # Load cohort info + realized P&L from DB
    cohort_info = {}
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
        except Exception as e:
            logger.debug(f"Cohort info query failed: {e}")
        finally:
            conn.close()

    # Pre-fetch all balances once (much faster than per-symbol queries)
    balances = {}
    if client:
        try:
            account = client.client.get_account()
            for b in account.get("balances", []):
                free = float(b["free"])
                locked = float(b["locked"])
                if free > 0 or locked > 0:
                    balances[b["asset"]] = free + locked
        except Exception as e:
            logger.debug(f"Failed to fetch balances: {e}")

    lines = ["<b>📊 PORTFOLIO DASHBOARD</b>", "━━━━━━━━━━━━━━━━━━━━━"]

    # Totals for footer
    total_starting = 0.0
    total_current = 0.0
    total_trades = 0
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
                if client:
                    try:
                        price = client.get_current_price(sym)
                        orders = client.client.get_open_orders(symbol=sym)
                        n_buy = sum(1 for o in orders if o["side"] == "BUY")
                        n_sell = sum(1 for o in orders if o["side"] == "SELL")
                        price_str = _format_price(price) if price else "—"
                        order_str = f"{n_buy}B/{n_sell}S"

                        # Calculate market value from held balance + locked in orders
                        held = balances.get(base, 0)
                        if price and held > 0:
                            mkt_val = held * price
                    except Exception:
                        pass

                # Show market value instead of static allocation
                val_str = f"${mkt_val:.0f}" if mkt_val >= 1 else f"${alloc:.0f}"
                cohort_market_value += mkt_val if mkt_val >= 1 else alloc
                coin_rows.append(f"  {base:<6s} {price_str:>8s}  {val_str:>5s}  {order_str}")

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
            total_trades += trade_count
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
        lines.append(f"🤖 {n_bots} Bots · {total_coins} Coins · {total_trades} Trades")

    return "\n".join(lines)


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

        # Per-cohort details
        cohort_status = _build_cohort_status()
        if cohort_status:
            telegram.send(cohort_status, disable_notification=True)

        data_sources_report = format_data_sources_report()
        if data_sources_report:
            telegram.send(data_sources_report, disable_notification=True)

        generate_performance_chart()

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
