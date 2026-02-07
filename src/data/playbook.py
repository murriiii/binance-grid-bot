"""
Trading Playbook System
=======================
Ein sich selbst aktualisierendes "Erfahrungsgedächtnis" für den Trading Bot.

Konzept:
- Markdown-Dokument mit gelernten Regeln und Patterns
- Wird automatisch aus Trade-Historie generiert
- Wird bei jedem DeepSeek API-Call als Kontext mitgesendet
- Aktualisiert sich wöchentlich basierend auf neuen Erkenntnissen

Das ist KEIN Fine-Tuning, sondern strukturiertes In-Context Learning.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("trading_bot")

# PostgreSQL
try:
    import psycopg2  # noqa: F401
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    RealDictCursor = None  # type: ignore


@dataclass
class PlaybookVersion:
    """Eine Version des Playbooks"""

    version: int
    content: str
    generated_at: datetime
    trade_count: int
    success_rate: float
    changes_summary: str


class TradingPlaybook:
    """
    Verwaltet das Trading Playbook - ein lernendes Erfahrungsdokument.

    Features:
    1. Generiert Playbook aus Trade-Historie
    2. Trackt was funktioniert hat und was nicht
    3. Aktualisiert sich automatisch
    4. Wird in DeepSeek Prompts eingebunden
    """

    # Pfad zum Playbook
    PLAYBOOK_PATH = Path("config/TRADING_PLAYBOOK.md")
    PLAYBOOK_HISTORY_PATH = Path("config/playbook_history/")

    # Minimum Trades für statistische Relevanz
    MIN_TRADES_FOR_PATTERN = 5
    MIN_TRADES_FOR_RULE = 10

    def __init__(self, db_connection=None):
        self.conn = db_connection
        self.playbook_content = ""
        self.current_version = 0

        # Erstelle Verzeichnisse
        self.PLAYBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.PLAYBOOK_HISTORY_PATH.mkdir(parents=True, exist_ok=True)

        # Lade existierendes Playbook oder erstelle neues
        self._load_or_create_playbook()

        # Erstelle DB-Tabelle für Playbook-Versionen
        if self.conn:
            self._create_tables()

    def _create_tables(self):
        """Erstellt Playbook-Tabellen in der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS playbook_versions (
                        id SERIAL PRIMARY KEY,
                        version INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        generated_at TIMESTAMPTZ DEFAULT NOW(),
                        trade_count INTEGER,
                        success_rate DECIMAL(5, 2),
                        changes_summary TEXT,
                        metrics JSONB
                    );

                    CREATE INDEX IF NOT EXISTS idx_playbook_version
                        ON playbook_versions(version);
                """)
                self.conn.commit()
        except Exception as e:
            logger.error(f"Playbook Tabellen-Fehler: {e}")

    def _load_or_create_playbook(self):
        """Lädt existierendes Playbook oder erstellt ein neues"""
        if self.PLAYBOOK_PATH.exists():
            self.playbook_content = self.PLAYBOOK_PATH.read_text(encoding="utf-8")
            # Extrahiere Version aus Header
            for line in self.playbook_content.split("\n"):
                if line.startswith("Version:"):
                    try:
                        self.current_version = int(line.split(":")[1].strip())
                    except (ValueError, IndexError):
                        self.current_version = 1
                    break
            logger.info(f"Playbook v{self.current_version} geladen")
        else:
            self._create_initial_playbook()

    def _create_initial_playbook(self):
        """Erstellt das initiale Playbook-Template"""
        self.current_version = 1
        self.playbook_content = self._generate_initial_template()
        self._save_playbook()
        logger.info("Initiales Playbook erstellt")

    def _generate_initial_template(self) -> str:
        """Generiert das initiale Playbook-Template"""
        return f"""# 🎯 TRADING PLAYBOOK

Version: {self.current_version}
Letzte Aktualisierung: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Basiert auf: 0 Trades

---

## 📊 MARKT-REGIME REGELN

### Fear & Greed Index Strategien

| F&G Range | Empfohlene Aktion | Konfidenz | Basiert auf |
|-----------|-------------------|-----------|-------------|
| 0-20 (Extreme Fear) | STRONG BUY | Hoch | Historische Daten zeigen Erholung |
| 20-40 (Fear) | BUY | Mittel | Noch keine Daten |
| 40-60 (Neutral) | HOLD | Niedrig | Abwarten |
| 60-80 (Greed) | REDUCE | Mittel | Noch keine Daten |
| 80-100 (Extreme Greed) | SELL | Hoch | Überkauft-Signale |

