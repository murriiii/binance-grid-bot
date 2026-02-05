# Binance Grid Trading Bot

Ein intelligenter Krypto-Trading-Bot mit Grid-Strategie, AI-Enhancement, Memory-System und selbstlernendem Trading Playbook.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Features

### Core Trading
- **Grid Trading Strategy** - Automatisches Kaufen/Verkaufen in definierten Preisbändern
- **Dynamic Grid Strategy** - ATR-basierte Grid-Abstände, asymmetrische Grids basierend auf Trend
- **AI-Enhanced Decisions** - DeepSeek-Integration für intelligentere Entscheidungen
- **Trading Playbook** - Selbstlernendes "Erfahrungsgedächtnis" das aus Trades lernt
- **Memory System** - PostgreSQL-basiertes RAG-System für historische Muster

### Learning & Optimization
- **Cohort System** - Parallele Strategie-Varianten (Konservativ, Balanced, Aggressiv, Baseline)
- **Cycle Management** - Wöchentliche Trading-Zyklen mit vollständiger Performance-Analyse
- **Bayesian Weight Learning** - Adaptive Signal-Gewichtung via Dirichlet-Distribution
- **A/B Testing Framework** - Statistische Signifikanz-Tests (Welch t-Test, Mann-Whitney U)
- **Regime Detection** - Hidden Markov Model für Markt-Regime (BULL/BEAR/SIDEWAYS)

### Risk Management
- **CVaR Position Sizing** - Conditional Value at Risk basierte Positionsgrößen
- **Stop-Loss Management** - Fixed, Trailing und ATR-basierte Stops
- **Kelly Criterion** - Optimale Positionsgrößen-Berechnung
- **Sharpe/Sortino Ratio** - Risiko-adjustierte Performance-Metriken

### Data Sources
- **Fear & Greed Integration** - Sentiment-basierte Trading-Signale
- **Social Sentiment** - LunarCrush, Reddit, Twitter Tracking
- **ETF Flow Tracking** - Bitcoin/Ethereum ETF Zuflüsse/Abflüsse
- **Token Unlocks** - Supply Events vorausschauend berücksichtigt
- **Whale Alert Tracking** - Überwachung großer Transaktionen
- **Economic Events** - FOMC, CPI, NFP automatisch berücksichtigt

### Technical Analysis
- **Divergence Detection** - RSI, MACD, Stochastic, MFI, OBV Divergenzen
- **Technical Indicators** - RSI, MACD, Bollinger Bands, SMA/EMA
- **Support/Resistance** - Automatische Level-Erkennung

### Infrastructure
- **Comprehensive Logging** - JSON-strukturierte Logs für langfristige Analyse
- **Weekly Analysis Export** - Automatische Reports für Claude Code Optimierung
- **Telegram Notifications** - Echtzeit-Alerts und tägliche Reports

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BINANCE GRID BOT                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Telegram   │◄───│   GridBot    │───►│   Binance    │                   │
│  │   Service    │    │   (Core)     │    │   Client     │                   │
│  └──────────────┘    └──────┬───────┘    └──────────────┘                   │
│                             │                                                │
│      ┌──────────────────────┼──────────────────────┐                        │
│      │                      │                      │                        │
│      ▼                      ▼                      ▼                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Cohort     │    │   Cycle      │    │   Signal     │                   │
│  │   Manager    │    │   Manager    │    │   Analyzer   │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  A/B Testing │    │   Metrics    │    │  Bayesian    │                   │
│  │  Framework   │    │  Calculator  │    │   Weights    │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                             │                                               │
│      ┌──────────────────────┼──────────────────────┐                        │
│      │                      │                      │                        │
│      ▼                      ▼                      ▼                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Regime     │    │  Divergence  │    │   Dynamic    │                   │
│  │   Detector   │    │  Detector    │    │   Grid       │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         DATA PROVIDERS                                  │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ │
│  │  │   Social     │ │   ETF Flow   │ │   Token      │ │   Economic   │   │ │
│  │  │  Sentiment   │ │   Tracker    │ │   Unlocks    │ │   Events     │   │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         RISK MANAGEMENT                                 │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ │
│  │  │   CVaR       │ │   Stop-Loss  │ │   Kelly      │ │   Sharpe/    │   │ │
│  │  │   Sizing     │ │   Manager    │ │   Criterion  │ │   Sortino    │   │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        LEARNING & ANALYSIS                              │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ │
│  │  │   Logging    │ │   Weekly     │ │  Playbook    │ │   Pattern    │   │ │
│  │  │   System     │ │   Export     │ │   History    │ │   Learning   │   │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                             │                                               │
│                             ▼                                               │
│                      ┌──────────────┐                                       │
│                      │  PostgreSQL  │                                       │
│                      │   Database   │                                       │
│                      └──────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cohort System - Paralleles Lernen

