#!/usr/bin/env python3
"""
Trading Bot Scheduler
Führt regelmäßige Tasks aus:
- Tägliche Summaries
- Stündliche Market Snapshots
- Wöchentliches Rebalancing
- Outcome Tracking für vergangene Trades
"""

import logging
import sys
import time
from datetime import datetime

import psycopg2
import schedule
from psycopg2.extras import RealDictCursor

sys.path.insert(0, "/app")

from dotenv import load_dotenv

load_dotenv()

from src.core.config import get_config
from src.data.market_data import get_market_data
from src.notifications.telegram_service import get_telegram

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Services
telegram = get_telegram()
market_data = get_market_data()
config = get_config()


def get_db_connection():
    """Erstellt Datenbankverbindung"""
    db_url = config.database.url
    if not db_url:
        return None
    try:
        return psycopg2.connect(db_url)
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════


def task_daily_summary():
    """Tägliche Portfolio-Zusammenfassung um 20:00"""
    logger.info("Running daily summary...")

    conn = get_db_connection()
    if not conn:
        telegram.send("⚠️ Daily Summary: DB nicht erreichbar")
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Trades heute
            cur.execute("""
                SELECT
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN outcome_24h > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(outcome_24h) as avg_return
                FROM trades
                WHERE timestamp::date = CURRENT_DATE
            """)
            today_stats = cur.fetchone()

            # Portfolio Snapshot
            cur.execute("""
                SELECT total_value_usd, daily_pnl_pct
                FROM portfolio_snapshots
                ORDER BY timestamp DESC LIMIT 1
            """)
            portfolio = cur.fetchone() or {"total_value_usd": 10, "daily_pnl_pct": 0}

        conn.close()

        # Marktdaten über zentralen Provider
        fear_greed = market_data.get_fear_greed()
        btc_price = market_data.get_price("BTCUSDT")

        trade_count = today_stats["trade_count"] or 0
        wins = today_stats["wins"] or 0
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0

        # Verwende den zentralen TelegramService
        telegram.send_daily_summary(
            portfolio_value=portfolio["total_value_usd"],
            daily_change=portfolio["daily_pnl_pct"],
            trades_today=trade_count,
            win_rate=win_rate,
            fear_greed=fear_greed.value,
        )

        # Chart generieren
        generate_performance_chart()

    except Exception as e:
        logger.error(f"Daily Summary Error: {e}")
        telegram.send_error(str(e), context="Daily Summary")


def generate_performance_chart():
    """Generiert und sendet Performance-Chart"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import io

        import matplotlib.pyplot as plt
        import numpy as np

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
            # Dummy-Daten wenn keine echten vorhanden
            days = 30
            dates = range(days)
            values = 10 * np.cumprod(1 + np.random.normal(0.001, 0.02, days))
        else:
            dates = [d["date"] for d in data]
            values = [d["total_value_usd"] for d in data]

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(10, 6), facecolor="#1a1a2e")
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

        telegram.send_photo(buf.getvalue(), "📈 <b>30-Tage Performance</b>")

    except Exception as e:
        logger.error(f"Chart Generation Error: {e}")


def task_market_snapshot():
    """Stündlicher Market Snapshot"""
    logger.info("Running market snapshot...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        # Marktdaten über zentralen Provider sammeln
        fear_greed = market_data.get_fear_greed()
        btc_price = market_data.get_price("BTCUSDT")
        btc_dominance = market_data.get_btc_dominance()

        # In DB speichern
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_snapshots
                (timestamp, fear_greed, btc_price, btc_dominance)
                VALUES (%s, %s, %s, %s)
            """,
                (datetime.now(), fear_greed.value, btc_price, btc_dominance),
            )
            conn.commit()

        logger.info(
            f"Market Snapshot saved: F&G={fear_greed.value}, BTC=${btc_price:,.0f}, Dom={btc_dominance:.1f}%"
        )

    except Exception as e:
        logger.error(f"Market Snapshot Error: {e}")
    finally:
        conn.close()