> ⚠️ Diese Regeln werden automatisch angepasst basierend auf echten Trade-Ergebnissen.

---

## 🐋 WHALE ALERT INTERPRETATION

### Bekannte Muster
- **Exchange Inflow (Bearish)**: Große Mengen zu Exchange = potentieller Verkaufsdruck
- **Exchange Outflow (Bullish)**: Abhebungen = langfristiges Halten

### Gelernte Schwellenwerte
- BTC: Signifikant ab 500 BTC
- ETH: Signifikant ab 5,000 ETH

> 📈 Noch keine ausreichenden Daten für spezifische Regeln.

---

## 📅 ECONOMIC EVENTS

### High-Impact Events
| Event | Typische BTC Reaktion | Empfehlung |
|-------|----------------------|------------|
| FOMC | ±3-5% | Positionen reduzieren vorher |
| CPI | ±2-3% | Abwarten |
| NFP | ±1-2% | Geringer Impact |

### Gelernte Event-Reaktionen
> 🔄 Wird nach ersten Events aktualisiert.

---

## 📈 TECHNISCHE ANALYSE REGELN

### RSI Strategien
- **RSI < 30**: Überverkauft → Potentieller Einstieg
- **RSI > 70**: Überkauft → Potentieller Ausstieg
- **RSI Divergenz**: Starkes Signal wenn Preis und RSI divergieren

### MACD Signale
- **MACD Cross Up**: Bullish
- **MACD Cross Down**: Bearish
- **Histogram Divergenz**: Trendwende möglich

> 📊 Erfolgsraten werden nach ausreichend Trades berechnet.

---

## ❌ WAS NICHT FUNKTIONIERT HAT

### Anti-Patterns (zu vermeiden)
> 🔄 Wird automatisch gefüllt wenn Trades mit negativem Outcome erkannt werden.

---

## ✅ WAS GUT FUNKTIONIERT HAT

### Erfolgreiche Strategien
> 🔄 Wird automatisch gefüllt basierend auf Trade-Performance.

---

## 🎛️ AKTUELLE PARAMETER

### Position Sizing
- **Standard Position**: 20 USDT pro Grid-Level
- **Max Drawdown Limit**: 10%
- **Stop-Loss**: 5% trailing

### Confidence Thresholds
- **Minimum für Trade**: 0.5
- **Für größere Position**: 0.7
- **Für YOLO**: 0.9 (nicht empfohlen)

---

## 📝 NOTIZEN & BEOBACHTUNGEN

### Manuelle Einträge
- *Hier können manuelle Beobachtungen eingetragen werden*

### System-generierte Insights
> 🔄 Wird automatisch aktualisiert.

---

## 📚 VERSIONS-HISTORIE

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1 | {datetime.now().strftime("%Y-%m-%d")} | Initiale Version |

---