Das **Cohort System** ermöglicht paralleles Testen verschiedener Strategien:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PARALLEL COHORTS                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Cohort A: KONSERVATIV        Cohort B: BALANCED                │
│  ├─ $1000 Kapital             ├─ $1000 Kapital                  │
│  ├─ Enge Grids (2%)           ├─ Standard Grids (5%)            │
│  ├─ Hohe Confidence (>0.7)    ├─ Medium Confidence (>0.5)       │
│  └─ Nur bei F&G < 40          └─ Playbook-gesteuert             │
│                                                                  │
│  Cohort C: AGGRESSIV          Cohort D: BASELINE                │
│  ├─ $1000 Kapital             ├─ $1000 Kapital                  │
│  ├─ Weite Grids (8%)          ├─ Keine Änderungen               │
│  ├─ Niedrige Confidence ok    ├─ Woche 1 Strategie              │
│  └─ Auch bei F&G > 60         └─ Kontrolle zum Vergleich        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Vorteile
- 4x mehr Daten pro Woche
- Direkter A/B/C/D Vergleich
- Baseline zeigt ob Änderungen wirklich helfen
- Schnellere statistische Signifikanz

### Cycle Management

Jede Cohort durchläuft wöchentliche Zyklen:
- **Sonntag 00:00**: Neuer Zyklus startet mit frischem Kapital
- **Samstag 23:59**: Zyklus endet, Metriken werden berechnet
- **Automatisch**: Sharpe, Sortino, Kelly, VaR, CVaR pro Zyklus

## Trading Playbook - Das Herzstück

Das **Trading Playbook** ist ein selbstlernendes Erfahrungsgedächtnis:

```
config/TRADING_PLAYBOOK.md          ◄── Aktuelles Playbook
config/playbook_history/            ◄── Alle historischen Versionen
├── playbook_v1_20260205.md
├── playbook_v2_20260212.md
└── ...
```

### Wie es funktioniert

1. **Tägliches Lernen** (21:00): Analysiert neue Trades
2. **Wöchentliches Update** (Sonntag 19:00): Generiert neues Playbook
3. **Pattern-Erkennung**: Identifiziert erfolgreiche/fehlgeschlagene Strategien
4. **AI-Integration**: Playbook wird als Kontext an DeepSeek übergeben

### Was das Playbook enthält

- Fear & Greed Regeln mit Erfolgsraten
- Whale Alert Interpretation
- Economic Event Reaktionen
- Technische Analyse Regeln
- Anti-Patterns (was zu vermeiden ist)
- Erfolgreiche Strategien

## Logging & Analyse

### Strukturierte Logs

```
logs/
├── error.log          # Fehler mit vollem Kontext
├── trade.log          # Jeder Trade mit Marktdaten
├── decision.log       # AI-Entscheidungen mit Reasoning
├── performance.log    # Tägliche/wöchentliche Performance
├── playbook.log       # Playbook-Updates & Regeln
├── api.log            # API-Calls für Rate-Limit Analyse
└── combined.log       # Alles kombiniert
```

Alle Logs sind JSON-formatiert für einfaches Parsen:

```json
{
  "timestamp": "2026-02-05T14:30:00Z",
  "level": "INFO",
  "category": "trade",
  "message": "Trade executed: BUY 0.001 BTCUSDT @ 97500",
  "data": {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": 0.001,
    "price": 97500,
    "context": {"fear_greed": 25, "btc_trend": "bullish"}
  }
}
```

### Weekly Analysis Export

Jeden Samstag 23:00 wird ein Export für Claude Code Analyse erstellt:

```
analysis_exports/
└── week_20260205/
    ├── analysis_export.json    # Strukturierte Daten
    ├── ANALYSIS_REPORT.md      # Lesbare Zusammenfassung
    └── logs/                   # Relevante Log-Ausschnitte
```

Siehe [docs/CLAUDE_ANALYSIS_GUIDE.md](docs/CLAUDE_ANALYSIS_GUIDE.md) für den Analyse-Workflow.

## Projektstruktur

```
binance-grid-bot/
├── src/
│   ├── core/
│   │   ├── bot.py              # Haupt-Bot-Logik
│   │   ├── config.py           # Zentrale Konfiguration
│   │   ├── logging_system.py   # Strukturiertes Logging
│   │   ├── cohort_manager.py   # Parallele Strategie-Varianten (NEU)
│   │   └── cycle_manager.py    # Wöchentliche Zyklen (NEU)
│   ├── api/
│   │   ├── binance_client.py   # Binance API Wrapper
│   │   └── http_client.py      # HTTP Client mit Retry/Caching
│   ├── strategies/
│   │   ├── grid_strategy.py    # Grid-Trading-Logik
│   │   ├── dynamic_grid.py     # ATR-basierte Grids (NEU)
│   │   ├── ai_enhanced.py      # DeepSeek AI + Playbook Integration
│   │   └── portfolio_rebalance.py
│   ├── data/
│   │   ├── market_data.py      # Zentraler Marktdaten-Provider
│   │   ├── sentiment.py        # Fear & Greed, CoinGecko
│   │   ├── social_sentiment.py # LunarCrush, Reddit, Twitter (NEU)
│   │   ├── etf_flows.py        # Bitcoin/ETH ETF Tracking (NEU)
│   │   ├── token_unlocks.py    # Supply Events (NEU)
│   │   ├── whale_alert.py      # Whale-Tracking
│   │   ├── economic_events.py  # FOMC, CPI, NFP Events
│   │   ├── memory.py           # Trading Memory System (RAG)
│   │   ├── playbook.py         # Trading Playbook Generator
│   │   └── fetcher.py          # Historische Daten
│   ├── risk/
│   │   ├── stop_loss.py        # Stop-Loss Management
│   │   └── cvar_sizing.py      # CVaR Position Sizing (NEU)
│   ├── analysis/
│   │   ├── technical_indicators.py
│   │   ├── weekly_export.py    # Wöchentlicher Analyse-Export
│   │   ├── signal_analyzer.py  # Signal-Breakdown Storage (NEU)
│   │   ├── metrics_calculator.py # Sharpe, Sortino, Kelly (NEU)
│   │   ├── regime_detection.py # HMM Markt-Regime (NEU)
│   │   ├── bayesian_weights.py # Adaptive Signal-Gewichte (NEU)
│   │   └── divergence_detector.py # RSI/MACD Divergenzen (NEU)
│   ├── optimization/
│   │   └── ab_testing.py       # A/B Testing Framework (NEU)
│   ├── models/
│   │   └── portfolio.py        # Markowitz, Kelly Criterion
│   ├── notifications/
│   │   ├── telegram_service.py # Zentraler Telegram Service
│   │   ├── telegram_bot.py     # Telegram Bot Commands
│   │   ├── charts.py           # Performance-Charts
│   │   └── ai_assistant.py     # AI Chat Integration
│   └── backtest/
│       └── engine.py           # Backtesting Engine
├── docker/
│   ├── docker-compose.yml      # PostgreSQL, Redis, Bot
│   ├── scheduler.py            # Scheduled Tasks (erweitert)
│   ├── telegram_bot_handler.py # Telegram Command Handler
│   └── init.sql                # Database Schema (erweitert)
├── config/
│   ├── bot_state.json          # Persistenter Bot-State
│   ├── TRADING_PLAYBOOK.md     # Aktuelles Playbook
│   └── playbook_history/       # Playbook-Versionen
├── logs/                       # Strukturierte Logs (gitignored)
├── analysis_exports/           # Wöchentliche Exports (gitignored)
├── docs/
│   └── CLAUDE_ANALYSIS_GUIDE.md
├── main.py                     # Entry Point
├── requirements.txt
├── pyproject.toml              # Linting/Formatting Config
└── .github/
    └── workflows/
        └── ci.yml              # CI/CD Pipeline mit Auto-Release
```

