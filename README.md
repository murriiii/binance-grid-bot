# Binance Grid Trading Bot

Ein intelligenter Krypto-Trading-Bot mit Grid-Strategie, AI-Enhancement und Memory-System.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Features

- **Grid Trading Strategy** - Automatisches Kaufen/Verkaufen in definierten Preisbändern
- **AI-Enhanced Decisions** - DeepSeek-Integration für intelligentere Entscheidungen
- **Memory System** - PostgreSQL-basiertes "Gedächtnis" - lernt aus vergangenen Trades
- **Fear & Greed Integration** - Sentiment-basierte Trading-Signale
- **Whale Alert Tracking** - Überwachung großer Transaktionen
- **Economic Events** - FOMC, CPI, NFP automatisch berücksichtigt
- **Stop-Loss Management** - Fixed, Trailing und ATR-basierte Stops
- **Telegram Notifications** - Echtzeit-Alerts und tägliche Reports
- **Technical Analysis** - RSI, MACD, Bollinger Bands, SMA/EMA

## Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BINANCE GRID BOT                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Telegram   │◄───│   GridBot    │───►│   Binance    │          │
│  │   Service    │    │   (Core)     │    │   Client     │          │
│  └──────────────┘    └──────┬───────┘    └──────────────┘          │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                  │
│         │                   │                   │                  │
│         ▼                   ▼                   ▼                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Market     │    │   Memory     │    │  Stop-Loss   │          │
│  │   Data       │    │   System     │    │  Manager     │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                  │
│         ▼                   ▼                   ▼                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  Sentiment   │    │  PostgreSQL  │    │   Risk       │          │
│  │  Aggregator  │    │   Database   │    │   Control    │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                                                          │
│         ├────────────────┬────────────────┐                        │
│         ▼                ▼                ▼                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │
│  │ Fear & Greed │ │ Whale Alert  │ │  Economic    │                │
│  │    Index     │ │   Tracker    │ │   Events     │                │
│  └──────────────┘ └──────────────┘ └──────────────┘                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Projektstruktur

```
binance-grid-bot/
├── src/
│   ├── core/
│   │   ├── bot.py              # Haupt-Bot-Logik
│   │   └── config.py           # Zentrale Konfiguration
│   ├── api/
│   │   ├── binance_client.py   # Binance API Wrapper
│   │   └── http_client.py      # HTTP Client mit Retry/Caching
│   ├── strategies/
│   │   ├── grid_strategy.py    # Grid-Trading-Logik
│   │   ├── ai_enhanced.py      # DeepSeek AI Integration
│   │   └── portfolio_rebalance.py
│   ├── data/
│   │   ├── market_data.py      # Zentraler Marktdaten-Provider
│   │   ├── sentiment.py        # Fear & Greed, CoinGecko
│   │   ├── whale_alert.py      # Whale-Tracking
│   │   ├── economic_events.py  # FOMC, CPI, NFP Events
│   │   ├── memory.py           # Trading Memory System
│   │   └── fetcher.py          # Historische Daten
│   ├── risk/
│   │   └── stop_loss.py        # Stop-Loss Management
│   ├── analysis/
│   │   └── technical_indicators.py
│   ├── models/
│   │   └── portfolio.py        # Markowitz, Kelly Criterion
│   ├── notifications/
│   │   ├── telegram_service.py # Zentraler Telegram Service
│   │   ├── telegram_bot.py     # Telegram Bot Commands
│   │   └── ai_assistant.py     # AI Chat Integration
│   └── backtest/
│       └── engine.py           # Backtesting Engine
├── docker/
│   ├── docker-compose.yml      # PostgreSQL, Redis, Bot
│   ├── scheduler.py            # Scheduled Tasks
│   └── init.sql                # Database Schema
├── config/
│   └── bot_state.json          # Persistenter Bot-State
├── main.py                     # Entry Point
├── requirements.txt
├── pyproject.toml              # Linting/Formatting Config
└── .github/
    └── workflows/
        └── ci.yml              # CI/CD Pipeline
```

## Datenbank-Schema

### Tabellen-Übersicht

| Tabelle | Beschreibung | Hauptverwendung |
|---------|--------------|-----------------|
| `trades` | Alle ausgeführten Trades | Trade-History, Performance-Analyse |
| `market_snapshots` | Stündliche Marktdaten | Historische Analyse, Pattern-Erkennung |
| `whale_alerts` | Große Transaktionen | Sentiment-Analyse, Frühwarnung |
| `economic_events` | Makro-Events (FOMC, CPI) | Event-basiertes Trading |
| `learned_patterns` | Erfolgreiche Muster | AI Context, Strategy Optimization |
| `portfolio_snapshots` | Portfolio-Zustand | Performance-Tracking, Drawdown |
| `stop_loss_orders` | Stop-Loss Tracking | Risk Management |
| `technical_indicators` | Berechnete Indikatoren | Technical Analysis |
| `ai_conversations` | Telegram AI Chat | Context für AI Antworten |