*Dieses Dokument wird automatisch aktualisiert basierend auf Trading-Ergebnissen.*
*Letzte Analyse: Noch keine Trades vorhanden.*
"""

    def _save_playbook(self):
        """Speichert das Playbook"""
        self.PLAYBOOK_PATH.write_text(self.playbook_content, encoding="utf-8")

        # Speichere auch historische Version
        history_file = self.PLAYBOOK_HISTORY_PATH / f"playbook_v{self.current_version}.md"
        history_file.write_text(self.playbook_content, encoding="utf-8")

    def get_playbook_for_prompt(self) -> str:
        """
        Gibt das Playbook im Format für DeepSeek Prompts zurück.
        Gekürzt auf die wichtigsten Regeln.
        """
        # Extrahiere die wichtigsten Abschnitte
        sections_to_include = [
            "## 📊 MARKT-REGIME REGELN",
            "## 🎯 SIGNAL ACCURACY",
            "## ❌ WAS NICHT FUNKTIONIERT HAT",
            "## ✅ WAS GUT FUNKTIONIERT HAT",
            "## 🎛️ AKTUELLE PARAMETER",
        ]

        prompt_content = "=== MEIN TRADING PLAYBOOK (Gelerntes Wissen) ===\n\n"

        lines = self.playbook_content.split("\n")
        include_section = False
        current_section = ""

        for line in lines:
            # Check if this is a section header we want
            if any(section in line for section in sections_to_include):
                include_section = True
                current_section = line
                prompt_content += f"\n{line}\n"
            # Check if this is a different section header (stop including)
            elif line.startswith("## ") and include_section:
                if not any(section in line for section in sections_to_include):
                    include_section = False
            # Include content if in relevant section
            elif include_section:
                prompt_content += f"{line}\n"

        prompt_content += "\n=== ENDE PLAYBOOK ===\n"
        prompt_content += "Nutze dieses Wissen um bessere Entscheidungen zu treffen.\n"

        return prompt_content

    def analyze_and_update(self) -> dict:
        """
        Analysiert Trade-Historie und aktualisiert das Playbook.
        Sollte wöchentlich vom Scheduler aufgerufen werden.

        Returns:
            dict: Zusammenfassung der Änderungen
        """
        if not self.conn:
            logger.warning("Keine DB-Verbindung für Playbook-Update")
            return {"error": "Keine Datenbankverbindung"}

        logger.info("Starte Playbook-Analyse...")

        changes = []
        metrics = {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Grundlegende Trade-Statistiken
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(CASE WHEN was_good_decision THEN 1 END) as good_trades,
                        AVG(outcome_24h) as avg_return_24h,
                        AVG(outcome_7d) as avg_return_7d
                    FROM trades
                    WHERE outcome_24h IS NOT NULL
                """)
                stats = cur.fetchone()
                metrics["total_trades"] = stats["total_trades"] or 0
                metrics["success_rate"] = (
                    (stats["good_trades"] / stats["total_trades"] * 100)
                    if stats["total_trades"] > 0
                    else 0
                )

                # 2. Fear & Greed Pattern Analyse
                fear_greed_patterns = self._analyze_fear_greed_patterns(cur)
                metrics["fear_greed_patterns"] = fear_greed_patterns

                # 3. Symbol-spezifische Analyse
                symbol_patterns = self._analyze_symbol_patterns(cur)
                metrics["symbol_patterns"] = symbol_patterns

                # 4. Zeitbasierte Analyse
                time_patterns = self._analyze_time_patterns(cur)
                metrics["time_patterns"] = time_patterns

                # 5. Anti-Patterns (was nicht funktioniert hat)
                anti_patterns = self._analyze_anti_patterns(cur)
                metrics["anti_patterns"] = anti_patterns

                # 6. Erfolgreiche Strategien
                success_patterns = self._analyze_success_patterns(cur)
                metrics["success_patterns"] = success_patterns

                # 7. Signal Accuracy (requires 10.1: was_correct populated)
                signal_accuracy = self._analyze_signal_accuracy(cur)
                metrics["signal_accuracy"] = signal_accuracy

            # Generiere neues Playbook
            if metrics["total_trades"] >= self.MIN_TRADES_FOR_PATTERN:
                self.current_version += 1
                self.playbook_content = self._generate_updated_playbook(metrics)
                self._save_playbook()
                self._save_to_database(metrics)

                changes.append(f"Playbook auf Version {self.current_version} aktualisiert")
                changes.append(f"Basiert auf {metrics['total_trades']} Trades")
                changes.append(f"Erfolgsrate: {metrics['success_rate']:.1f}%")

                logger.info(f"Playbook v{self.current_version} generiert")
            else:
                changes.append(
                    f"Nicht genug Trades ({metrics['total_trades']}/{self.MIN_TRADES_FOR_PATTERN})"
                )

        except Exception as e:
            logger.error(f"Playbook-Analyse Fehler: {e}")
            return {"error": str(e)}

        return {
            "version": self.current_version,
            "changes": changes,
            "metrics": metrics,
        }

    def _analyze_signal_accuracy(self, cur) -> dict:
        """Analysiert Signal-Accuracy aus signal_components.

        Returns per-signal accuracy rates and overall stats.
        Requires 10.1 (was_correct populated) to produce data.
        """
        signal_columns = [
            ("fear_greed_signal", "Fear & Greed"),
            ("rsi_signal", "RSI"),
            ("macd_signal", "MACD"),
            ("trend_signal", "Trend (SMA)"),
            ("volume_signal", "Volume"),
            ("whale_signal", "Whale Activity"),
            ("sentiment_signal", "Sentiment"),
            ("macro_signal", "Macro"),
            ("ai_direction_signal", "AI Direction"),
        ]

        signals = []

        for col, label in signal_columns:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN was_correct THEN 1 END) as correct,
                    AVG(ABS({col})) as avg_strength
                FROM signal_components
                WHERE was_correct IS NOT NULL
                AND ABS({col}) > 0.1
                """,
            )
            result = cur.fetchone()
            total = result["total"] or 0

            if total >= self.MIN_TRADES_FOR_PATTERN:
                accuracy = (result["correct"] or 0) / total * 100
                signals.append(
                    {
                        "signal": label,
                        "column": col,
                        "total": total,
                        "correct": result["correct"] or 0,
                        "accuracy": accuracy,
                        "avg_strength": float(result["avg_strength"] or 0),
                    }
                )

        # Overall accuracy
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN was_correct THEN 1 END) as correct
            FROM signal_components
            WHERE was_correct IS NOT NULL
        """)
        overall = cur.fetchone()
        overall_total = overall["total"] or 0
        overall_accuracy = (
            (overall["correct"] or 0) / overall_total * 100 if overall_total > 0 else 0
        )

        # Per-regime signal accuracy
        regime_accuracy = {}
        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN sc.was_correct THEN 1 END) as correct
                FROM signal_components sc
                JOIN trades t ON sc.trade_id = t.id
                WHERE sc.was_correct IS NOT NULL
                AND t.market_trend = %s
                """,
                (regime,),
            )
            r = cur.fetchone()
            r_total = r["total"] or 0
            if r_total >= self.MIN_TRADES_FOR_PATTERN:
                regime_accuracy[regime] = {
                    "total": r_total,
                    "accuracy": (r["correct"] or 0) / r_total * 100,
                }

        return {
            "signals": sorted(signals, key=lambda x: -x["accuracy"]),
            "overall_total": overall_total,
            "overall_accuracy": overall_accuracy,
            "regime_accuracy": regime_accuracy,
        }

    def _analyze_fear_greed_patterns(self, cur) -> list[dict]:
        """Analysiert Fear & Greed Patterns, stratifiziert nach Regime."""
        patterns = []

        ranges = [
            (0, 20, "Extreme Fear"),
            (20, 40, "Fear"),
            (40, 60, "Neutral"),
            (60, 80, "Greed"),
            (80, 100, "Extreme Greed"),
        ]

        regimes = ["BULL", "BEAR", "SIDEWAYS", None]

        for min_fg, max_fg, label in ranges:
            for action in ["BUY", "SELL"]:
                for regime in regimes:
                    regime_filter = (
                        "AND market_trend = %s" if regime else "AND market_trend IS NOT NULL"
                    )
                    params = [min_fg, max_fg, action]
                    if regime:
                        params.append(regime)

                    cur.execute(
                        f"""
                        SELECT
                            COUNT(*) as trades,
                            COUNT(CASE WHEN was_good_decision THEN 1 END) as wins,
                            AVG(outcome_24h) as avg_return,
                            STDDEV(outcome_24h) as volatility
                        FROM trades
                        WHERE fear_greed >= %s AND fear_greed < %s
                        AND action = %s
                        {regime_filter}
                        AND outcome_24h IS NOT NULL
                        """,
                        params,
                    )
                    result = cur.fetchone()

                    if result["trades"] and result["trades"] >= self.MIN_TRADES_FOR_PATTERN:
                        patterns.append(
                            {
                                "range": label,
                                "min": min_fg,
                                "max": max_fg,
                                "action": action,
                                "regime": regime or "ALL",
                                "trades": result["trades"],
                                "success_rate": result["wins"] / result["trades"] * 100,
                                "avg_return": float(result["avg_return"] or 0),
                                "volatility": float(result["volatility"] or 0),
                            }
                        )

        return patterns

    def _analyze_symbol_patterns(self, cur) -> list[dict]:
        """Analysiert Symbol-spezifische Patterns"""
        cur.execute(
            """
            SELECT
                symbol,
                action,
                COUNT(*) as trades,
                COUNT(CASE WHEN was_good_decision THEN 1 END) as wins,
                AVG(outcome_24h) as avg_return
            FROM trades
            WHERE outcome_24h IS NOT NULL
            GROUP BY symbol, action
            HAVING COUNT(*) >= %s
            ORDER BY COUNT(*) DESC
        """,
            (self.MIN_TRADES_FOR_PATTERN,),
        )

        return [
            {
                "symbol": row["symbol"],
                "action": row["action"],
                "trades": row["trades"],
                "success_rate": row["wins"] / row["trades"] * 100,
                "avg_return": float(row["avg_return"] or 0),
            }
            for row in cur.fetchall()
        ]

    def _analyze_time_patterns(self, cur) -> dict:
        """Analysiert zeitbasierte Patterns (Wochentag, Stunde)"""
        # Wochentag-Analyse
        cur.execute("""
            SELECT
                EXTRACT(DOW FROM timestamp) as day_of_week,
                COUNT(*) as trades,
                AVG(outcome_24h) as avg_return
            FROM trades
            WHERE outcome_24h IS NOT NULL
            GROUP BY EXTRACT(DOW FROM timestamp)
            ORDER BY avg_return DESC
        """)
        weekday_data = cur.fetchall()

        # Stunden-Analyse
        cur.execute("""
            SELECT
                EXTRACT(HOUR FROM timestamp) as hour,
                COUNT(*) as trades,
                AVG(outcome_24h) as avg_return
            FROM trades
            WHERE outcome_24h IS NOT NULL
            GROUP BY EXTRACT(HOUR FROM timestamp)
            HAVING COUNT(*) >= 3
            ORDER BY avg_return DESC
            LIMIT 5
        """)
        hour_data = cur.fetchall()

        return {
            "best_weekdays": weekday_data[:3] if weekday_data else [],
            "best_hours": hour_data,
        }

    def _analyze_anti_patterns(self, cur) -> dict:
        """Findet Patterns die NICHT funktioniert haben, stratifiziert nach Regime."""
        results = {}

        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            cur.execute(
                """
                SELECT
                    fear_greed,
                    action,
                    symbol,
                    market_trend,
                    COUNT(*) as trades,
                    AVG(outcome_24h) as avg_return
                FROM trades
                WHERE outcome_24h IS NOT NULL
                AND was_good_decision = FALSE
                AND market_trend = %s
                GROUP BY fear_greed, action, symbol, market_trend
                HAVING COUNT(*) >= %s AND AVG(outcome_24h) < -1
                ORDER BY AVG(outcome_24h) ASC
                LIMIT 5
                """,
                (regime, self.MIN_TRADES_FOR_PATTERN),
            )

            results[regime] = [
                {
                    "fear_greed": row["fear_greed"],
                    "action": row["action"],
                    "symbol": row["symbol"],
                    "trend": row["market_trend"],
                    "trades": row["trades"],
                    "avg_return": float(row["avg_return"]),
                }
                for row in cur.fetchall()
            ]

        # Also keep global top anti-patterns for backwards compatibility
        cur.execute(
            """
            SELECT
                fear_greed, action, symbol, market_trend,
                COUNT(*) as trades, AVG(outcome_24h) as avg_return
            FROM trades
            WHERE outcome_24h IS NOT NULL AND was_good_decision = FALSE
            GROUP BY fear_greed, action, symbol, market_trend
            HAVING COUNT(*) >= %s AND AVG(outcome_24h) < -1
            ORDER BY AVG(outcome_24h) ASC
            LIMIT 10
            """,
            (self.MIN_TRADES_FOR_PATTERN,),
        )
        results["ALL"] = [
            {
                "fear_greed": row["fear_greed"],
                "action": row["action"],
                "symbol": row["symbol"],
                "trend": row["market_trend"],
                "trades": row["trades"],
                "avg_return": float(row["avg_return"]),
            }
            for row in cur.fetchall()
        ]

        return results

    def _analyze_success_patterns(self, cur) -> dict:
        """Findet die erfolgreichsten Patterns, stratifiziert nach Regime."""
        results = {}

        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            cur.execute(
                """
                SELECT
                    fear_greed,
                    action,
                    symbol,
                    market_trend,
                    COUNT(*) as trades,
                    AVG(outcome_24h) as avg_return,
                    COUNT(CASE WHEN was_good_decision THEN 1 END)::float
                        / COUNT(*) as win_rate
                FROM trades
                WHERE outcome_24h IS NOT NULL
                AND was_good_decision = TRUE
                AND market_trend = %s
                GROUP BY fear_greed, action, symbol, market_trend
                HAVING COUNT(*) >= %s AND AVG(outcome_24h) > 1
                ORDER BY win_rate DESC, AVG(outcome_24h) DESC
                LIMIT 5
                """,
                (regime, self.MIN_TRADES_FOR_PATTERN),
            )

            results[regime] = [
                {
                    "fear_greed": row["fear_greed"],
                    "action": row["action"],
                    "symbol": row["symbol"],
                    "trend": row["market_trend"],
                    "trades": row["trades"],
                    "avg_return": float(row["avg_return"]),
                    "win_rate": float(row["win_rate"]) * 100,
                }
                for row in cur.fetchall()
            ]

        # Global top patterns
        cur.execute(
            """
            SELECT
                fear_greed, action, symbol, market_trend,
                COUNT(*) as trades, AVG(outcome_24h) as avg_return,
                COUNT(CASE WHEN was_good_decision THEN 1 END)::float / COUNT(*) as win_rate
            FROM trades
            WHERE outcome_24h IS NOT NULL AND was_good_decision = TRUE
            GROUP BY fear_greed, action, symbol, market_trend
            HAVING COUNT(*) >= %s AND AVG(outcome_24h) > 1
            ORDER BY win_rate DESC, AVG(outcome_24h) DESC
            LIMIT 10
            """,
            (self.MIN_TRADES_FOR_PATTERN,),
        )
        results["ALL"] = [
            {
                "fear_greed": row["fear_greed"],
                "action": row["action"],
                "symbol": row["symbol"],
                "trend": row["market_trend"],
                "trades": row["trades"],
                "avg_return": float(row["avg_return"]),
                "win_rate": float(row["win_rate"]) * 100,
            }
            for row in cur.fetchall()
        ]

        return results

    def _generate_updated_playbook(self, metrics: dict) -> str:
        """Generiert ein aktualisiertes Playbook basierend auf Metriken"""
        now = datetime.now()

        playbook = f"""# 🎯 TRADING PLAYBOOK