## Datenbank-Schema

### Tabellen-Übersicht

| Tabelle | Beschreibung | Hauptverwendung |
|---------|--------------|-----------------|
| `trades` | Alle ausgeführten Trades | Trade-History, Performance-Analyse |
| `cohorts` | Parallele Strategie-Varianten | A/B/C/D Testing |
| `trading_cycles` | Wöchentliche Trading-Zyklen | Performance pro Zyklus |
| `signal_components` | Signal-Breakdown pro Trade | Signal-Performance Analyse |
| `calculation_snapshots` | Kelly, VaR, CVaR Berechnungen | Risk Tracking |
| `trade_pairs` | BUY/SELL Paare | Echtes P&L Tracking |
| `regime_history` | Markt-Regime Änderungen | Regime-basierte Anpassungen |
| `social_sentiment` | Social Media Tracking | Sentiment Signale |
| `etf_flows` | BTC/ETH ETF Zuflüsse | Institutional Flows |
| `token_unlocks` | Token Supply Events | Supply-basierte Signale |
| `market_snapshots` | Stündliche Marktdaten | Historische Analyse |
| `whale_alerts` | Große Transaktionen | Sentiment-Analyse |
| `economic_events` | Makro-Events (FOMC, CPI) | Event-basiertes Trading |
| `learned_patterns` | Erfolgreiche Muster | AI Context |
| `portfolio_snapshots` | Portfolio-Zustand | Performance-Tracking |
| `stop_loss_orders` | Stop-Loss Tracking | Risk Management |
| `technical_indicators` | Berechnete Indikatoren | Technical Analysis |
| `ai_conversations` | Telegram AI Chat | Context für AI Antworten |

### `trades` - Trade-Historie mit Kontext

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

    -- Market Context (zum Zeitpunkt des Trades)
    fear_greed_at_entry INTEGER,  -- 0-100
    btc_price_at_entry DECIMAL(20, 2),
    market_trend VARCHAR(20),     -- BULL, BEAR, SIDEWAYS

    -- Decision Context
    math_signal JSONB,            -- Markowitz/Portfolio Output
    ai_signal JSONB,              -- DeepSeek Analyse
    reasoning TEXT,               -- Begründung für Trade
    confidence DECIMAL(3, 2),     -- 0.00 - 1.00

    -- Outcome (später aktualisiert für Playbook-Learning)
    outcome_1h DECIMAL(10, 4),    -- Return nach 1h
    outcome_24h DECIMAL(10, 4),   -- Return nach 24h
    outcome_7d DECIMAL(10, 4),    -- Return nach 7d
    was_good_decision BOOLEAN     -- Automatisch berechnet
);
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
| `/playbook` | Aktuelles Trading Playbook anzeigen |
| `/playbook_stats` | Playbook-Statistiken |
| `/playbook_update` | Manuelles Playbook-Update auslösen |
| `/stop` | Bot stoppen |

### Scheduler Tasks

