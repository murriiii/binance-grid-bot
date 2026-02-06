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
from src.core.logging_system import get_logger
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
trading_logger = get_logger()


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


def check_data_sources_status() -> dict[str, bool]:
    """
    Prüft welche Datenquellen verfügbar sind.
    Wird im Daily Summary Report verwendet.
    """
    import os

    status = {}

    # LunarCrush (kostenpflichtig, $90/Monat)
    status["lunarcrush"] = bool(os.getenv("LUNARCRUSH_API_KEY"))

    # Reddit API
    status["reddit"] = bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))

    # Token Unlocks API
    status["token_unlocks"] = bool(os.getenv("TOKEN_UNLOCKS_API_KEY"))

    # DeepSeek AI
    status["deepseek"] = bool(os.getenv("DEEPSEEK_API_KEY"))

    # Telegram
    status["telegram"] = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))

    return status


def format_data_sources_report() -> str:
    """Formatiert Datenquellen-Status für Telegram Report"""
    status = check_data_sources_status()

    unavailable = [name for name, available in status.items() if not available]

    if not unavailable:
        return ""

    report = "\n\n⚠️ *Inaktive Datenquellen:*\n"
    for name in unavailable:
        if name == "lunarcrush":
            report += "• LunarCrush (kein API Key, $90/Mon)\n"
        elif name == "reddit":
            report += "• Reddit (REDDIT_CLIENT_ID/SECRET fehlt)\n"
        elif name == "token_unlocks":
            report += "• Token Unlocks (kein API Key)\n"
        elif name == "deepseek":
            report += "• DeepSeek AI (kein API Key)\n"
        elif name == "telegram":
            report += "• Telegram (Token/ChatID fehlt)\n"
        else:
            report += f"• {name}\n"

    return report


# B3: Task locking - prevent concurrent execution
from src.utils.task_lock import task_locked

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

        # Datenquellen-Status melden (falls welche fehlen)
        data_sources_report = format_data_sources_report()
        if data_sources_report:
            telegram.send(data_sources_report, disable_notification=True)

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
        trading_logger.error("Pattern learning failed", e, {"task": "learn_patterns"})

    finally:
        if conn:
            conn.close()


def task_weekly_export():
    """
    Erstellt wöchentlichen Export für Claude Code Analyse.
    Läuft Samstag 23:00 - so ist alles bereit für Sonntags-Analyse.

    Der Export enthält:
    - Performance-Metriken der Woche
    - Trade-Statistiken
    - Error-Zusammenfassung
    - Playbook-Status
    - Empfehlungen für Optimierung
    """
    logger.info("Running weekly export for Claude Code analysis...")

    try:
        from src.analysis.weekly_export import WeeklyExporter

        exporter = WeeklyExporter()
        result = exporter.export_weekly_analysis()

        # Log the export
        trading_logger.playbook_updated(
            version=0,  # Will be updated with actual version
            changes=["Weekly export generated"],
            patterns_found=result["summary"]["total_trades"],
            anti_patterns_found=result["summary"]["error_count"],
        )

        # Telegram Benachrichtigung
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
        telegram.send(message)
        logger.info(f"Weekly export completed: {result['export_path']}")

    except Exception as e:
        logger.exception(f"Weekly Export Error: {e}")
        trading_logger.error("Weekly export failed", e, {"task": "weekly_export"})
        telegram.send_error(str(e), context="Weekly Export")


def task_system_health_check():
    """
    Prüft Systemgesundheit und loggt Metriken.
    Läuft alle 6 Stunden.
    """
    logger.info("Running system health check...")

    try:
        import psutil

        # Memory usage
        memory = psutil.virtual_memory()
        memory_usage_mb = memory.used / (1024 * 1024)

        # DB status
        conn = get_db_connection()
        db_status = "healthy" if conn else "unavailable"
        if conn:
            conn.close()

        # API status (quick check)
        try:
            btc_price = market_data.get_price("BTCUSDT")
            api_status = "healthy" if btc_price > 0 else "degraded"
        except Exception:
            api_status = "unavailable"

        overall_status = "healthy"
        if db_status != "healthy" or api_status != "healthy":
            overall_status = "degraded"

        # Log health
        trading_logger.system_health(
            status=overall_status,
            api_status=api_status,
            db_status=db_status,
            memory_usage_mb=memory_usage_mb,
        )

        if overall_status != "healthy":
            telegram.send(f"⚠️ <b>System Health Warning</b>\n\nDB: {db_status}\nAPI: {api_status}")

    except ImportError:
        # psutil not available, skip detailed metrics
        trading_logger.system_health(
            status="unknown",
            api_status="unknown",
            db_status="unknown",
        )
    except Exception as e:
        logger.error(f"Health Check Error: {e}")
        trading_logger.error("Health check failed", e, {"task": "health_check"})