### Detaillierte Tabellen-Strukturen

#### `trades` - Trade-Historie
```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Trade Details
    action VARCHAR(10),       -- BUY, SELL, HOLD
    symbol VARCHAR(20),       -- z.B. BTCUSDT
    price DECIMAL(20, 8),
    quantity DECIMAL(20, 8),
    value_usd DECIMAL(20, 2),
    fee_usd DECIMAL(10, 4),

    -- Market Context (zum Zeitpunkt des Trades)
    fear_greed INTEGER,           -- 0-100
    btc_price DECIMAL(20, 2),
    symbol_24h_change DECIMAL(10, 4),
    market_trend VARCHAR(20),     -- BULL, BEAR, SIDEWAYS
    volatility_regime VARCHAR(20), -- LOW, MEDIUM, HIGH, EXTREME

    -- Decision Context
    math_signal JSONB,            -- Markowitz/Portfolio Output
    ai_signal JSONB,              -- DeepSeek Analyse
    sentiment_data JSONB,         -- Sentiment zum Zeitpunkt
    reasoning TEXT,               -- Begründung für Trade
    confidence DECIMAL(3, 2),     -- 0.00 - 1.00

    -- Outcome (später aktualisiert)
    outcome_1h DECIMAL(10, 4),    -- Return nach 1h
    outcome_24h DECIMAL(10, 4),   -- Return nach 24h
    outcome_7d DECIMAL(10, 4),    -- Return nach 7d
    was_good_decision BOOLEAN     -- Automatisch berechnet
);
```

**Verwendung:**
- Speichert jeden Trade mit vollständigem Kontext
- Ermöglicht Analyse welche Bedingungen zu guten Trades führen
- AI nutzt historische Trades für bessere Entscheidungen

#### `market_snapshots` - Marktdaten-Historie
```sql
CREATE TABLE market_snapshots (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Global Market
    fear_greed INTEGER,
    btc_price DECIMAL(20, 2),
    btc_24h_change DECIMAL(10, 4),
    total_market_cap DECIMAL(30, 2),
    btc_dominance DECIMAL(5, 2),

    -- Top Movers (JSONB)
    top_gainers JSONB,    -- [{symbol, change_pct}, ...]
    top_losers JSONB,
    trending_coins JSONB,

    -- Macro
    etf_flows JSONB,          -- {btc_flow, eth_flow}
    upcoming_events JSONB,

    -- Technical
    btc_rsi DECIMAL(5, 2),
    btc_macd JSONB
);
```

**Verwendung:**
- Stündlicher Snapshot der Marktlage
- Pattern-Erkennung über Zeit
- Kontext für AI-Entscheidungen

#### `whale_alerts` - Große Transaktionen
```sql
CREATE TABLE whale_alerts (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,

    symbol VARCHAR(20),
    amount DECIMAL(30, 8),
    amount_usd DECIMAL(20, 2),
    transaction_type VARCHAR(50),  -- transfer, exchange_deposit, exchange_withdrawal
    from_owner VARCHAR(100),       -- Exchange Name oder "unknown"
    to_owner VARCHAR(100),

    is_significant BOOLEAN,
    potential_impact VARCHAR(20)   -- BULLISH, BEARISH, NEUTRAL
);
```

**Verwendung:**
- Exchange Deposit → Potentieller Verkaufsdruck (BEARISH)
- Exchange Withdrawal → Akkumulation (BULLISH)
- Schwellwerte: BTC > $10M, ETH > $5M, Altcoins > $1M

#### `learned_patterns` - Erfolgreiche Muster
```sql
CREATE TABLE learned_patterns (
    id UUID PRIMARY KEY,
    pattern_name VARCHAR(100) UNIQUE,
    description TEXT,
    conditions JSONB,              -- {"fear_greed_min": 20, "fear_greed_max": 30}

    -- Statistiken
    sample_size INTEGER,
    success_rate DECIMAL(5, 2),
    avg_return_24h DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),

    is_active BOOLEAN,
    last_triggered TIMESTAMPTZ
);
```

**Vordefinierte Patterns:**
- `buy_extreme_fear` - F&G < 25 (historisch gute Kaufgelegenheit)
- `buy_fear` - F&G 25-40
- `sell_extreme_greed` - F&G > 75 (Warnsignal)
- `buy_rsi_oversold` - RSI < 30
- `buy_whale_accumulation` - Nach großen Exchange-Withdrawals