Version: {self.current_version}
Letzte Aktualisierung: {now.strftime("%Y-%m-%d %H:%M")}
Basiert auf: {metrics["total_trades"]} Trades
Gesamterfolgsrate: {metrics["success_rate"]:.1f}%

---

## 📊 MARKT-REGIME REGELN

### Fear & Greed Index Strategien (Datenbasiert)

| F&G Range | Aktion | Erfolgsrate | Avg Return | Trades | Empfehlung |
|-----------|--------|-------------|------------|--------|------------|
"""
        # Fear & Greed Tabelle (global view)
        fg_patterns = metrics.get("fear_greed_patterns", [])
        fg_global = [p for p in fg_patterns if p.get("regime") == "ALL"]
        if fg_global:
            for p in sorted(fg_global, key=lambda x: x["min"]):
                confidence = (
                    "Stark"
                    if p["success_rate"] > 60
                    else "Mittel"
                    if p["success_rate"] > 45
                    else "Schwach"
                )
                playbook += f"| {p['range']} ({p['min']}-{p['max']}) | {p['action']} | {p['success_rate']:.1f}% | {p['avg_return']:+.2f}% | {p['trades']} | {confidence} |\n"
        else:
            playbook += "| *Noch keine ausreichenden Daten* | - | - | - | - | - |\n"

        # Regime-stratified Fear & Greed
        playbook += "\n### Regime-spezifische F&G Regeln\n\n"
        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            fg_regime = [p for p in fg_patterns if p.get("regime") == regime]
            if fg_regime:
                playbook += f"**{regime} Regime:**\n"
                best = sorted(fg_regime, key=lambda x: -x["success_rate"])[:3]
                for p in best:
                    emoji = "+" if p["avg_return"] > 0 else ""
                    playbook += (
                        f"- {p['action']} bei {p['range']}: "
                        f"{p['success_rate']:.0f}% Erfolg, "
                        f"{emoji}{p['avg_return']:.2f}% avg ({p['trades']} Trades)\n"
                    )
                playbook += "\n"

        playbook += """### Automatisch gelernte Regeln