| Task | Zeitplan | Beschreibung |
|------|----------|--------------|
| **Data Collection** | | |
| Market Snapshot | Stündlich | Marktdaten speichern |
| Whale Check | Stündlich | Große Transaktionen |
| Sentiment Check | 4h | F&G Extreme Alert |
| Social Sentiment | 4h | LunarCrush, Reddit, Twitter |
| ETF Flows | 10:00 | Bitcoin/ETH ETF Tracking |
| Token Unlocks | 08:00 | Supply Events |
| Macro Check | 08:00 | FOMC/CPI Events prüfen |
| **Analysis** | | |
| Regime Detection | 4h | HMM Markt-Regime Update |
| Divergence Scan | 2h | RSI/MACD Divergenzen |
| Signal Weights | 22:00 | Bayesian Weight Update |
| Pattern Learning | 21:00 | Tägliche Trade-Analyse |
| **Risk & Performance** | | |
| Stop-Loss Check | 5 Min | Aktive Stops prüfen |
| Outcome Update | 6h | Trade-Ergebnisse aktualisieren |
| System Health | 6h | DB, API, Memory prüfen |
| A/B Test Check | 23:00 | Statistische Signifikanz prüfen |
| **Reports** | | |
| Daily Summary | 20:00 | Portfolio-Report |
| Weekly Export | Sa 23:00 | Analyse-Export erstellen |
| **Weekly Tasks** | | |
| Cycle Management | So 00:00 | Zyklus beenden/starten |
| Weekly Rebalance | So 18:00 | Portfolio-Rebalancing |
| Playbook Update | So 19:00 | Playbook neu generieren |

## Wöchentlicher Optimierungs-Workflow

```bash
# Jeden Sonntag nach dem automatischen Export:
cd /home/murriiii/dev/private/trading/binance-grid-bot
claude

# Claude Code fragen:
"Analyze the latest weekly export in analysis_exports/ and suggest:
1. Playbook rule updates based on trade outcomes
2. Code improvements for common errors
3. Risk management adjustments"
```

Detaillierte Anleitung: [docs/CLAUDE_ANALYSIS_GUIDE.md](docs/CLAUDE_ANALYSIS_GUIDE.md)

## AI-Enhanced Trading

### DeepSeek + Playbook Integration

```python
from src.strategies.ai_enhanced import AITradingEnhancer

ai = AITradingEnhancer()

# Der System-Prompt enthält automatisch das Playbook:
# - Fear & Greed Regeln
# - Historische Erfolgsraten
# - Anti-Patterns zu vermeiden

signal = ai.analyze_news([
    {"title": "Fed signals rate cut", "summary": "..."}
])
print(signal.direction)    # BULLISH
print(signal.confidence)   # 0.75
print(signal.reasoning)    # "Fed dovish → Risk-On, Playbook sagt BUY bei F&G < 40..."
```

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

## CI/CD Pipeline

Die GitHub Actions Pipeline:

1. **Lint & Format**: Ruff checks
2. **Type Check**: MyPy
3. **Tests**: Pytest mit Coverage
4. **Auto-Release**: Bei Version-Bump in pyproject.toml wird automatisch ein GitHub Release erstellt

## Conventional Commits

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

## API Integration

| API | Zweck | Auth |
|-----|-------|------|
| Binance | Trading, Preise | API Key |
| Alternative.me | Fear & Greed Index | Keine |
| CoinGecko | Social Stats, Trending | Keine |
| LunarCrush | Social Sentiment, Galaxy Score | API Key |
| Reddit (PRAW) | Reddit Mentions, Sentiment | OAuth |
| Farside Investors | Bitcoin ETF Flows | Keine |
| SoSoValue | ETH ETF Flows | Keine |
| TokenUnlocks.app | Token Unlock Events | Keine |
| Blockchain.com | Whale Tracking (BTC) | Keine |
| TradingView | Economic Calendar | Keine |
| DeepSeek | AI Analysis | API Key |
| Telegram | Notifications | Bot Token |

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Disclaimer

**Dieses Projekt ist nur für Bildungszwecke gedacht.**

- Keine Finanzberatung
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

Made with Claude Code by [murriiii](https://github.com/murriiii)