# ═══════════════════════════════════════════════════════════════
# NEW TASKS - PHASE 2-5 ADDITIONS
# ═══════════════════════════════════════════════════════════════


def task_fetch_etf_flows():
    """
    Holt tägliche ETF-Flow Daten.
    Läuft täglich um 10:00 (nach US-Marktschluss).
    """
    logger.info("Fetching ETF flow data...")

    try:
        from src.data.etf_flows import ETFFlowTracker

        tracker = ETFFlowTracker.get_instance()
        flows = tracker.fetch_and_store_daily()

        if flows:
            signal, reasoning = tracker.get_institutional_signal()
            logger.info(f"ETF Flows: Signal={signal:.2f}, {reasoning}")

            # Alert bei starkem Signal
            if abs(signal) > 0.5:
                direction = "📈 BULLISH" if signal > 0 else "📉 BEARISH"
                telegram.send(f"""
🏦 <b>ETF FLOW ALERT</b>

{direction} Institutional Signal: {signal:.2f}

{reasoning}
""")

    except Exception as e:
        logger.error(f"ETF Flow Fetch Error: {e}")
        trading_logger.error("ETF flow fetch failed", e, {"task": "fetch_etf_flows"})


def task_fetch_social_sentiment():
    """
    Holt Social Media Sentiment Daten.
    Läuft alle 4 Stunden.
    """
    logger.info("Fetching social sentiment...")

    try:
        from src.data.social_sentiment import SocialSentimentProvider

        provider = SocialSentimentProvider.get_instance()

        # Fetch für wichtige Symbole
        symbols = ["BTC", "ETH", "SOL"]

        for symbol in symbols:
            metrics = provider.get_sentiment(symbol)

            if metrics:
                logger.info(
                    f"Social Sentiment {symbol}: "
                    f"Score={metrics.composite_sentiment:.2f}, "
                    f"Volume={metrics.social_volume}"
                )

                # Alert bei extremem Sentiment
                if abs(metrics.composite_sentiment) > 0.7:
                    direction = "🚀 EUPHORIE" if metrics.composite_sentiment > 0 else "😰 PANIK"
                    telegram.send(f"""
📱 <b>SOCIAL SENTIMENT ALERT</b>

{symbol}: {direction}
Composite Score: {metrics.composite_sentiment:.2f}
Social Volume: {metrics.social_volume:,}
""")

    except Exception as e:
        logger.error(f"Social Sentiment Fetch Error: {e}")
        trading_logger.error("Social sentiment fetch failed", e, {"task": "fetch_social_sentiment"})


def task_fetch_token_unlocks():
    """
    Holt anstehende Token Unlock Events.
    Läuft täglich um 08:00.
    """
    logger.info("Fetching token unlocks...")

    try:
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker.get_instance()
        unlocks = tracker.fetch_and_store_upcoming(days=14)

        # Finde signifikante Unlocks
        significant = tracker.get_significant_unlocks(days=7, min_pct=2.0)

        if significant:
            message = "🔓 <b>SIGNIFIKANTE TOKEN UNLOCKS</b>\n\n"

            for unlock in significant[:5]:
                impact_emoji = "🔴" if unlock.expected_impact == "HIGH" else "🟡"
                message += f"""
{impact_emoji} <b>{unlock.symbol}</b>
📅 {unlock.unlock_date.strftime("%d.%m.%Y")}
📊 {unlock.unlock_pct_of_supply:.1f}% Supply
💰 ${unlock.unlock_value_usd / 1_000_000:.1f}M
"""

            telegram.send(message)

        logger.info(f"Token Unlocks: {len(unlocks)} total, {len(significant)} significant")

    except Exception as e:
        logger.error(f"Token Unlock Fetch Error: {e}")
        trading_logger.error("Token unlock fetch failed", e, {"task": "fetch_token_unlocks"})