"""
        # Beste Fear & Greed Strategien
        best_fg = [
            p
            for p in fg_patterns
            if p["success_rate"] > 55 and p["trades"] >= self.MIN_TRADES_FOR_RULE
        ]
        if best_fg:
            playbook += "**Empfohlene Strategien:**\n"
            for p in sorted(best_fg, key=lambda x: -x["success_rate"])[:5]:
                regime_info = f" [{p.get('regime', 'ALL')}]" if p.get("regime") != "ALL" else ""
                playbook += f"- {p['action']} bei {p['range']}{regime_info}: {p['success_rate']:.0f}% Erfolgsrate ({p['trades']} Trades)\n"
        else:
            playbook += "> Noch nicht genug Daten für automatische Regeln.\n"

        playbook += """
---

## 🪙 SYMBOL-SPEZIFISCHE REGELN

"""
        symbol_patterns = metrics.get("symbol_patterns", [])
        if symbol_patterns:
            playbook += "| Symbol | Aktion | Erfolgsrate | Avg Return | Trades |\n"
            playbook += "|--------|--------|-------------|------------|--------|\n"
            for p in symbol_patterns[:10]:
                playbook += f"| {p['symbol']} | {p['action']} | {p['success_rate']:.1f}% | {p['avg_return']:+.2f}% | {p['trades']} |\n"
        else:
            playbook += "> Noch keine symbol-spezifischen Daten.\n"

        # Signal Accuracy Section
        playbook += self._generate_signal_accuracy_section(metrics)

        # Anti-Patterns (regime-stratified)
        playbook += """