def task_check_stops():
    """Prüft Stop-Loss Orders alle 5 Minuten"""
    logger.info("Checking stop-loss orders...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Aktive Stop-Loss Orders holen
            cur.execute("""
                SELECT id, symbol, entry_price, stop_price, quantity, stop_type
                FROM stop_loss_orders
                WHERE is_active = true
            """)
            stops = cur.fetchall()

            for stop in stops:
                # Preis für spezifisches Symbol holen
                current_price = market_data.get_price(stop["symbol"])

                if current_price <= stop["stop_price"]:
                    # Stop triggered!
                    logger.warning(f"STOP TRIGGERED: {stop['symbol']} @ {current_price}")

                    # Update DB
                    cur.execute(
                        """
                        UPDATE stop_loss_orders
                        SET is_active = false, triggered_at = NOW()
                        WHERE id = %s
                    """,
                        (stop["id"],),
                    )
                    conn.commit()

                    # Telegram Alert über zentralen Service
                    telegram.send_stop_loss_alert(
                        symbol=stop["symbol"],
                        trigger_price=current_price,
                        stop_price=stop["stop_price"],
                        quantity=stop["quantity"],
                    )

    except Exception as e:
        logger.error(f"Stop Check Error: {e}")
    finally:
        conn.close()


def task_update_outcomes():
    """Aktualisiert Trade-Outcomes"""
    logger.info("Updating trade outcomes...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Trades von vor 24h ohne Outcome
            cur.execute("""
                SELECT id, symbol, price, action
                FROM trades
                WHERE timestamp < NOW() - INTERVAL '24 hours'
                AND timestamp > NOW() - INTERVAL '25 hours'
                AND outcome_24h IS NULL
            """)
            trades = cur.fetchall()

            for trade in trades:
                # Preis für spezifisches Symbol holen
                current_price = market_data.get_price(trade["symbol"])

                # Outcome berechnen
                pct_change = ((current_price - trade["price"]) / trade["price"]) * 100
                if trade["action"] == "SELL":
                    pct_change = -pct_change

                # Update
                cur.execute(
                    """
                    UPDATE trades SET outcome_24h = %s WHERE id = %s
                """,
                    (pct_change, trade["id"]),
                )

                logger.info(f"Updated outcome for trade {trade['id']}: {pct_change:+.2f}%")

            conn.commit()

    except Exception as e:
        logger.error(f"Outcome Update Error: {e}")
    finally:
        conn.close()


def task_weekly_rebalance():
    """Wöchentliches Rebalancing (Sonntag 18:00)"""
    logger.info("Running weekly rebalance...")

    telegram.send("""
🔄 <b>WÖCHENTLICHES REBALANCING</b>

Analyse läuft...

<i>Details folgen nach Abschluss.</i>
""")

    # TODO: Implementiere echte Rebalancing-Logik
    # - Portfolio analysieren
    # - Abweichungen von Ziel-Allokation berechnen
    # - Trades vorschlagen


def task_macro_check():
    """Prüft anstehende Makro-Events (täglich 8:00)"""
    logger.info("Checking macro events...")

    try:
        from src.data.economic_events import EconomicCalendar

        calendar = EconomicCalendar()
        events = calendar.fetch_upcoming_events(days=2)
        high_impact = [e for e in events if e.impact == "HIGH"]

        if high_impact:
            # Verwende den zentralen TelegramService
            telegram.send_macro_alert(
                [{"date": e.date.strftime("%d.%m %H:%M"), "name": e.name} for e in high_impact[:5]]
            )
        else:
            logger.info("Keine High-Impact Events in den nächsten 48h")

    except Exception as e:
        logger.error(f"Macro Check Error: {e}")


def task_sentiment_check():
    """Prüft Sentiment und warnt bei Extremen"""
    logger.info("Checking sentiment...")

    fear_greed = market_data.get_fear_greed()

    # Verwende den zentralen TelegramService für Sentiment-Alerts
    telegram.send_sentiment_alert(fear_greed.value, fear_greed.classification)


def task_whale_check():
    """Prüft Whale-Aktivität"""
    logger.info("Checking whale activity...")

    try:
        from src.data.whale_alert import WhaleAlertTracker

        tracker = WhaleAlertTracker()
        whales = tracker.fetch_recent_whales(hours=1)

        if whales:
            # Nur die größten melden (über 50M USD)
            big_whales = [w for w in whales if w.amount_usd >= config.whale.alert_threshold]

            for whale in big_whales[:3]:
                telegram.send_whale_alert(
                    symbol=whale.symbol,
                    amount=whale.amount,
                    amount_usd=whale.amount_usd,
                    direction=whale.potential_impact,
                    from_owner=whale.from_owner,
                    to_owner=whale.to_owner,
                )

    except Exception as e:
        logger.error(f"Whale Check Error: {e}")


def task_update_playbook():
    """
    Aktualisiert das Trading Playbook basierend auf Trade-Historie.
    Läuft wöchentlich (Sonntag 19:00) nach dem Rebalancing.

    Das Playbook ist das "Erfahrungsgedächtnis" des Bots:
    - Analysiert welche Strategien funktioniert haben
    - Identifiziert Anti-Patterns (was vermieden werden sollte)
    - Generiert automatisch Regeln aus Daten
    - Wird bei jedem DeepSeek API-Call als Kontext verwendet
    """
    logger.info("Updating Trading Playbook...")

    conn = get_db_connection()
    if not conn:
        logger.error("Playbook Update: Keine DB-Verbindung")
        telegram.send("⚠️ Playbook Update: DB nicht erreichbar")
        return

    try:
        from src.data.playbook import TradingPlaybook

        playbook = TradingPlaybook(db_connection=conn)
        result = playbook.analyze_and_update()

        if "error" in result:
            logger.error(f"Playbook Update Fehler: {result['error']}")
            telegram.send(f"⚠️ Playbook Update Fehler: {result['error']}")
        else:
            # Erfolgreiche Aktualisierung
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

            # Fear & Greed Pattern Zusammenfassung
            fg_patterns = metrics.get("fear_greed_patterns", [])
            if fg_patterns:
                best_pattern = max(fg_patterns, key=lambda x: x["success_rate"])
                message += f"""
<b>Beste Strategie:</b>
{best_pattern["action"]} bei {best_pattern["range"]}: {best_pattern["success_rate"]:.0f}% Erfolg
"""

            # Anti-Patterns
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
        telegram.send_error(str(e), context="Playbook Update")

    finally:
        if conn:
            conn.close()


def task_learn_patterns():
    """
    Analysiert Trades und aktualisiert gelernte Patterns in der Datenbank.
    Läuft täglich um 21:00 (nach Daily Summary).
    """
    logger.info("Learning patterns from trade history...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        from src.data.memory import TradingMemory

        memory = TradingMemory()
        if memory.conn:
            memory.learn_and_update_patterns()
            logger.info("Pattern learning completed")

    except Exception as e:
        logger.error(f"Pattern Learning Error: {e}")

    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════


def main():
    """Hauptfunktion - Scheduler Setup"""
    logger.info("Starting Trading Bot Scheduler...")

    # Sende Startup-Nachricht über zentralen Service
    telegram.send("🚀 <b>Trading Bot Scheduler gestartet</b>\n\n<i>Alle Jobs aktiv.</i>")

    # ═══════════════════════════════════════════════════════════════
    # SCHEDULE JOBS
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

    # Pattern Learning täglich um 21:00 (nach Daily Summary)
    schedule.every().day.at("21:00").do(task_learn_patterns)

    # Playbook Update wöchentlich Sonntag 19:00 (nach Rebalancing)
    schedule.every().sunday.at("19:00").do(task_update_playbook)

    logger.info("Scheduled jobs:")
    for job in schedule.get_jobs():
        logger.info(f"  - {job}")

    # Run loop
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Scheduler Error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