@task_locked
def task_regime_detection():
    """
    Erkennt aktuelles Markt-Regime (BULL/BEAR/SIDEWAYS).
    Läuft alle 4 Stunden.
    """
    logger.info("Running regime detection...")

    try:
        from src.analysis.regime_detection import RegimeDetector

        detector = RegimeDetector.get_instance()

        # Analysiere Hauptsymbol
        regime_state = detector.detect_regime("BTCUSDT")

        if not regime_state:
            logger.warning("Regime detection returned None - using SIDEWAYS fallback")

        if regime_state:
            logger.info(
                f"Market Regime: {regime_state.regime.value} "
                f"(probability: {regime_state.probability:.2f})"
            )

            # Speichere in DB
            detector.store_regime(regime_state)

            # Alert bei Regime-Wechsel
            # (Vergleiche mit letztem gespeicherten Regime)
            conn = get_db_connection()
            if conn:
                try:
                    from psycopg2.extras import RealDictCursor

                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT regime FROM regime_history
                            ORDER BY timestamp DESC
                            OFFSET 1 LIMIT 1
                        """)
                        prev = cur.fetchone()

                        if prev and prev["regime"] != regime_state.regime.value:
                            telegram.send(f"""
🔄 <b>REGIME CHANGE DETECTED</b>

{prev["regime"]} → <b>{regime_state.regime.value}</b>

Probability: {regime_state.probability:.1%}
Confidence: {regime_state.model_confidence:.1%}

<i>Signal-Gewichte werden angepasst.</i>
""")
                finally:
                    conn.close()

    except Exception as e:
        logger.error(f"Regime Detection Error: {e}")
        trading_logger.error("Regime detection failed", e, {"task": "regime_detection"})


def task_update_signal_weights():
    """
    Aktualisiert Bayesian Signal Weights basierend auf Performance.
    Läuft täglich um 22:00.
    """
    logger.info("Updating Bayesian signal weights...")

    try:
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner.get_instance()
        result = learner.weekly_update()

        updates_count = len(result.get("updates", []))
        errors_count = len(result.get("errors", []))

        logger.info(f"Bayesian Weights: {updates_count} updates, {errors_count} errors")

        if updates_count > 0:
            # Finde Global Update
            global_update = None
            for update in result["updates"]:
                if update["type"] == "global":
                    global_update = update
                    break

            if global_update:
                # Top 3 Signale
                weights = global_update["weights"]
                top_signals = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]

                message = f"""
📊 <b>SIGNAL WEIGHTS UPDATED</b>

Confidence: {global_update["confidence"]:.1%}
Sample Size: {global_update["sample_size"]} trades