---

## ❌ WAS NICHT FUNKTIONIERT HAT (Anti-Patterns)

"""
        anti_patterns = metrics.get("anti_patterns", {})
        if isinstance(anti_patterns, dict):
            # Regime-stratified format
            for regime in ["BULL", "BEAR", "SIDEWAYS"]:
                regime_anti = anti_patterns.get(regime, [])
                if regime_anti:
                    playbook += f"### {regime} Regime - Vermeide:\n\n"
                    for i, p in enumerate(regime_anti[:3], 1):
                        playbook += (
                            f"{i}. **{p['action']} {p['symbol']}** bei F&G={p['fear_greed']}\n"
                        )
                        playbook += (
                            f"   - Avg Return: {p['avg_return']:+.2f}% ({p['trades']} Trades)\n\n"
                        )

            # Global fallback
            all_anti = anti_patterns.get("ALL", [])
            if all_anti:
                playbook += "### Global Top Anti-Patterns:\n\n"
                for i, p in enumerate(all_anti[:5], 1):
                    playbook += f"{i}. **{p['action']} {p['symbol']}** F&G={p['fear_greed']}, Trend={p['trend']}: {p['avg_return']:+.2f}% ({p['trades']}x)\n"
            elif not any(anti_patterns.get(r) for r in ["BULL", "BEAR", "SIDEWAYS"]):
                playbook += "> Noch keine signifikanten Anti-Patterns gefunden.\n"
        else:
            playbook += "> Noch keine Anti-Pattern-Daten.\n"

        # Success Patterns (regime-stratified)
        playbook += """
