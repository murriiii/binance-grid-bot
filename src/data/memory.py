"""
Trading Memory System mit PostgreSQL
"Gedächtnis" für den Bot - lernt aus vergangenen Entscheidungen

Konzept:
- Speichert JEDEN Trade mit Kontext
- Speichert Marktbedingungen
- Trackt ob Entscheidungen gut waren
- Findet ähnliche historische Situationen
- Gibt DeepSeek Kontext für bessere Entscheidungen

Das ist KEIN echtes ML-Training, sondern:
- RAG (Retrieval Augmented Generation)
- In-Context Learning
- Pattern Recognition durch Beispiele
"""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("trading_bot")


@dataclass
class TradeRecord:
    """Ein Trade mit vollständigem Kontext"""

    # Trade Details
    timestamp: datetime
    action: str  # BUY, SELL, HOLD
    symbol: str
    price: float
    quantity: float
    value_usd: float

    # Markt-Kontext zum Zeitpunkt
    fear_greed: int
    btc_price: float
    symbol_24h_change: float
    market_trend: str  # BULL, BEAR, SIDEWAYS

    # Entscheidungs-Kontext
    math_signal: str  # Was sagte Markowitz?
    ai_signal: str  # Was sagte DeepSeek?
    reasoning: str  # Vollständige Begründung

    # Fees
    fee_usd: float = 0.0

    # Slippage tracking (D4)
    expected_price: float | None = None  # Limit order price
    slippage_bps: float | None = None  # Basis points: positive = worse execution

    # Ergebnis (wird später aktualisiert)
    outcome_24h: float | None = None  # PnL nach 24h
    outcome_7d: float | None = None  # PnL nach 7 Tagen
    was_good_decision: bool | None = None


@dataclass
class MarketSnapshot:
    """Markt-Zustand zu einem Zeitpunkt"""

    timestamp: datetime
    fear_greed: int
    btc_price: float
    total_market_cap: float
    btc_dominance: float
    top_gainers: list[str]
    top_losers: list[str]
    trending_coins: list[str]
    notable_news: str