<b>Top Signals:</b>
"""
                for name, weight in top_signals:
                    bar = "█" * int(weight * 20)
                    message += f"• {name}: {weight:.1%} {bar}\n"

                telegram.send(message)

    except Exception as e:
        logger.error(f"Signal Weight Update Error: {e}")
        trading_logger.error("Signal weight update failed", e, {"task": "update_signal_weights"})


@task_locked
def task_cycle_management():
    """
    Verwaltet Trading-Zyklen (wöchentlich).
    Läuft Sonntag um 00:00.

    - Schließt aktuellen Zyklus ab
    - Berechnet alle Metriken
    - Startet neuen Zyklus
    - Erstellt Vergleichsreport
    """
    logger.info("Running cycle management...")

    try:
        from src.core.cycle_manager import CycleManager

        manager = CycleManager.get_instance()

        # Für jede aktive Cohort
        conn = get_db_connection()
        if not conn:
            logger.error("Cycle Management: Keine DB-Verbindung")
            return

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name FROM cohorts WHERE is_active = TRUE")
                cohorts = cur.fetchall()

            cycle_reports = []

            for cohort in cohorts:
                cohort_id = str(cohort["id"])
                cohort_name = cohort["name"]

                # Aktuellen Zyklus schließen
                closed_cycle = manager.close_current_cycle(cohort_id)

                if closed_cycle:
                    logger.info(
                        f"Cycle {closed_cycle.cycle_number} closed for {cohort_name}: "
                        f"P&L={closed_cycle.total_pnl_pct:.2f}%"
                    )
                    cycle_reports.append(
                        {
                            "cohort": cohort_name,
                            "cycle": closed_cycle.cycle_number,
                            "pnl_pct": closed_cycle.total_pnl_pct or 0,
                            "sharpe": closed_cycle.sharpe_ratio or 0,
                            "trades": closed_cycle.total_trades or 0,
                        }
                    )

                # Neuen Zyklus starten
                new_cycle = manager.start_new_cycle(cohort_id)

                if new_cycle:
                    logger.info(f"Cycle {new_cycle.cycle_number} started for {cohort_name}")

            # Sende Zusammenfassung
            if cycle_reports:
                message = "📅 <b>WÖCHENTLICHER ZYKLUSREPORT</b>\n\n"

                # Sortiere nach Performance
                sorted_reports = sorted(cycle_reports, key=lambda x: x["pnl_pct"], reverse=True)

                for report in sorted_reports:
                    emoji = "🏆" if report == sorted_reports[0] else "📊"
                    pnl_emoji = "📈" if report["pnl_pct"] > 0 else "📉"

                    message += f"""
{emoji} <b>{report["cohort"].upper()}</b> (Zyklus {report["cycle"]})
{pnl_emoji} P&L: {report["pnl_pct"]:+.2f}%
📊 Sharpe: {report["sharpe"]:.2f}
🔄 Trades: {report["trades"]}
"""

                # Winner
                if len(sorted_reports) > 1:
                    winner = sorted_reports[0]
                    message += f"\n🏆 <b>Winner:</b> {winner['cohort'].upper()} mit {winner['pnl_pct']:+.2f}%"

                telegram.send(message)

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Cycle Management Error: {e}")
        trading_logger.error("Cycle management failed", e, {"task": "cycle_management"})


def task_ab_test_check():
    """
    Prüft laufende A/B Tests auf statistische Signifikanz.
    Läuft täglich um 23:00.
    """
    logger.info("Checking A/B tests...")

    try:
        from src.optimization.ab_testing import ABTestingFramework

        framework = ABTestingFramework.get_instance()

        # Hole alle laufenden Experimente
        summaries = framework.get_all_experiments_summary()
        running = [s for s in summaries if s.get("status") == "RUNNING"]

        for exp in running:
            exp_id = exp["id"]

            # Prüfe auf frühes Stoppen
            should_stop, reason = framework.check_early_stopping(exp_id)

            if should_stop:
                # Beende Experiment
                result = framework.complete_experiment(exp_id, promote_winner=True)

                if result:
                    telegram.send(f"""
🧪 <b>A/B TEST ABGESCHLOSSEN</b>

<b>{exp["name"]}</b>
Grund: {reason}

<b>Ergebnis:</b>
🏆 Winner: {result.winner}
📊 p-Wert: {result.p_value:.4f}
📈 Verbesserung: {result.winner_improvement:+.1f}%
🎯 Signifikanz: {result.significance.value}
""")
            else:
                # Log Status
                logger.info(f"A/B Test '{exp['name']}': {reason}")

    except Exception as e:
        logger.error(f"A/B Test Check Error: {e}")
        trading_logger.error("A/B test check failed", e, {"task": "ab_test_check"})


def task_divergence_scan():
    """
    Scannt nach Divergenzen in wichtigen Symbolen.
    Läuft alle 2 Stunden.
    """
    logger.info("Scanning for divergences...")

    try:
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector.get_instance()

        # Wichtige Symbole
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in symbols:
            analysis = detector.analyze(symbol, timeframe="1h")

            if analysis.divergence_count > 0 and analysis.average_confidence > 0.6:
                logger.info(
                    f"Divergence found in {symbol}: "
                    f"{analysis.dominant_type.value}, "
                    f"confidence={analysis.average_confidence:.2f}"
                )

                # Alert bei starkem Signal
                if abs(analysis.net_signal) > 0.5:
                    direction = "🟢 BULLISH" if analysis.net_signal > 0 else "🔴 BEARISH"

                    div_list = "\n".join(
                        [
                            f"• {d.indicator}: {d.divergence_type.value}"
                            for d in analysis.divergences[:3]
                        ]
                    )

                    telegram.send(f"""
📊 <b>DIVERGENCE ALERT</b>

<b>{symbol}</b>
{direction} Signal: {analysis.net_signal:.2f}