### Views

```sql
-- Performance der letzten 30 Tage
CREATE VIEW v_recent_performance AS
SELECT
    DATE_TRUNC('day', timestamp) as date,
    COUNT(*) as trades,
    SUM(CASE WHEN was_good_decision THEN 1 ELSE 0 END) as winning_trades,
    AVG(outcome_24h) as avg_return
FROM trades
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY date;

-- Aktive Pattern-Performance
CREATE VIEW v_pattern_performance AS
SELECT pattern_name, success_rate, sample_size, avg_return_24h
FROM learned_patterns
WHERE is_active = true AND sample_size >= 10
ORDER BY success_rate DESC;
```

## Installation

### Voraussetzungen

- Python 3.10+
- Docker & Docker Compose
- Binance Account (Testnet oder Live)
- Optional: DeepSeek API Key, Telegram Bot

### Schnellstart

```bash
# Repository klonen
git clone https://github.com/murriiii/binance-grid-bot.git
cd binance-grid-bot

# Virtual Environment erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt

# Environment konfigurieren
cp .env.example .env
# .env mit deinen API Keys bearbeiten

# Docker Services starten (PostgreSQL, Redis)
cd docker
docker-compose up -d

# Bot starten
cd ..
python main.py
```

### Docker Setup (Empfohlen)

```bash
# Alles mit Docker starten
cd docker
docker-compose up -d

# Logs anzeigen
docker logs -f trading-bot

# Status prüfen
docker-compose ps
```

## Konfiguration

### Environment Variables (.env)

```env
# === BINANCE ===
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_SECRET=your_testnet_secret
BINANCE_API_KEY=your_live_key       # Nur für Live-Trading
BINANCE_SECRET=your_live_secret

# === TRADING ===
TRADING_PAIR=BTCUSDT
INVESTMENT_AMOUNT=10                 # USDT
NUM_GRIDS=3
GRID_RANGE_PERCENT=5

# === RISK ===
RISK_TOLERANCE=medium               # low, medium, high
MAX_DAILY_DRAWDOWN=10               # Prozent
ENABLE_STOP_LOSS=true
STOP_LOSS_PERCENT=5

# === AI ===
ENABLE_AI=false
DEEPSEEK_API_KEY=your_deepseek_key

# === NOTIFICATIONS ===
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# === DATABASE ===
DATABASE_URL=postgresql://trading:password@localhost:5433/trading_bot
```

### Config Klassen

Die Konfiguration ist zentral in `src/core/config.py` definiert:

```python
from src.core.config import get_config

config = get_config()
print(config.bot.symbol)           # BTCUSDT
print(config.bot.investment)       # 10.0
print(config.sentiment.extreme_fear_threshold)  # 20
print(config.whale.btc_threshold)  # 10_000_000
```

## Verwendung

### Telegram Commands

| Command | Beschreibung |
|---------|--------------|
| `/status` | Aktueller Bot-Status und Portfolio |
| `/market` | Marktübersicht (F&G, BTC, Trending) |
| `/ta BTCUSDT` | Technical Analysis für Symbol |
| `/whale` | Letzte Whale-Alerts |
| `/events` | Anstehende Makro-Events |
| `/performance` | 30-Tage Performance |
| `/stop` | Bot stoppen |

### Täglicher Report

Der Bot sendet automatisch um 20:00 Uhr einen Tages-Report:

```
📊 TAGES-REPORT 2024-01-15

💰 Portfolio: $1,234.56
📈 Heute: +2.34%

Trades heute: 5
Win Rate: 80%

Markt:
├ Fear & Greed: 45 (Neutral)
├ BTC: $42,500
└ Trend: Bullish

Gute Nacht! 🌙
```

### Scheduler Tasks

| Task | Zeitplan | Beschreibung |
|------|----------|--------------|
| Daily Summary | 20:00 | Portfolio-Report |
| Market Snapshot | Stündlich | Marktdaten speichern |
| Stop-Loss Check | 5 Min | Aktive Stops prüfen |
| Outcome Update | 6h | Trade-Ergebnisse aktualisieren |
| Macro Check | 08:00 | FOMC/CPI Events prüfen |
| Sentiment Check | 4h | F&G Extreme Alert |
| Whale Check | Stündlich | Große Transaktionen |
| Weekly Rebalance | So 18:00 | Portfolio-Rebalancing |

## API Integration

### Verwendete APIs