class TradingMemory:
    """
    PostgreSQL-basiertes Gedächtnis für den Trading Bot.

    Features:
    1. Speichert alle Trades mit Kontext
    2. Findet ähnliche historische Situationen
    3. Analysiert welche Strategien funktioniert haben
    4. Generiert Kontext für DeepSeek Prompts
    """

    def __init__(self):
        self.db = None
        self._connect()

    def _connect(self):
        """Verbindet via DatabaseManager Pool."""
        try:
            from src.data.database import DatabaseManager

            db = DatabaseManager.get_instance()
            if db and db._pool:
                self.db = db
                logger.info("TradingMemory: connected via DatabaseManager")
            else:
                logger.warning("TradingMemory: DatabaseManager pool unavailable")
        except Exception as e:
            logger.error(f"TradingMemory: connection error: {e}")
            self.db = None

    def save_trade(self, trade: TradeRecord) -> int:
        """Speichert einen Trade"""
        if not self.db:
            return -1

        try:
            with self.db.get_cursor(dict_cursor=False) as cur:
                cur.execute(
                    """
                    INSERT INTO trades (
                        timestamp, action, symbol, price, quantity, value_usd,
                        fear_greed, btc_price, symbol_24h_change, market_trend,
                        math_signal, ai_signal, reasoning, fee_usd,
                        expected_price, slippage_bps
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING id
                """,
                    (
                        trade.timestamp,
                        trade.action,
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.value_usd,
                        trade.fear_greed,
                        trade.btc_price,
                        trade.symbol_24h_change,
                        trade.market_trend,
                        trade.math_signal,
                        trade.ai_signal,
                        trade.reasoning,
                        trade.fee_usd,
                        trade.expected_price,
                        trade.slippage_bps,
                    ),
                )
                trade_id = cur.fetchone()[0]
                return trade_id
        except Exception as e:
            logger.error(f"TradingMemory: save_trade error: {e}")
            return -1

    def update_trade_outcome(
        self, trade_id: int, outcome_24h: float | None = None, outcome_7d: float | None = None
    ):
        """Aktualisiert das Ergebnis eines Trades"""
        if not self.db:
            return

        # Bestimme ob es eine gute Entscheidung war
        was_good = None
        if outcome_24h is not None:
            # Simpel: > 0 = gut, aber mit Toleranz für Fees
            was_good = outcome_24h > -0.5  # 0.5% Toleranz für Fees

        with self.db.get_cursor(dict_cursor=False) as cur:
            cur.execute(
                """
                UPDATE trades
                SET outcome_24h = COALESCE(%s, outcome_24h),
                    outcome_7d = COALESCE(%s, outcome_7d),
                    was_good_decision = COALESCE(%s, was_good_decision)
                WHERE id = %s
            """,
                (outcome_24h, outcome_7d, was_good, trade_id),
            )

    @staticmethod
    def _similarity_score(
        candidate: dict,
        fear_greed: int,
        symbol: str | None,
        market_trend: str | None,
    ) -> float:
        """Multi-dimensional similarity scoring (C1).

        Dimensions with weights:
        - Fear&Greed distance (30%): Gaussian decay, sigma=15
        - Regime match (25%): exact match on market_trend
        - Symbol match (20%): exact=1.0, same base=0.5
        - Temporal decay (15%): half-life 30 days
        - Outcome quality (10%): boost trades with known outcomes
        """
        score = 0.0

        # 1. Fear&Greed distance (30%) — Gaussian kernel
        fg_diff = abs((candidate.get("fear_greed") or 50) - fear_greed)
        score += 0.30 * math.exp(-(fg_diff**2) / (2 * 15**2))

        # 2. Regime match (25%)
        if market_trend and candidate.get("market_trend"):
            score += 0.25 * (1.0 if candidate["market_trend"] == market_trend else 0.0)
        else:
            score += 0.25 * 0.5  # neutral if unknown

        # 3. Symbol match (20%)
        if symbol and candidate.get("symbol"):
            if candidate["symbol"] == symbol:
                score += 0.20
            elif candidate["symbol"][:3] == symbol[:3]:
                score += 0.20 * 0.5
        else:
            score += 0.20 * 0.3

        # 4. Temporal decay (15%) — exponential half-life 30 days
        ts = candidate.get("timestamp")
        if ts:
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts = None
            if ts:
                days_ago = (datetime.now() - ts).total_seconds() / 86400
                score += 0.15 * math.exp(-0.693 * days_ago / 30)

        # 5. Outcome quality (10%) — boost trades with known outcomes
        if candidate.get("outcome_24h") is not None:
            score += 0.10
        elif candidate.get("outcome_7d") is not None:
            score += 0.05

        return score

    def find_similar_situations(
        self,
        fear_greed: int,
        symbol: str | None = None,
        market_trend: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Findet ähnliche historische Situationen (C1: Multi-Dimensional Scoring).

        Loads a broad candidate pool and ranks by weighted similarity score
        across Fear&Greed distance, regime, symbol, recency, and outcome quality.
        """
        if not self.db:
            return []

        # Broad candidate pool: F&G ±25 OR last 500 trades with outcomes
        fg_min = max(0, fear_greed - 25)
        fg_max = min(100, fear_greed + 25)

        with self.db.get_cursor() as cur:
            cur.execute(
                """
                (
                    SELECT timestamp, action, symbol, price, value_usd,
                           fear_greed, market_trend, reasoning,
                           outcome_24h, outcome_7d, was_good_decision
                    FROM trades
                    WHERE fear_greed BETWEEN %s AND %s
                    AND outcome_24h IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 500
                )
                UNION
                (
                    SELECT timestamp, action, symbol, price, value_usd,
                           fear_greed, market_trend, reasoning,
                           outcome_24h, outcome_7d, was_good_decision
                    FROM trades
                    WHERE outcome_24h IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 500
                )
                """,
                [fg_min, fg_max],
            )
            candidates = cur.fetchall()

        if not candidates:
            return []

        # Score and rank
        scored = [
            (self._similarity_score(c, fear_greed, symbol, market_trend), c) for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        return [c for _, c in scored[:limit]]

    def get_pattern_stats(self, conditions: dict) -> dict:
        """
        Analysiert wie gut bestimmte Bedingungen funktioniert haben.

        Beispiel:
        conditions = {"fear_greed_max": 30, "action": "BUY"}
        -> "Wie gut waren Kaufe bei Fear < 30?"
        """
        if not self.db:
            return {}

        with self.db.get_cursor() as cur:
            query = """
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN was_good_decision THEN 1 END) as good_trades,
                    AVG(outcome_24h) as avg_24h_return,
                    AVG(outcome_7d) as avg_7d_return,
                    STDDEV(outcome_24h) as volatility
                FROM trades
                WHERE outcome_24h IS NOT NULL
            """
            params: list = []

            if "fear_greed_min" in conditions:
                query += " AND fear_greed >= %s"
                params.append(conditions["fear_greed_min"])

            if "fear_greed_max" in conditions:
                query += " AND fear_greed <= %s"
                params.append(conditions["fear_greed_max"])

            if "action" in conditions:
                query += " AND action = %s"
                params.append(conditions["action"])

            if "symbol" in conditions:
                query += " AND symbol = %s"
                params.append(conditions["symbol"])

            cur.execute(query, params)
            result = cur.fetchone()

            if result and result["total_trades"] > 0:
                return {
                    "total_trades": result["total_trades"],
                    "success_rate": result["good_trades"] / result["total_trades"] * 100,
                    "avg_24h_return": float(result["avg_24h_return"] or 0),
                    "avg_7d_return": float(result["avg_7d_return"] or 0),
                    "volatility": float(result["volatility"] or 0),
                }
            return {}

    def generate_context_for_ai(
        self, current_fear_greed: int, symbol: str, proposed_action: str
    ) -> str:
        """
        Generiert Kontext für DeepSeek basierend auf historischen Daten.

        DAS IST DER KERN DES "LERNENS"!

        Statt: "Soll ich SOL kaufen?"
        Wird:  "Soll ich SOL kaufen? Hier sind 10 ähnliche Situationen
                aus meiner Geschichte, 7 waren profitabel..."
        """
        # Finde ähnliche Situationen
        similar = self.find_similar_situations(
            fear_greed=current_fear_greed, symbol=symbol, limit=10
        )

        # Analysiere Pattern-Stats
        buy_at_fear_stats = self.get_pattern_stats({"fear_greed_max": 30, "action": "BUY"})

        buy_at_greed_stats = self.get_pattern_stats({"fear_greed_min": 70, "action": "BUY"})

        # Baue Kontext-String
        context = f"""