<b>Divergenzen:</b>
{div_list}

Confidence: {analysis.average_confidence:.1%}
""")

    except Exception as e:
        logger.error(f"Divergence Scan Error: {e}")
        trading_logger.error("Divergence scan failed", e, {"task": "divergence_scan"})


# ═══════════════════════════════════════════════════════════════
# PHASE 6 - MULTI-COIN TASKS
# ═══════════════════════════════════════════════════════════════


def task_update_watchlist():
    """
    Aktualisiert Marktdaten für alle Coins in der Watchlist.
    Läuft alle 30 Minuten.

    Updates:
    - Aktuelle Preise
    - 24h Volumen
    - Deaktiviert Coins mit zu wenig Liquidität
    """
    logger.info("Updating watchlist market data...")

    try:
        from src.data.watchlist import get_watchlist_manager

        manager = get_watchlist_manager()

        # Marktdaten aktualisieren
        updated = manager.update_market_data()

        # Liquiditätsprüfung
        deactivated = manager.check_liquidity()

        if deactivated:
            telegram.send(f"""
⚠️ <b>WATCHLIST UPDATE</b>

{len(deactivated)} Coins wegen niedriger Liquidität deaktiviert:
{", ".join(deactivated[:5])}{"..." if len(deactivated) > 5 else ""}
""")

        logger.info(f"Watchlist: {updated} coins updated, {len(deactivated)} deactivated")

    except Exception as e:
        logger.error(f"Watchlist Update Error: {e}")
        trading_logger.error("Watchlist update failed", e, {"task": "update_watchlist"})


@task_locked
def task_scan_opportunities():
    """
    Scannt Watchlist nach Trading-Opportunities.
    Läuft alle 2 Stunden.

    Analysiert:
    - Technische Indikatoren (RSI, MACD, Bollinger)
    - Volume Anomalien
    - Sentiment-Shifts
    - Whale-Aktivität
    - Momentum
    """
    logger.info("Scanning for trading opportunities...")

    try:
        from src.scanner import OpportunityDirection, get_coin_scanner

        scanner = get_coin_scanner()
        opportunities = scanner.scan_opportunities(force_refresh=True)

        if not opportunities:
            logger.info("No opportunities found")
            return

        # Stats loggen
        stats = scanner.get_scan_stats()
        logger.info(
            f"Opportunities: {stats['total_opportunities']} found, "
            f"avg score={stats.get('average_score', 0):.2f}"
        )

        # Top 3 Opportunities für Alert
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

            telegram.send(message)

        # Store top opportunities für Cohorts
        conn = get_db_connection()
        if conn:
            try:
                # Cohort Manager benachrichtigen
                from src.core.cohort_manager import CohortManager

                cohort_manager = CohortManager.get_instance()

                # Top 5 an alle aktiven Cohorts verteilen
                top_5 = scanner.get_top_opportunities(5)
                for opp in top_5:
                    cohort_manager.evaluate_opportunity(opp)

            except Exception as e:
                logger.debug(f"Cohort evaluation skipped: {e}")
            finally:
                conn.close()

    except Exception as e:
        logger.error(f"Opportunity Scan Error: {e}")
        trading_logger.error("Opportunity scan failed", e, {"task": "scan_opportunities"})


@task_locked
def task_portfolio_rebalance():
    """
    Prüft Portfolio-Allocation und schlägt Rebalancing vor.
    Läuft täglich um 06:00.

    Aktionen:
    - Vergleicht aktuelle vs. Ziel-Allocation
    - Identifiziert Abweichungen > 5%
    - Generiert Rebalancing-Vorschläge
    """
    logger.info("Checking portfolio allocation...")

    try:
        from src.portfolio import get_portfolio_allocator
        from src.scanner import get_coin_scanner

        allocator = get_portfolio_allocator()
        scanner = get_coin_scanner()

        # Hole aktuelle Positionen
        conn = get_db_connection()
        if not conn:
            return

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name FROM cohorts WHERE is_active = TRUE")
                cohorts = cur.fetchall()

            for cohort in cohorts:
                cohort_id = str(cohort["id"])
                cohort_name = cohort["name"]

                # Hole aktuelle Positionen und Stats
                stats = allocator.get_portfolio_stats(cohort_id)

                if stats["position_count"] == 0:
                    # Keine Positionen - neue Allocation berechnen
                    opportunities = scanner.get_top_opportunities(5)

                    # Berechne optimale Allocation (mit $1000 Default)
                    result = allocator.calculate_allocation(
                        opportunities=opportunities,
                        available_capital=1000.0,
                        cohort_id=cohort_id,
                    )

                    if result.allocations:
                        alloc_str = "\n".join(
                            [f"• {s}: ${a:.2f}" for s, a in list(result.allocations.items())[:5]]
                        )

                        telegram.send(f"""