---

## ✅ WAS GUT FUNKTIONIERT HAT (Erfolgs-Patterns)

"""
        success_patterns = metrics.get("success_patterns", {})
        if isinstance(success_patterns, dict):
            for regime in ["BULL", "BEAR", "SIDEWAYS"]:
                regime_success = success_patterns.get(regime, [])
                if regime_success:
                    playbook += f"### {regime} Regime - Bevorzuge:\n\n"
                    for i, p in enumerate(regime_success[:3], 1):
                        playbook += (
                            f"{i}. **{p['action']} {p['symbol']}** bei F&G={p['fear_greed']}\n"
                        )
                        playbook += f"   - Win Rate: {p['win_rate']:.0f}%, Avg: {p['avg_return']:+.2f}% ({p['trades']}x)\n\n"

            all_success = success_patterns.get("ALL", [])
            if all_success:
                playbook += "### Global Top Erfolgs-Patterns:\n\n"
                for i, p in enumerate(all_success[:5], 1):
                    playbook += f"{i}. **{p['action']} {p['symbol']}** F&G={p['fear_greed']}, Trend={p['trend']}: Win={p['win_rate']:.0f}%, Avg={p['avg_return']:+.2f}% ({p['trades']}x)\n"
            elif not any(success_patterns.get(r) for r in ["BULL", "BEAR", "SIDEWAYS"]):
                playbook += "> Noch keine signifikanten Erfolgs-Patterns gefunden.\n"
        else:
            playbook += "> Noch keine Erfolgs-Pattern-Daten.\n"

        playbook += """
---

## ⏰ ZEIT-BASIERTE ERKENNTNISSE

"""
        time_patterns = metrics.get("time_patterns", {})
        best_hours = time_patterns.get("best_hours", [])
        if best_hours:
            playbook += "### Beste Trading-Zeiten (UTC)\n"
            for h in best_hours[:3]:
                playbook += f"- **{int(h['hour']):02d}:00 Uhr**: {h['avg_return']:+.2f}% avg ({h['trades']} Trades)\n"
        else:
            playbook += "> Noch keine Zeit-Analyse verfügbar.\n"

        playbook += f"""
---

## 🎛️ AKTUELLE PARAMETER

### Position Sizing (Automatisch angepasst)
- **Basis Position**: 20 USDT pro Grid-Level
- **Bei hoher Konfidenz (>70%)**: +50% Position
- **Bei niedriger Konfidenz (<40%)**: -50% Position

### Confidence Thresholds
- **Minimum für Trade**: 0.5
- **Für größere Position**: 0.7

### Risiko-Limits
- **Max Drawdown**: 10%
- **Stop-Loss**: 5% trailing

---

## 📈 PERFORMANCE METRIKEN

| Metrik | Wert |
|--------|------|
| Gesamte Trades (mit Outcome) | {metrics["total_trades"]} |
| Erfolgsrate | {metrics["success_rate"]:.1f}% |
| Playbook Version | {self.current_version} |
| Letzte Aktualisierung | {now.strftime("%Y-%m-%d %H:%M")} |

---

