#!/usr/bin/env python3
"""
Interactive Telegram Bot Handler
Verarbeitet Befehle und zeigt Inline-Buttons für Aktionen

Features:
- /status - Portfolio Status
- /ask <frage> - AI Frage
- /market - Markt-Analyse
- /stops - Aktive Stop-Loss
- Inline Buttons für Trade-Bestätigung
"""

import logging
import os
import sys
from datetime import datetime

# Telegram Bot API
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add parent to path
sys.path.insert(0, "/app")

from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")


class TradingTelegramBot:
    """Interactive Telegram Bot für Trading"""

    def __init__(self):
        self.pending_trades = {}  # Trade-Vorschläge die auf Bestätigung warten

    # ═══════════════════════════════════════════════════════════════
    # COMMAND HANDLERS
    # ═══════════════════════════════════════════════════════════════

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start Befehl"""
        await update.message.reply_text(
            "🤖 *Trading Bot aktiv!*\n\n"
            "*Befehle:*\n"
            "/status - Portfolio Status\n"
            "/report - Cohort-Zwischenbericht\n"
            "/compare - Cohort-Vergleich\n"
            "/market - Markt-Analyse\n"
            "/ask <frage> - AI Frage\n"
            "/stops - Aktive Stop-Loss\n"
            "/ta <symbol> - Technische Analyse\n"
            "/help - Alle Befehle\n",
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hilfe Befehl"""
        help_text = """
🤖 *TRADING BOT BEFEHLE*

*Portfolio:*
/status - Aktueller Portfolio-Status
/portfolio - 3-Tier Portfolio Breakdown
/report - Cohort-Zwischenbericht (live)
/compare - Cohort-Vergleichsranking
/positions - Offene Positionen
/performance - Performance-Übersicht
/stops - Aktive Stop-Loss Orders

*Analyse:*
/market - Markt-Übersicht + Sentiment
/ta <symbol> - Technische Analyse
/whale - Letzte Whale Alerts
/macro - Anstehende Events

*AI Assistant:*
/ask <frage> - Stelle eine Frage
/explain <konzept> - Erkläre ein Konzept
/analyze <symbol> - AI Coin-Analyse

*Trading:*
/buy <symbol> <betrag> - Kaufvorschlag
/sell <symbol> - Verkaufsvorschlag
/rebalance - Rebalancing starten
/validate - Production Readiness Check

*Playbook (Erfahrungsgedächtnis):*
/playbook - Zeige aktuelle Regeln
/playbook_update - Manuelles Update auslösen
/playbook_stats - Playbook Statistiken

*Einstellungen:*
/alerts on|off - Benachrichtigungen
/risk low|medium|high - Risiko-Level
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Portfolio Status"""
        # TODO: Echte Daten aus DB holen
        status = """
📊 *PORTFOLIO STATUS*

💰 *Wert:* `$12.45`
📈 *Heute:* `+$0.23 (+1.88%)`
📊 *Gesamt:* `+$2.45 (+24.5%)`

*Positionen:*
├ SOL: `$4.50` (36%)
├ ETH: `$3.20` (26%)
├ ARB: `$2.75` (22%)
└ Cash: `$2.00` (16%)

*Risiko:*
├ Max Drawdown: `-5.2%`
├ Aktive Stops: `3`
└ Nächstes Rebalancing: `2d 4h`

⏰ {time}
""".format(time=datetime.now().strftime("%Y-%m-%d %H:%M"))

        # Inline Buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 Details", callback_data="details"),
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status"),
            ],
            [
                InlineKeyboardButton("📈 Performance", callback_data="performance"),
                InlineKeyboardButton("⚙️ Einstellungen", callback_data="settings"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(status, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Markt-Übersicht"""
        # TODO: Echte Daten
        market = """
🌍 *MARKT-ÜBERSICHT*

*Fear & Greed:* 45 (Neutral) 😐

*Bitcoin:* `$97,234` (+1.2%)
*Ethereum:* `$3,456` (+0.8%)
*Gesamt MC:* `$3.2T`

*Trending:*
🔥 SOL, ARB, OP, INJ

*Whale Activity:*
├ BTC: 🟢 Akkumulation
├ ETH: ⚪ Neutral
└ SOL: 🟢 Akkumulation

*Macro:*
⚠️ FOMC Meeting in 3 Tagen
"""

        keyboard = [
            [
                InlineKeyboardButton("🧠 AI Analyse", callback_data="ai_market"),
                InlineKeyboardButton("🐋 Whale Details", callback_data="whale_details"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(market, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI Frage"""
        if not context.args:
            await update.message.reply_text("Usage: /ask <deine Frage>")
            return

        question = " ".join(context.args)

        # Zeige "typing" während AI antwortet
        await update.message.chat.send_action("typing")

        # DeepSeek API Call
        import requests

        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Du bist ein Trading-Assistent. Antworte präzise auf Deutsch.",
                        },
                        {"role": "user", "content": question},
                    ],
                    "max_tokens": 500,
                },
                timeout=30,
            )

            if response.status_code == 200:
                answer = response.json()["choices"][0]["message"]["content"]
                await update.message.reply_text(
                    f"🧠 *AI Antwort:*\n\n{answer}", parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ API Fehler")

        except Exception as e:
            await update.message.reply_text(f"❌ Fehler: {e!s}")

    async def cmd_stops(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Zeige aktive Stop-Loss Orders"""
        stops = """
🛑 *AKTIVE STOP-LOSS*

1️⃣ *SOL*
   Entry: `$142.50`
   Stop: `$135.38` (-5%)
   Type: Trailing

2️⃣ *ETH*
   Entry: `$3,400`
   Stop: `$3,230` (-5%)
   Type: Fixed

3️⃣ *ARB*
   Entry: `$1.25`
   Stop: `$1.19` (-5%)
   Type: ATR-based
"""

        keyboard = [
            [
                InlineKeyboardButton("➕ Neuer Stop", callback_data="new_stop"),
                InlineKeyboardButton("✏️ Bearbeiten", callback_data="edit_stops"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(stops, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_ta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Technische Analyse"""
        if not context.args:
            await update.message.reply_text("Usage: /ta <symbol>\nBeispiel: /ta SOL")
            return

        symbol = context.args[0].upper()

        # TODO: Echte TA Daten
        ta = f"""
📊 *TECHNISCHE ANALYSE - {symbol}*

*Preis:* `$142.50`

*Indikatoren:*
├ RSI(14): `45.2` ⚪ Neutral
├ MACD: `0.25` 🟢 Bullish
├ SMA20: `$140.00`
├ SMA50: `$135.00`
└ ATR: `$5.20` (Medium)

*Signale:*
├ Trend: 🟢 UP
├ Momentum: ⚪ NEUTRAL
└ Overall: 🟢 *BUY*

*Confidence:* 65%

_RSI neutral, MACD bullish crossover, Preis über SMAs_
"""

        keyboard = [
            [
                InlineKeyboardButton("📈 Chart", callback_data=f"chart_{symbol}"),
                InlineKeyboardButton("🛒 Buy", callback_data=f"buy_{symbol}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(ta, parse_mode="Markdown", reply_markup=reply_markup)

    # ═══════════════════════════════════════════════════════════════
    # PORTFOLIO TIER COMMANDS (3-Tier System)
    # ═══════════════════════════════════════════════════════════════

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show 3-Tier portfolio breakdown."""
        await update.message.reply_text("Loading portfolio tiers...")

        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            database_url = os.getenv("DATABASE_URL")
            if database_url:
                conn = psycopg2.connect(database_url)
            else:
                conn = psycopg2.connect(
                    host=os.getenv("POSTGRES_HOST", "localhost"),
                    port=os.getenv("POSTGRES_PORT", 5432),
                    database=os.getenv("POSTGRES_DB", "trading_bot"),
                    user=os.getenv("POSTGRES_USER", "trading"),
                    password=os.getenv("POSTGRES_PASSWORD", ""),
                )

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT tier_name, target_pct, current_pct, current_value_usd "
                    "FROM portfolio_tiers WHERE is_active = TRUE "
                    "ORDER BY tier_name"
                )
                tiers = cur.fetchall()

            conn.close()

            if not tiers:
                await update.message.reply_text(
                    "No portfolio tier data found.\nIs PORTFOLIO_MANAGER=true?"
                )
                return

            total_value = sum(float(t["current_value_usd"] or 0) for t in tiers)

            tier_emojis = {
                "cash_reserve": "💵",
                "index_holdings": "📊",
                "trading": "⚡",
            }

            lines = [
                "<b>🏦 3-TIER PORTFOLIO</b>",
                "━━━━━━━━━━━━━━━━━━━━━",
            ]

            for t in tiers:
                name = t["tier_name"]
                emoji = tier_emojis.get(name, "📋")
                target = float(t["target_pct"])
                current = float(t["current_pct"] or 0)
                value = float(t["current_value_usd"] or 0)
                drift = current - target

                bar_len = int(current / 5)  # 20 chars = 100%
                bar = "█" * bar_len + "░" * (20 - bar_len)

                lines.append(f"\n{emoji} <b>{name.upper()}</b>")
                lines.append(f"<code>{bar} {current:5.1f}%</code>")
                lines.append(
                    f"  Target: {target:.0f}% | Value: ${value:,.0f} | Drift: {drift:+.1f}pp"
                )

            lines.append(f"\n<b>Total: ${total_value:,.2f}</b>")

            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PLAYBOOK COMMANDS (Erfahrungsgedächtnis)
    # ═══════════════════════════════════════════════════════════════

    async def cmd_playbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Zeigt das aktuelle Trading Playbook"""
        try:
            from src.data.playbook import get_playbook

            playbook = get_playbook()

            # Kürze auf wichtigste Teile für Telegram
            content = playbook.playbook_content

            # Extrahiere Header und wichtigste Regeln
            lines = content.split("\n")
            summary_lines = []
            in_section = False
            sections_found = 0

            for line in lines:
                if line.startswith("# "):
                    summary_lines.append(f"*{line[2:]}*")
                elif (
                    line.startswith("Version:")
                    or line.startswith("Basiert auf:")
                    or line.startswith("Gesamterfolgsrate:")
                ):
                    summary_lines.append(f"`{line}`")
                elif "WAS NICHT FUNKTIONIERT" in line:
                    summary_lines.append("\n*❌ Anti-Patterns:*")
                    in_section = True
                    sections_found += 1
                elif "WAS GUT FUNKTIONIERT" in line:
                    summary_lines.append("\n*✅ Erfolgs-Patterns:*")
                    in_section = True
                    sections_found += 1
                elif line.startswith("## ") and in_section:
                    in_section = False
                elif (
                    in_section
                    and line.strip()
                    and not line.startswith("---")
                    and len(summary_lines) < 40
                ):
                    summary_lines.append(line)

                if sections_found >= 2 and not in_section:
                    break

            message = "\n".join(summary_lines[:40])
            message += "\n\n_Nutze /playbook\\_stats für Details_"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Fehler: {e}")

    async def cmd_playbook_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Zeigt Playbook-Statistiken"""
        try:
            from src.data.playbook import get_playbook

            playbook = get_playbook()

            stats = f"""📚 *PLAYBOOK STATISTIKEN*

*Version:* {playbook.current_version}
*Pfad:* `{playbook.PLAYBOOK_PATH}`

*Inhalt:*
• Zeilen: {len(playbook.playbook_content.split(chr(10)))}
• Zeichen: {len(playbook.playbook_content)}

*Nächstes Update:* Sonntag 19:00

_Das Playbook wird bei jedem AI-Call als Kontext verwendet._
"""

            keyboard = [[InlineKeyboardButton("🔄 Update jetzt", callback_data="playbook_update")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(stats, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            await update.message.reply_text(f"❌ Fehler: {e}")

    async def cmd_playbook_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Löst manuelles Playbook-Update aus"""
        await update.message.reply_text("🔄 Starte Playbook-Analyse...")

        try:
            import psycopg2

            database_url = os.getenv("DATABASE_URL")
            if database_url:
                conn = psycopg2.connect(database_url)
            else:
                conn = psycopg2.connect(
                    host=os.getenv("POSTGRES_HOST", "localhost"),
                    port=os.getenv("POSTGRES_PORT", 5432),
                    database=os.getenv("POSTGRES_DB", "trading_bot"),
                    user=os.getenv("POSTGRES_USER", "trading"),
                    password=os.getenv("POSTGRES_PASSWORD", ""),
                )

            from src.data.playbook import TradingPlaybook

            playbook = TradingPlaybook(db_connection=conn)
            result = playbook.analyze_and_update()
            conn.close()

            if "error" in result:
                await update.message.reply_text(f"❌ Fehler: {result['error']}")
            else:
                metrics = result.get("metrics", {})
                message = f"""✅ *PLAYBOOK AKTUALISIERT*

*Version:* {result.get("version", 0)}
*Trades analysiert:* {metrics.get("total_trades", 0)}
*Erfolgsrate:* {metrics.get("success_rate", 0):.1f}%

*Änderungen:*
"""
                for change in result.get("changes", [])[:5]:
                    message += f"• {change}\n"

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTION VALIDATION COMMANDS
    # ═══════════════════════════════════════════════════════════════

    async def cmd_validate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run production readiness validation."""
        await update.message.reply_text("Running production validation...")

        try:
            from src.portfolio.validation import ProductionValidator

            validator = ProductionValidator()
            report = validator.validate_detailed()

            lines = [
                "<b>🔍 PRODUCTION VALIDATION</b>",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"Status: <b>{'✅ READY' if report.is_ready else '⏳ NOT READY'}</b>",
                f"Progress: <b>{report.passed_count}/{report.total_count}</b> "
                f"({report.progress_pct:.0f}%)\n",
            ]

            for r in report.results:
                icon = "✅" if r.passed else "❌"
                lines.append(f"{icon} {r.message}")

            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ═══════════════════════════════════════════════════════════════
    # REPORT COMMAND (Cohort-Zwischenbericht)
    # ═══════════════════════════════════════════════════════════════

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generiert Cohort-Zwischenbericht on-demand."""
        await update.message.reply_text("📊 Generiere Cohort-Bericht...")

        try:
            from src.tasks.reporting_tasks import _build_cohort_status

            report = _build_cohort_status()

            if not report:
                await update.message.reply_text(
                    "⚠️ Keine Cohort-Daten gefunden.\nSind State-Files vorhanden?"
                )
                return

            await update.message.reply_text(report, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Report error: {e}")
            await update.message.reply_text(f"❌ Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # COMPARE COMMAND (Cohort-Vergleich)
    # ═══════════════════════════════════════════════════════════════

    async def cmd_compare(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generiert Cohort-Vergleichsranking on-demand."""
        await update.message.reply_text("🏆 Generiere Cohort-Vergleich...")

        try:
            from src.tasks.reporting_tasks import _build_cohort_comparison

            report = _build_cohort_comparison()

            if not report:
                await update.message.reply_text(
                    "⚠️ Keine Vergleichsdaten.\nMind. 2 aktive Cohorts mit Trades benötigt."
                )
                return

            await update.message.reply_text(report, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Compare error: {e}")
            await update.message.reply_text(f"❌ Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # CALLBACK HANDLERS (Button Clicks)
    # ═══════════════════════════════════════════════════════════════

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Verarbeitet Button-Klicks"""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data == "refresh_status":
            await query.edit_message_text("🔄 Status wird aktualisiert...")
            # TODO: Aktualisiere Status
            await self.cmd_status(update, context)

        elif data == "ai_market":
            await query.edit_message_text("🧠 AI analysiert Markt...")
            # TODO: AI Markt-Analyse

        elif data.startswith("buy_"):
            symbol = data.replace("buy_", "")
            await self.show_buy_confirmation(query, symbol)

        elif data.startswith("confirm_buy_"):
            symbol = data.replace("confirm_buy_", "")
            await query.edit_message_text(f"✅ Kauforder für {symbol} wird ausgeführt...")
            # TODO: Echte Order ausführen

        elif data.startswith("cancel_"):
            await query.edit_message_text("❌ Abgebrochen")

        elif data == "playbook_update":
            await query.edit_message_text("🔄 Playbook wird aktualisiert...")
            # Rufe cmd_playbook_update auf
            await self.cmd_playbook_update(update, context)

        elif data == "details":
            await query.edit_message_text("📊 Details werden geladen...")

        elif data == "settings":
            await self.show_settings(query)

    async def show_buy_confirmation(self, query, symbol: str):
        """Zeigt Kaufbestätigung mit Buttons"""
        message = f"""
🛒 *KAUFEN: {symbol}*

Möchtest du wirklich kaufen?

*Details:*
├ Preis: `$142.50`
├ Menge: `0.035`
├ Wert: `$5.00`
└ Stop-Loss: `$135.38` (-5%)

*AI Einschätzung:*
_Gutes Entry-Timing, RSI neutral, Trend bullish_
"""

        keyboard = [
            [
                InlineKeyboardButton("✅ Bestätigen", callback_data=f"confirm_buy_{symbol}"),
                InlineKeyboardButton("❌ Abbrechen", callback_data="cancel_buy"),
            ],
            [InlineKeyboardButton("📊 Mehr Details", callback_data=f"details_{symbol}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    async def show_settings(self, query):
        """Zeigt Einstellungen"""
        message = """
⚙️ *EINSTELLUNGEN*

*Benachrichtigungen:*
├ Trade Alerts: ✅ An
├ Daily Summary: ✅ An
├ Whale Alerts: ✅ An
└ Macro Events: ✅ An

*Risiko:*
├ Level: Medium
├ Max Drawdown: 10%
└ Stop-Loss: Auto

*AI:*
└ DeepSeek: ✅ Aktiv
"""

        keyboard = [
            [
                InlineKeyboardButton("🔔 Alerts", callback_data="settings_alerts"),
                InlineKeyboardButton("⚠️ Risiko", callback_data="settings_risk"),
            ],
            [InlineKeyboardButton("🔙 Zurück", callback_data="back_status")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    # ═══════════════════════════════════════════════════════════════
    # MESSAGE HANDLER
    # ═══════════════════════════════════════════════════════════════

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Verarbeitet normale Nachrichten (ohne Befehl)"""
        text = update.message.text

        # Wenn es eine Frage ist, an AI weiterleiten
        if "?" in text:
            context.args = text.split()
            await self.cmd_ask(update, context)
        else:
            await update.message.reply_text(
                "Ich verstehe nur Befehle. Nutze /help für eine Übersicht."
            )


def main():
    """Startet den Bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN nicht gesetzt!")
        return

    # Bot Instance
    bot = TradingTelegramBot()

    # Application erstellen
    app = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("status", bot.cmd_status))
    app.add_handler(CommandHandler("market", bot.cmd_market))
    app.add_handler(CommandHandler("ask", bot.cmd_ask))
    app.add_handler(CommandHandler("stops", bot.cmd_stops))
    app.add_handler(CommandHandler("ta", bot.cmd_ta))

    # Report + Compare Commands
    app.add_handler(CommandHandler("report", bot.cmd_report))
    app.add_handler(CommandHandler("compare", bot.cmd_compare))

    # Portfolio Tier Commands
    app.add_handler(CommandHandler("portfolio", bot.cmd_portfolio))

    # Validation Commands
    app.add_handler(CommandHandler("validate", bot.cmd_validate))

    # Playbook Commands
    app.add_handler(CommandHandler("playbook", bot.cmd_playbook))
    app.add_handler(CommandHandler("playbook_stats", bot.cmd_playbook_stats))
    app.add_handler(CommandHandler("playbook_update", bot.cmd_playbook_update))

    # Callback Handler (Buttons)
    app.add_handler(CallbackQueryHandler(bot.button_callback))

    # Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Start
    logger.info("Starting Telegram Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