📊 <b>NEUE ALLOCATION für {cohort_name.upper()}</b>

{alloc_str}

Total: ${result.total_allocated:.2f}
Cash: ${result.cash_remaining:.2f}
""")

                else:
                    # Prüfe auf Rebalancing-Bedarf
                    logger.info(
                        f"Portfolio {cohort_name}: "
                        f"{stats['position_count']} positions, "
                        f"${stats['total_value']:.2f}"
                    )

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Portfolio Rebalance Error: {e}")
        trading_logger.error("Portfolio rebalance failed", e, {"task": "portfolio_rebalance"})


def task_coin_performance_update():
    """
    Aktualisiert Performance-Metriken pro Coin.
    Läuft täglich um 21:30 (nach Daily Summary).

    Tracked:
    - Win Rate pro Coin
    - Durchschnittlicher Return
    - Optimale Grid-Range
    - Beste Signal-Kombinationen
    """
    logger.info("Updating coin performance metrics...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        from psycopg2.extras import RealDictCursor

        from src.data.watchlist import get_watchlist_manager

        manager = get_watchlist_manager()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Berechne Performance pro Coin für die letzte Woche
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

                # Update Watchlist
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

            # Store in coin_performance table
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
        trading_logger.error(
            "Coin performance update failed", e, {"task": "coin_performance_update"}
        )

    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# PHASE 6 - HYBRID ORCHESTRATOR TASKS
# ═══════════════════════════════════════════════════════════════


@task_locked
def task_mode_evaluation():
    """
    Evaluates current market regime and logs mode recommendation.
    Runs every hour.

    Reads the latest regime from DB, evaluates against hysteresis
    rules, and stores the recommendation in trading_mode_history.
    """
    logger.info("Running mode evaluation...")

    try:
        from src.analysis.regime_detection import RegimeDetector

        detector = RegimeDetector.get_instance()
        regime_state = detector.detect_regime("BTCUSDT")

        if not regime_state:
            logger.warning("Mode evaluation: no regime data, skipping")
            return

        # Evaluate mode recommendation
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
        trading_logger.error("Mode evaluation failed", e, {"task": "mode_evaluation"})


@task_locked
def task_hybrid_rebalance():
    """
    Checks portfolio allocation drift for the hybrid system.
    Runs every 6 hours.

    Reads current positions and compares against target allocations.
    Logs recommendations to DB and notifies via Telegram.
    """
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

        # Check each symbol's drift
        drift_report = []
        for symbol, sdata in symbols.items():
            allocation = sdata.get("allocation_usd", 0)
            if allocation <= 0:
                continue

            # Get current price for value estimation
            try:
                price = market_data.get_price(symbol)
                if not price or price <= 0:
                    continue

                # Estimate current value
                hold_qty = sdata.get("hold_quantity", 0)
                current_value = hold_qty * price if hold_qty > 0 else allocation

                drift_pct = abs(current_value - allocation) / allocation * 100
                if drift_pct > 5.0:  # Same threshold as REBALANCE_DRIFT_PCT
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
        trading_logger.error("Hybrid rebalance failed", e, {"task": "hybrid_rebalance"})


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

    # Weekly Export Samstag 23:00 (vor Sonntags-Analyse)
    schedule.every().saturday.at("23:00").do(task_weekly_export)

    # System Health Check alle 6 Stunden
    schedule.every(6).hours.do(task_system_health_check)

    # ═══════════════════════════════════════════════════════════════
    # NEW JOBS - PHASE 2-5 ADDITIONS
    # ═══════════════════════════════════════════════════════════════

    # ETF Flow Daten täglich um 10:00 (nach US-Marktschluss)
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
    # PHASE 6 - MULTI-COIN JOBS
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