=== HISTORISCHE DATEN AUS MEINEM GEDÄCHTNIS ===

ÄHNLICHE SITUATIONEN (Fear&Greed ±10 von {current_fear_greed}):
"""
        if similar:
            good_count = sum(1 for s in similar if s.get("was_good_decision"))

            context += f"Gefunden: {len(similar)} ähnliche Trades\n"
            context += (
                f"Davon erfolgreich: {good_count} ({good_count / len(similar) * 100:.0f}%)\n\n"
            )

            for i, trade in enumerate(similar[:5], 1):
                outcome = "OK" if trade.get("was_good_decision") else "FAIL"
                trend_tag = f" [{trade.get('market_trend', '?')}]"
                context += f"{i}. {outcome} {trade['action']} {trade['symbol']}"
                context += f"{trend_tag} bei F&G={trade['fear_greed']}: "
                context += f"{trade['outcome_24h']:+.2f}% (24h)\n"
        else:
            context += "Keine ähnlichen Situationen in der Datenbank.\n"

        context += f"""
PATTERN-ANALYSE:

Käufe bei Fear (<30):
  - Trades: {buy_at_fear_stats.get("total_trades", 0)}
  - Erfolgsrate: {buy_at_fear_stats.get("success_rate", 0):.1f}%
  - Avg Return: {buy_at_fear_stats.get("avg_24h_return", 0):+.2f}%