| API | Zweck | Auth |
|-----|-------|------|
| Binance | Trading, Preise | API Key |
| Alternative.me | Fear & Greed Index | Keine |
| CoinGecko | Social Stats, Trending | Keine |
| Blockchain.com | Whale Tracking (BTC) | Keine |
| TradingView | Economic Calendar | Keine |
| DeepSeek | AI Analysis | API Key |
| Telegram | Notifications | Bot Token |

### HTTP Client

Zentraler HTTP Client mit Retry-Logik:

```python
from src.api.http_client import get_http_client

http = get_http_client()
data = http.get(
    "https://api.example.com/data",
    params={'symbol': 'BTCUSDT'},
    api_type='binance',  # Verwendet Binance-spezifischen Timeout
    timeout=10           # Optional: Override
)
```

## Grid Trading Strategie

### Funktionsweise

```
Upper Price ────────────────────── $105,000
                    │ SELL
Level 4      ──────┬┴──────────── $103,750
                   │ SELL
Level 3      ─────┬┴───────────── $102,500
                  │ SELL
Level 2      ────┬┴────────────── $101,250
                 │
Current Price ───●─────────────── $100,500
                 │
Level 1      ────┴┬────────────── $100,000
                  │ BUY
Lower Price  ─────┴────────────── $95,000
```

1. Bot platziert BUY Orders unter dem aktuellen Preis
2. Bot platziert SELL Orders über dem aktuellen Preis
3. Bei Ausführung einer BUY Order → Neue SELL Order auf nächstem Level
4. Bei Ausführung einer SELL Order → Neue BUY Order auf nächstem Level

### min_qty Validierung

```python
# Jedes Grid-Level wird validiert
if quantity < symbol_info['min_qty']:
    logger.warning(f"Level {price} übersprungen: qty {quantity} < min {min_qty}")
    level.valid = False
```

## AI-Enhanced Trading

### DeepSeek Integration

```python
from src.strategies.ai_enhanced import AITradingEnhancer

ai = AITradingEnhancer()

# News analysieren
signal = ai.analyze_news([
    {"title": "Fed signals rate cut", "summary": "..."}
])
print(signal.direction)    # BULLISH
print(signal.confidence)   # 0.75
print(signal.reasoning)    # "Fed dovish → Risk-On..."

# Anomalie erklären
explanation = ai.explain_anomaly(
    "BTC dropped 5% in 1 hour",
    context={"fear_greed": 75, "whale_activity": "high"}
)
```

### Retry & Fallback

- 3 Retries mit Exponential Backoff
- 30 Sekunden Timeout
- Rate Limit Handling (429)
- Fallback Response bei Ausfall

## Risk Management

### Stop-Loss Typen

| Typ | Beschreibung |
|-----|--------------|
| `FIXED` | Fester Prozentsatz unter Entry |
| `TRAILING` | Folgt dem Preis nach oben |
| `ATR` | Volatilitätsbasiert (14-Perioden ATR) |
| `BREAK_EVEN` | Auf Entry setzen nach X% Gewinn |

### Portfolio Risk

- **Max Daily Drawdown**: Automatischer Stop bei 10% Tagesverlust
- **Position Sizing**: Kelly Criterion für optimale Größe
- **Diversifikation**: Markowitz Mean-Variance Optimization

## Development

### Code Style

```bash
# Linting mit Ruff
ruff check src/

# Formatierung mit Ruff
ruff format src/

# Type Checking
mypy src/
```

### Tests

```bash
# Unit Tests
pytest tests/

# Mit Coverage
pytest --cov=src tests/
```

### Pre-commit Hooks

```bash
# Installation
pip install pre-commit
pre-commit install

# Manuell ausführen
pre-commit run --all-files
```

## Conventional Commits

Das Projekt verwendet [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: Add whale alert integration
fix: Correct min_qty validation
docs: Update README with database schema
refactor: Extract HTTP client to separate module
test: Add tests for grid strategy
chore: Update dependencies
```

### Automatische Versionierung

| Prefix | Version Bump |
|--------|--------------|
| `feat:` | Minor (0.X.0) |
| `fix:` | Patch (0.0.X) |
| `BREAKING CHANGE:` | Major (X.0.0) |

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Disclaimer

**Dieses Projekt ist nur für Bildungszwecke gedacht.**

- Kein Finanzberatung
- Trading birgt Risiken
- Verwende immer zuerst das Testnet
- Investiere nur was du bereit bist zu verlieren

## Contributing

1. Fork das Repository
2. Feature Branch erstellen (`git checkout -b feature/amazing-feature`)
3. Änderungen committen (`git commit -m 'feat: Add amazing feature'`)
4. Branch pushen (`git push origin feature/amazing-feature`)
5. Pull Request öffnen

---

Made with ❤️ by [murriiii](https://github.com/murriiii)