## 📚 VERSIONS-HISTORIE

| Version | Datum | Trades | Erfolgsrate |
|---------|-------|--------|-------------|
| {self.current_version} | {now.strftime("%Y-%m-%d")} | {metrics["total_trades"]} | {metrics["success_rate"]:.1f}% |

---

*Dieses Dokument wurde automatisch generiert basierend auf {metrics["total_trades"]} echten Trades.*
*Nächste Aktualisierung: In 7 Tagen oder nach 50 neuen Trades.*
"""

        return playbook

    def _generate_signal_accuracy_section(self, metrics: dict) -> str:
        """Generates the signal accuracy section for the playbook."""
        signal_data = metrics.get("signal_accuracy", {})
        signals = signal_data.get("signals", [])
        overall_total = signal_data.get("overall_total", 0)
        overall_accuracy = signal_data.get("overall_accuracy", 0)
        regime_accuracy = signal_data.get("regime_accuracy", {})

        section = """
---

## 🎯 SIGNAL ACCURACY

"""
        if overall_total < self.MIN_TRADES_FOR_PATTERN:
            section += "> Noch nicht genug ausgewertete Signale.\n"
            return section

        section += f"Gesamt: {overall_accuracy:.1f}% Accuracy ({overall_total} Signale)\n\n"

        # Per-regime overall accuracy
        if regime_accuracy:
            section += "### Accuracy pro Regime\n\n"
            for regime in ["BULL", "BEAR", "SIDEWAYS"]:
                if regime in regime_accuracy:
                    ra = regime_accuracy[regime]
                    section += f"- **{regime}**: {ra['accuracy']:.1f}% ({ra['total']} Signale)\n"
            section += "\n"

        # Per-signal breakdown
        if signals:
            section += "### Signal-Trefferquoten\n\n"
            section += "| Signal | Accuracy | Stärke | Evaluiert |\n"
            section += "|--------|----------|--------|----------|\n"
            for s in signals:
                reliability = (
                    "Zuverlässig"
                    if s["accuracy"] > 60
                    else "Mittel"
                    if s["accuracy"] > 45
                    else "Schwach"
                )
                section += (
                    f"| {s['signal']} | {s['accuracy']:.1f}% ({reliability}) | "
                    f"{s['avg_strength']:.2f} | {s['total']} |\n"
                )

            # Top 3 most reliable
            top3 = [s for s in signals if s["accuracy"] > 55][:3]
            if top3:
                section += "\n**Zuverlässigste Signale:**\n"
                for s in top3:
                    section += f"- {s['signal']}: {s['accuracy']:.0f}% Trefferquote\n"

            # Worst signals to de-weight
            worst = [s for s in signals if s["accuracy"] < 45]
            if worst:
                section += "\n**Unzuverlässige Signale (de-gewichten):**\n"
                for s in worst:
                    section += f"- {s['signal']}: nur {s['accuracy']:.0f}%\n"

        return section

    def _save_to_database(self, metrics: dict):
        """Speichert die Playbook-Version in der Datenbank"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO playbook_versions
                        (version, content, trade_count, success_rate, changes_summary, metrics)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        self.current_version,
                        self.playbook_content,
                        metrics["total_trades"],
                        metrics["success_rate"],
                        f"Auto-Update basierend auf {metrics['total_trades']} Trades",
                        json.dumps(metrics, default=str),
                    ),
                )
                self.conn.commit()
        except Exception as e:
            logger.error(f"Playbook DB-Speichern Fehler: {e}")

    def add_manual_note(self, note: str, category: str = "observation"):
        """
        Fügt eine manuelle Notiz zum Playbook hinzu.

        Args:
            note: Die Notiz
            category: observation, rule, warning
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Finde den Notizen-Abschnitt
        marker = "### Manuelle Einträge"
        if marker in self.playbook_content:
            insert_pos = self.playbook_content.find(marker) + len(marker)
            new_entry = f"\n- [{timestamp}] **{category.upper()}**: {note}"
            self.playbook_content = (
                self.playbook_content[:insert_pos] + new_entry + self.playbook_content[insert_pos:]
            )
            self._save_playbook()
            logger.info(f"Manuelle Notiz hinzugefügt: {note[:50]}...")


# Singleton-Instanz
_playbook_instance: TradingPlaybook | None = None


def get_playbook(db_connection=None) -> TradingPlaybook:
    """Gibt die globale Playbook-Instanz zurück"""
    global _playbook_instance
    if _playbook_instance is None:
        _playbook_instance = TradingPlaybook(db_connection)
    return _playbook_instance