Käufe bei Greed (>70):
  - Trades: {buy_at_greed_stats.get("total_trades", 0)}
  - Erfolgsrate: {buy_at_greed_stats.get("success_rate", 0):.1f}%
  - Avg Return: {buy_at_greed_stats.get("avg_24h_return", 0):+.2f}%

=== AKTUELLE ENTSCHEIDUNG ===
Vorgeschlagene Aktion: {proposed_action} {symbol}
Aktueller Fear&Greed: {current_fear_greed}

Basierend auf meiner Historie, ist das eine gute Entscheidung?
"""
        return context

    def learn_and_update_patterns(self):
        """
        Analysiert alle Trades und aktualisiert gelernte Patterns.
        Sollte regelmäßig laufen (z.B. täglich).
        """
        if not self.db:
            return

        patterns_to_check = [
            ("buy_extreme_fear", {"fear_greed_max": 25, "action": "BUY"}),
            ("buy_fear", {"fear_greed_min": 25, "fear_greed_max": 45, "action": "BUY"}),
            ("buy_neutral", {"fear_greed_min": 45, "fear_greed_max": 55, "action": "BUY"}),
            ("buy_greed", {"fear_greed_min": 55, "fear_greed_max": 75, "action": "BUY"}),
            ("buy_extreme_greed", {"fear_greed_min": 75, "action": "BUY"}),
            ("sell_extreme_fear", {"fear_greed_max": 25, "action": "SELL"}),
            ("sell_extreme_greed", {"fear_greed_min": 75, "action": "SELL"}),
        ]

        with self.db.get_cursor(dict_cursor=False) as cur:
            for pattern_name, conditions in patterns_to_check:
                stats = self.get_pattern_stats(conditions)

                if stats.get("total_trades", 0) >= 5:  # Mindestens 5 Samples
                    cur.execute(
                        """
                        INSERT INTO learned_patterns
                            (pattern_name, conditions, success_rate, sample_size, avg_return)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (pattern_name)
                        DO UPDATE SET
                            success_rate = EXCLUDED.success_rate,
                            sample_size = EXCLUDED.sample_size,
                            avg_return = EXCLUDED.avg_return,
                            last_updated = NOW()
                    """,
                        (
                            pattern_name,
                            json.dumps(conditions),
                            stats["success_rate"],
                            stats["total_trades"],
                            stats["avg_24h_return"],
                        ),
                    )

    def get_trading_insights(self) -> str:
        """
        Generiert einen Insights-Report basierend auf allen Daten.
        Perfekt für tägliche Telegram-Updates.
        """
        if not self.db:
            return "Keine Datenbank-Verbindung"

        with self.db.get_cursor() as cur:
            # Gesamt-Statistiken
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN was_good_decision THEN 1 END) as good_trades,
                    AVG(outcome_24h) as avg_return,
                    MAX(outcome_24h) as best_trade,
                    MIN(outcome_24h) as worst_trade
                FROM trades
                WHERE outcome_24h IS NOT NULL
            """)
            stats = cur.fetchone()

            # Beste Patterns
            cur.execute("""
                SELECT pattern_name, success_rate, sample_size, avg_return
                FROM learned_patterns
                WHERE sample_size >= 5
                ORDER BY success_rate DESC
                LIMIT 3
            """)
            best_patterns = cur.fetchall()

        report = f"""
*TRADING INSIGHTS*

*Gesamt-Performance:*
- Trades: {stats["total_trades"] or 0}
- Erfolgsrate: {(stats["good_trades"] or 0) / max(stats["total_trades"] or 1, 1) * 100:.1f}%
- Avg Return: {stats["avg_return"] or 0:+.2f}%
- Bester Trade: {stats["best_trade"] or 0:+.2f}%
- Schlechtester: {stats["worst_trade"] or 0:+.2f}%

*Beste Strategien:*
"""
        for p in best_patterns:
            report += (
                f"- {p['pattern_name']}: {p['success_rate']:.1f}% ({p['sample_size']} Trades)\n"
            )

        return report
