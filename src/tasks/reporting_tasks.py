"""Reporting and export tasks."""

import os

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger


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


def task_daily_summary():
    """Tägliche Portfolio-Zusammenfassung um 20:00."""
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram

    logger.info("Running daily summary...")

    conn = get_db_connection()
    if not conn:
        telegram = get_telegram()
        telegram.send("⚠️ Daily Summary: DB nicht erreichbar")
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
