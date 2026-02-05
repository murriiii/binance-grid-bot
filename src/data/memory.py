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
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import json

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger('trading_bot')

# PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.warning("psycopg2 nicht installiert - pip install psycopg2-binary")


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
    ai_signal: str    # Was sagte DeepSeek?
    reasoning: str    # Vollständige Begründung

    # Ergebnis (wird später aktualisiert)
    outcome_24h: Optional[float] = None  # PnL nach 24h
    outcome_7d: Optional[float] = None   # PnL nach 7 Tagen
    was_good_decision: Optional[bool] = None


@dataclass
class MarketSnapshot:
    """Markt-Zustand zu einem Zeitpunkt"""
    timestamp: datetime
    fear_greed: int
    btc_price: float
    total_market_cap: float
    btc_dominance: float
    top_gainers: List[str]
    top_losers: List[str]
    trending_coins: List[str]
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
        self.conn = None
        self.connect()

    def connect(self):
        """Verbindet zur PostgreSQL Datenbank"""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar")
            return

        try:
            self.conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=os.getenv('POSTGRES_PORT', 5432),
                database=os.getenv('POSTGRES_DB', 'trading_bot'),
                user=os.getenv('POSTGRES_USER', 'trading'),
                password=os.getenv('POSTGRES_PASSWORD', '')
            )
            logger.info("PostgreSQL verbunden")
            self._create_tables()
        except Exception as e:
            logger.error(f"PostgreSQL Fehler: {e}")
            self.conn = None

    def _create_tables(self):
        """Erstellt die Tabellen wenn sie nicht existieren"""
        if not self.conn:
            return

        with self.conn.cursor() as cur:
            # Trades Tabelle
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    action VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    price DECIMAL(20, 8) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    value_usd DECIMAL(20, 2) NOT NULL,

                    -- Markt-Kontext
                    fear_greed INTEGER,
                    btc_price DECIMAL(20, 2),
                    symbol_24h_change DECIMAL(10, 4),
                    market_trend VARCHAR(20),

                    -- Entscheidungs-Kontext
                    math_signal TEXT,
                    ai_signal TEXT,
                    reasoning TEXT,

                    -- Ergebnis
                    outcome_24h DECIMAL(10, 4),
                    outcome_7d DECIMAL(10, 4),
                    was_good_decision BOOLEAN,

                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_trades_fear_greed ON trades(fear_greed);
            """)

            # Market Snapshots Tabelle
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    fear_greed INTEGER,
                    btc_price DECIMAL(20, 2),
                    total_market_cap DECIMAL(30, 2),
                    btc_dominance DECIMAL(5, 2),
                    top_gainers JSONB,
                    top_losers JSONB,
                    trending_coins JSONB,
                    notable_news TEXT,

                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON market_snapshots(timestamp);
            """)

            # Patterns Tabelle (was funktioniert hat)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id SERIAL PRIMARY KEY,
                    pattern_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    conditions JSONB,  -- {"fear_greed_min": 20, "fear_greed_max": 30, ...}
                    success_rate DECIMAL(5, 2),
                    sample_size INTEGER,
                    avg_return DECIMAL(10, 4),
                    last_updated TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            self.conn.commit()

    def save_trade(self, trade: TradeRecord) -> int:
        """Speichert einen Trade"""
        if not self.conn:
            return -1

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trades (
                    timestamp, action, symbol, price, quantity, value_usd,
                    fear_greed, btc_price, symbol_24h_change, market_trend,
                    math_signal, ai_signal, reasoning
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                trade.timestamp, trade.action, trade.symbol, trade.price,
                trade.quantity, trade.value_usd, trade.fear_greed,
                trade.btc_price, trade.symbol_24h_change, trade.market_trend,
                trade.math_signal, trade.ai_signal, trade.reasoning
            ))
            trade_id = cur.fetchone()[0]
            self.conn.commit()
            return trade_id

    def update_trade_outcome(self, trade_id: int, outcome_24h: float = None,
                             outcome_7d: float = None):
        """Aktualisiert das Ergebnis eines Trades"""
        if not self.conn:
            return

        with self.conn.cursor() as cur:
            # Bestimme ob es eine gute Entscheidung war
            was_good = None
            if outcome_24h is not None:
                # Simpel: > 0 = gut, aber mit Toleranz für Fees
                was_good = outcome_24h > -0.5  # 0.5% Toleranz für Fees

            cur.execute("""
                UPDATE trades
                SET outcome_24h = COALESCE(%s, outcome_24h),
                    outcome_7d = COALESCE(%s, outcome_7d),
                    was_good_decision = COALESCE(%s, was_good_decision)
                WHERE id = %s
            """, (outcome_24h, outcome_7d, was_good, trade_id))
            self.conn.commit()

    def find_similar_situations(
        self,
        fear_greed: int,
        symbol: str = None,
        market_trend: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Findet ähnliche historische Situationen.

        Das ist der Kern des "Lernens":
        - Suche nach Trades unter ähnlichen Bedingungen
        - Zeige was funktioniert hat und was nicht
        """
        if not self.conn:
            return []

        # Fear & Greed Range: ±10
        fg_min = max(0, fear_greed - 10)
        fg_max = min(100, fear_greed + 10)

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT
                    timestamp, action, symbol, price, value_usd,
                    fear_greed, market_trend, reasoning,
                    outcome_24h, outcome_7d, was_good_decision
                FROM trades
                WHERE fear_greed BETWEEN %s AND %s
                AND outcome_24h IS NOT NULL
            """
            params = [fg_min, fg_max]

            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)

            if market_trend:
                query += " AND market_trend = %s"
                params.append(market_trend)

            query += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            return cur.fetchall()

    def get_pattern_stats(self, conditions: Dict) -> Dict:
        """
        Analysiert wie gut bestimmte Bedingungen funktioniert haben.

        Beispiel:
        conditions = {"fear_greed_max": 30, "action": "BUY"}
        → "Wie gut waren Käufe bei Fear < 30?"
        """
        if not self.conn:
            return {}

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            params = []

            if 'fear_greed_min' in conditions:
                query += " AND fear_greed >= %s"
                params.append(conditions['fear_greed_min'])

            if 'fear_greed_max' in conditions:
                query += " AND fear_greed <= %s"
                params.append(conditions['fear_greed_max'])

            if 'action' in conditions:
                query += " AND action = %s"
                params.append(conditions['action'])

            if 'symbol' in conditions:
                query += " AND symbol = %s"
                params.append(conditions['symbol'])

            cur.execute(query, params)
            result = cur.fetchone()

            if result and result['total_trades'] > 0:
                return {
                    'total_trades': result['total_trades'],
                    'success_rate': result['good_trades'] / result['total_trades'] * 100,
                    'avg_24h_return': float(result['avg_24h_return'] or 0),
                    'avg_7d_return': float(result['avg_7d_return'] or 0),
                    'volatility': float(result['volatility'] or 0)
                }
            return {}

    def generate_context_for_ai(
        self,
        current_fear_greed: int,
        symbol: str,
        proposed_action: str
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
            fear_greed=current_fear_greed,
            symbol=symbol,
            limit=10
        )

        # Analysiere Pattern-Stats
        buy_at_fear_stats = self.get_pattern_stats({
            'fear_greed_max': 30,
            'action': 'BUY'
        })

        buy_at_greed_stats = self.get_pattern_stats({
            'fear_greed_min': 70,
            'action': 'BUY'
        })

        # Baue Kontext-String
        context = f"""
=== HISTORISCHE DATEN AUS MEINEM GEDÄCHTNIS ===

📊 ÄHNLICHE SITUATIONEN (Fear&Greed ±10 von {current_fear_greed}):
"""
        if similar:
            good_count = sum(1 for s in similar if s.get('was_good_decision'))
            bad_count = len(similar) - good_count

            context += f"Gefunden: {len(similar)} ähnliche Trades\n"
            context += f"Davon erfolgreich: {good_count} ({good_count/len(similar)*100:.0f}%)\n\n"

            for i, trade in enumerate(similar[:5], 1):
                outcome = "✅" if trade.get('was_good_decision') else "❌"
                context += f"{i}. {outcome} {trade['action']} {trade['symbol']} "
                context += f"bei F&G={trade['fear_greed']}: "
                context += f"{trade['outcome_24h']:+.2f}% (24h)\n"
        else:
            context += "Keine ähnlichen Situationen in der Datenbank.\n"

        context += f"""
📈 PATTERN-ANALYSE:

Käufe bei Fear (<30):
  - Trades: {buy_at_fear_stats.get('total_trades', 0)}
  - Erfolgsrate: {buy_at_fear_stats.get('success_rate', 0):.1f}%
  - Avg Return: {buy_at_fear_stats.get('avg_24h_return', 0):+.2f}%

Käufe bei Greed (>70):
  - Trades: {buy_at_greed_stats.get('total_trades', 0)}
  - Erfolgsrate: {buy_at_greed_stats.get('success_rate', 0):.1f}%
  - Avg Return: {buy_at_greed_stats.get('avg_24h_return', 0):+.2f}%

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
        if not self.conn:
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

        with self.conn.cursor() as cur:
            for pattern_name, conditions in patterns_to_check:
                stats = self.get_pattern_stats(conditions)

                if stats.get('total_trades', 0) >= 5:  # Mindestens 5 Samples
                    cur.execute("""
                        INSERT INTO learned_patterns
                            (pattern_name, conditions, success_rate, sample_size, avg_return)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (pattern_name)
                        DO UPDATE SET
                            success_rate = EXCLUDED.success_rate,
                            sample_size = EXCLUDED.sample_size,
                            avg_return = EXCLUDED.avg_return,
                            last_updated = NOW()
                    """, (
                        pattern_name,
                        json.dumps(conditions),
                        stats['success_rate'],
                        stats['total_trades'],
                        stats['avg_24h_return']
                    ))

            self.conn.commit()

    def get_trading_insights(self) -> str:
        """
        Generiert einen Insights-Report basierend auf allen Daten.
        Perfekt für tägliche Telegram-Updates.
        """
        if not self.conn:
            return "Keine Datenbank-Verbindung"

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
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
📊 *TRADING INSIGHTS*

*Gesamt-Performance:*
├ Trades: {stats['total_trades'] or 0}
├ Erfolgsrate: {(stats['good_trades'] or 0) / max(stats['total_trades'] or 1, 1) * 100:.1f}%
├ Avg Return: {stats['avg_return'] or 0:+.2f}%
├ Bester Trade: {stats['best_trade'] or 0:+.2f}%
└ Schlechtester: {stats['worst_trade'] or 0:+.2f}%

*Beste Strategien:*
"""
        for p in best_patterns:
            report += f"• {p['pattern_name']}: {p['success_rate']:.1f}% ({p['sample_size']} Trades)\n"

        return report
