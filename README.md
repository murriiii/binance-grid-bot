# Binance Grid Trading Bot

Ein regime-adaptiver Krypto-Trading-Bot mit Hybrid-System (HOLD/GRID/CASH), Multi-Coin Trading, AI-Enhancement, Memory-System und selbstlernendem Trading Playbook.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version: 1.8.1](https://img.shields.io/badge/version-1.8.1-green.svg)](https://github.com/murriiii/binance-grid-bot/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Features

### Hybrid Trading System
- **Regime-Adaptive Modes** - Automatischer Wechsel zwischen HOLD (Bull), GRID (Sideways) und CASH (Bear)
- **HMM Regime Detection** - Hidden Markov Model erkennt Markt-Regime (BULL/BEAR/SIDEWAYS)
- **Hysteresis-Schutz** - Verhindert Flip-Flopping: Mindest-Wahrscheinlichkeit (75%), Mindest-Dauer (2 Tage), 24h Cooldown, Safety-Lock nach 2 Transitions/48h
- **Emergency Bear Exit** - Sofortiger Wechsel zu CASH bei Bear-Probability >= 85%
- **6 Transition-Pfade** - Graceful Transitions zwischen allen Modi (GRID<->HOLD, GRID<->CASH, HOLD<->CASH)

### Core Trading
- **Grid Trading Strategy** - Automatisches Kaufen/Verkaufen in definierten Preisbändern
- **Decimal Precision** - Alle Preis-/Mengenberechnungen nutzen `Decimal` statt `float` (keine Binance-Rejections durch Rundungsfehler)
- **Fee-Aware Trading** - Binance Taker-Fees (0.1%) werden bei Sell-Quantities automatisch abgezogen
- **Multi-Coin Trading** - Handel ueber 5-8 Coins mit intelligenter Kapitalverteilung
- **Dynamic Grid Strategy** - ATR-basierte Grid-Abstände, asymmetrische Grids basierend auf Trend
- **AI-Enhanced Decisions** - DeepSeek-Integration für intelligentere Entscheidungen
- **Trading Playbook** - Selbstlernendes "Erfahrungsgedächtnis" das aus Trades lernt
- **Memory System** - PostgreSQL-basiertes RAG-System für historische Muster

### Multi-Coin System
- **Watchlist Management** - 25+ Coins in 6 Kategorien (LARGE_CAP, MID_CAP, L2, DEFI, AI, GAMING)
- **Coin Scanner** - Opportunity Detection mit technischen, Volume und Sentiment-Signalen
- **Portfolio Allocator** - Kelly-basierte Kapitalverteilung mit Risk Constraints
- **Per-Coin Learning** - Optimale Settings pro Coin automatisch erlernen

### Learning & Optimization
- **Cohort System** - Parallele Strategie-Varianten (Konservativ, Balanced, Aggressiv, Baseline)
- **Cycle Management** - Wöchentliche Trading-Zyklen mit vollständiger Performance-Analyse
- **Bayesian Weight Learning** - Adaptive Signal-Gewichtung via Dirichlet-Distribution
- **A/B Testing Framework** - Statistische Signifikanz-Tests (Welch t-Test, Mann-Whitney U)
- **Regime Detection** - Hidden Markov Model für Markt-Regime (BULL/BEAR/SIDEWAYS)

### Risk Management
- **Risk Enforcement Pipeline** - Jede Order wird gegen CVaR-Limits, Allocation-Constraints und Portfolio-Drawdown geprüft
- **Circuit Breaker** - Emergency-Stop bei >10% Flash-Crash zwischen Check-Zyklen
- **CVaR Position Sizing** - Conditional Value at Risk basierte Positionsgrößen
- **Stop-Loss Execution** - Retry-Logik (3 Versuche mit Backoff), Balance-Awareness (tatsaechliche Balance statt Soll-Menge, automatisches Re-Fetch bei INSUFFICIENT_BALANCE), Step-Size-Rounding, Telegram-Alert bei totalem Fehlschlag
- **Stop-Loss Lifecycle** - Zwei-Phasen-Trigger: `update()` erkennt Trigger, `confirm_trigger()` deaktiviert erst nach erfolgreichem Market-Sell, `reactivate()` bei Sell-Fehler
- **Fee-Adjusted Stop-Loss** - Stop-Loss-Quantities werden um Taker-Fee (0.1%) reduziert, verhindert INSUFFICIENT_BALANCE bei Trigger
- **Trailing Distance Fix** - TRAILING-Stops nutzen uebergebenen `stop_percentage` als Trailing-Abstand (HOLD=7%, GRID=5%)
- **Daily Drawdown Reset** - Automatischer Reset der Drawdown-Baseline um Mitternacht (Scheduler-Task + in-tick Detection)
- **Partial-Fill-Handling** - Teilweise gefuellte Orders werden korrekt verarbeitet statt verworfen
- **Downtime-Fill-Recovery** - Bei Neustart werden waehrend der Downtime gefuellte Orders erkannt und Follow-ups platziert
- **Follow-Up Retry** - Fehlgeschlagene Folge-Orders werden mit exponentiellem Backoff (2/5/15/30/60 Min) bis zu 5x wiederholt, kein Telegram-Spam
- **Kelly Criterion** - Optimale Positionsgroessen-Berechnung
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
- **Graceful Shutdown** - SIGTERM-Handling in allen Entry Points (main.py, main_hybrid.py, scheduler.py) fuer sauberes Docker stop/restart
- **Heartbeat Health Checks** - Docker Health Checks via `data/heartbeat` Datei statt HTTP-Endpoint (zentrales `touch_heartbeat()` Utility)
- **Config Validation** - `BotConfig.from_env()` mit `validate()` prueft alle Parameter vor dem Start, `validate_environment()` prueft API-Keys und Abhaengigkeiten
- **Per-Symbol State Files** - Jede GridBot-Instanz im Hybrid-Modus schreibt eigene `grid_state_{SYMBOL}.json` (kein Ueberschreiben bei Multi-Coin)
- **State Corruption Recovery** - Korrupte JSON State-Files werden erkannt und sauber zurueckgesetzt statt Crash
- **Orphan Order Cleanup** - Bei Config-Aenderung (Symbol/Investment) werden alte Orders bei Binance automatisch gecancelt
- **Circuit Breaker Init** - `_last_known_price` wird bei `initialize()` gesetzt (kein falscher Trigger beim ersten Tick)
- **Centralized DB Connections** - Alle Module nutzen DatabaseManager Connection Pool statt eigene Connections
- **Comprehensive Logging** - JSON-strukturierte Logs fuer langfristige Analyse
- **Weekly Analysis Export** - Automatische Reports fuer Claude Code Optimierung
- **Telegram Notifications** - Echtzeit-Alerts und taegliche Reports (TelegramNotifier delegiert an TelegramService Singleton)
- **SingletonMixin Pattern** - Alle Services (DatabaseManager, HTTPClient, WatchlistManager, CoinScanner, TelegramService, MarketDataProvider, ModeManager etc.) nutzen `SingletonMixin` mit automatischem `close()` Lifecycle und `reset_instance()`
- **Atomic State Writes** - Temp-File + Rename Pattern fuer korruptionsfreie State-Persistenz (DecimalEncoder, Temp-File Cleanup bei Fehlern)

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      HYBRID TRADING SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐               │
│  │   Telegram   │◄───│   Hybrid         │───►│   Binance    │               │
│  │   Service    │    │   Orchestrator   │    │   Client     │               │
│  └──────────────┘    └────────┬─────────┘    └──────────────┘               │
│                               │                                              │
│                    ┌──────────┼──────────┐                                   │
│                    │          │          │                                   │
│                    ▼          ▼          ▼                                   │
│              ┌──────────┐ ┌──────┐ ┌──────────┐                             │
│              │   HOLD   │ │ GRID │ │   CASH   │                             │
│              │   Mode   │ │ Mode │ │   Mode   │                             │
│              │ (BULL)   │ │(SIDE)│ │  (BEAR)  │                             │
│              └──────────┘ └──┬───┘ └──────────┘                             │
│                              │                                               │
│                    ┌─────────┴─────────┐                                    │
│                    │                   │                                    │
│                    ▼                   ▼                                    │
│              ┌──────────┐       ┌──────────────┐                            │
│              │   Mode   │       │   GridBot    │                            │
│              │  Manager │       │   (tick)     │                            │
│              │(Hysteres)│       └──────────────┘                            │
│              └──────────┘                                                    │
│                    │                                                         │
│      ┌─────────────┼─────────────┐                                          │
│      ▼             ▼             ▼                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                                    │
│  │  Regime  │ │  Signal  │ │ Bayesian │                                    │
│  │ Detector │ │ Analyzer │ │ Weights  │                                    │
│  └──────────┘ └──────────┘ └──────────┘                                    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         MULTI-COIN SYSTEM                              │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ │
│  │  │  Watchlist   │ │    Coin      │ │  Portfolio   │ │  Per-Coin    │   │ │
│  │  │  Manager     │ │   Scanner    │ │  Allocator   │ │  Learning    │   │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
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

## Hybrid Trading System

Das **Hybrid System** wechselt automatisch zwischen drei Trading-Modi basierend auf dem erkannten Markt-Regime:

```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID TRADING MODES                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  HOLD (BULL)                  GRID (SIDEWAYS)                   │
│  ├─ Market-Buy Allocations    ├─ Grid-Trading pro Symbol         │
│  ├─ 7% Trailing Stop          ├─ ATR-basierte Grid-Abstände     │
│  ├─ Trend reiten              ├─ BUY → SELL → BUY Cycle         │
│  └─ Kein aktives Trading      └─ Bestehende Grid-Logik          │
│                                                                  │
│  CASH (BEAR)                  TRANSITIONS                       │
│  ├─ Offene Orders canceln     ├─ GRID → HOLD: Grids auslaufen   │
│  ├─ Positionen verkaufen      ├─ GRID → CASH: Orders canceln    │
│  ├─ Kapital in USDT           ├─ HOLD → CASH: Enge Trailing     │
│  └─ Nur Regime-Monitoring     ├─ CASH → GRID: Neues Scanning    │
│                                ├─ CASH → HOLD: Market-Buy        │
│                                └─ HOLD → GRID: Grid um Position  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Mode-Management mit Hysteresis

Der ModeManager verhindert Flip-Flopping durch mehrere Schutzmechanismen:

| Regel | Wert | Beschreibung |
|-------|------|--------------|
| Min. Regime-Wahrscheinlichkeit | 75% | Regime muss sicher erkannt sein |
| Min. Regime-Dauer | 2 Tage | Kurzfristige Schwankungen ignorieren |
| Cooldown nach Wechsel | 24h | Keine sofortige Rueckkehr |
| Max. Transitions / 48h | 2 | Safety-Lock auf GRID bei Ueberschreitung (Auto-Reset nach 7 Tagen) |
| Emergency Bear | 85% | Sofortiger CASH-Wechsel ohne Cooldown |

### Regime-zu-Mode Mapping

| Regime | Mode | Constraints |
|--------|------|-------------|
| BULL | HOLD | Aggressive (max 15% pro Coin) |
| SIDEWAYS | GRID | Balanced / Small Portfolio |
| BEAR | CASH | Conservative (min 30% Cash) |
| TRANSITION | Aktuellen Modus beibehalten | Aktuelle Constraints |
| None/Unbekannt | GRID (Fallback) | Balanced |

### Starten

```bash
# Hybrid-Bot (Multi-Coin, Regime-Adaptive)
cd docker && docker compose --profile hybrid up -d

# Klassischer Single-Coin GridBot (weiterhin verfuegbar)
cd docker && docker compose up -d
```

### Konfiguration

```env
# Hybrid-System
HYBRID_INITIAL_MODE=GRID
HYBRID_ENABLE_MODE_SWITCHING=false     # Erstmal nur Multi-Coin GRID testen
HYBRID_TOTAL_INVESTMENT=400
HYBRID_MAX_SYMBOLS=8
HYBRID_MIN_POSITION_USD=10
HYBRID_HOLD_TRAILING_STOP_PCT=7.0
HYBRID_MODE_COOLDOWN_HOURS=24
HYBRID_MIN_REGIME_PROBABILITY=0.75
HYBRID_MIN_REGIME_DURATION_DAYS=2
```

## Multi-Coin Trading System

Das **Multi-Coin System** ermöglicht diversifiziertes Trading ueber mehrere Coins:

```
┌─────────────────────────────────────────────────────────────────┐
│                    COIN UNIVERSE (25+ Coins)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LARGE CAPS (Tier 1)           MID CAPS (Tier 1)                │
│  ├─ BTC, ETH                   ├─ SOL, AVAX, LINK, DOT          │
│  └─ Stabil, hohe Liquidität    └─ Gute Moves, moderate Risiko   │
│                                                                  │
│  L2 ECOSYSTEM                  DEFI                              │
│  ├─ ARB, OP, MATIC             ├─ UNI, AAVE, MKR, CRV, LDO      │
│  └─ Layer 2 Growth             └─ DeFi Blue Chips               │
│                                                                  │
│  AI TOKENS                     GAMING                            │
│  ├─ FET, RNDR, TAO, NEAR       ├─ IMX, GALA, AXS, SAND          │
│  └─ AI/Compute Narrative       └─ Gaming/Metaverse              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Komponenten

| Modul | Funktion |
|-------|----------|
| **WatchlistManager** | Verwaltet Coin-Universe, aktualisiert Marktdaten, prüft Liquidität |
| **CoinScanner** | Scannt nach Opportunities mit 5 Score-Dimensionen |
| **PortfolioAllocator** | Verteilt Kapital mit Kelly-Criterion und Risk Constraints |

### Opportunity Scoring

Der CoinScanner analysiert jeden Coin auf 5 Dimensionen:

```
Total Score = Σ (Score × Weight)

┌────────────────────────────────────────────────────────────────┐
│  Technical (30%)  │ RSI, MACD, Bollinger Bands, Divergenzen   │
│  Volume (20%)     │ Volume Spikes, Anomalien                   │
│  Sentiment (15%)  │ Fear & Greed, Social Media                 │
│  Whale (15%)      │ Exchange In/Outflows, Accumulation         │
│  Momentum (20%)   │ 24h Price Change, Trend Stärke             │
└────────────────────────────────────────────────────────────────┘
```

### Allocation Constraints

```python
# Diversifikation
max_per_coin_pct = 10.0      # Max 10% pro Coin
max_per_category_pct = 30.0  # Max 30% pro Kategorie
min_cash_reserve_pct = 20.0  # Mindestens 20% Cash

# Limits
max_open_positions = 10      # Max gleichzeitige Positionen
min_position_usd = 10.0      # Mindestposition

# Risk-Adjusted Sizing
kelly_fraction = 0.5         # Half-Kelly für konservatives Sizing
```

### Erwartete Datensammlung (3-4 Monate)

Mit 4 Cohorts × 20+ Coins × 24/7 Trading:

| Metrik | Erwartetes Volumen |
|--------|-------------------|
| Trades | ~30.000 |
| Signal-Datenpunkte | ~450.000 |
| Markt-Snapshots | ~45.000 |
| Per-Coin Optimierungen | 20+ Sets |

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
│   │   ├── bot.py              # GridBot mit tick() Methode
│   │   ├── order_manager.py    # OrderManagerMixin (Order-Lifecycle)
│   │   ├── state_manager.py    # StateManagerMixin (State-Persistenz)
│   │   ├── risk_guard.py       # RiskGuardMixin (Risk-Validierung)
│   │   ├── config.py           # Zentrale Konfiguration mit Validierung
│   │   ├── hybrid_orchestrator.py # Hybrid-System Orchestrator
│   │   ├── hybrid_config.py    # Hybrid-System Konfiguration
│   │   ├── mode_manager.py     # Mode-Management mit Hysteresis
│   │   ├── trading_mode.py     # TradingMode Enum, ModeState
│   │   ├── logging_system.py   # Strukturiertes Logging
│   │   ├── cohort_manager.py   # Parallele Strategie-Varianten
│   │   └── cycle_manager.py    # Woechentliche Zyklen
│   ├── api/
│   │   ├── binance_client.py   # Binance API Wrapper
│   │   └── http_client.py      # HTTP Client mit Retry/Caching
│   ├── strategies/
│   │   ├── grid_strategy.py    # Grid-Trading-Logik
│   │   ├── dynamic_grid.py     # ATR-basierte Grids
│   │   ├── ai_enhanced.py      # DeepSeek AI + Playbook Integration
│   │   └── portfolio_rebalance.py
│   ├── data/
│   │   ├── market_data.py      # Zentraler Marktdaten-Provider
│   │   ├── watchlist.py        # Multi-Coin Watchlist Manager
│   │   ├── sentiment.py        # Fear & Greed, CoinGecko
│   │   ├── social_sentiment.py # LunarCrush, Reddit, Twitter
│   │   ├── etf_flows.py        # Bitcoin/ETH ETF Tracking
│   │   ├── token_unlocks.py    # Supply Events
│   │   ├── whale_alert.py      # Whale-Tracking
│   │   ├── economic_events.py  # FOMC, CPI, NFP Events
│   │   ├── memory.py           # Trading Memory System (RAG)
│   │   ├── playbook.py         # Trading Playbook Generator
│   │   └── fetcher.py          # Historische Daten
│   ├── scanner/                # Multi-Coin Opportunity Scanner
│   │   ├── __init__.py
│   │   ├── coin_scanner.py     # Opportunity Detection
│   │   └── opportunity.py      # Opportunity Dataclass
│   ├── portfolio/              # Portfolio Management
│   │   ├── __init__.py
│   │   ├── allocator.py        # Kelly-basierte Kapitalverteilung
│   │   └── constraints.py      # Allocation Rules & Limits
│   ├── risk/
│   │   ├── stop_loss.py        # Stop-Loss Management (Lifecycle: confirm/reactivate)
│   │   ├── stop_loss_executor.py # Retry + Balance-Aware Market-Sell
│   │   └── cvar_sizing.py      # CVaR Position Sizing
│   ├── analysis/
│   │   ├── technical_indicators.py
│   │   ├── weekly_export.py    # Wöchentlicher Analyse-Export
│   │   ├── signal_analyzer.py  # Signal-Breakdown Storage
│   │   ├── metrics_calculator.py # Sharpe, Sortino, Kelly
│   │   ├── regime_detection.py # HMM Markt-Regime
│   │   ├── bayesian_weights.py # Adaptive Signal-Gewichte
│   │   └── divergence_detector.py # RSI/MACD Divergenzen
│   ├── optimization/
│   │   └── ab_testing.py       # A/B Testing Framework
│   ├── models/
│   │   └── portfolio.py        # Markowitz, Kelly Criterion
│   ├── notifications/
│   │   ├── telegram_service.py # Zentraler Telegram Service
│   │   ├── telegram_bot.py     # Telegram Bot Commands
│   │   ├── charts.py           # Performance-Charts
│   │   └── ai_assistant.py     # AI Chat Integration
│   ├── utils/
│   │   ├── singleton.py        # SingletonMixin Basisklasse (alle Services)
│   │   ├── heartbeat.py        # Docker Health-Check Heartbeat
│   │   └── task_lock.py        # Thread-safe Task-Locking
│   ├── tasks/                  # Domain-spezifische Scheduler Tasks
│   │   ├── base.py             # Shared Infra (DB-Connection via Pool)
│   │   ├── system_tasks.py     # Health, Stops, Drawdown Reset
│   │   ├── analysis_tasks.py   # Regime, Weights, Divergence
│   │   ├── market_tasks.py     # Snapshots, Sentiment
│   │   ├── data_tasks.py       # ETF, Social, Whale, Unlocks
│   │   ├── hybrid_tasks.py     # Mode Eval, Rebalance
│   │   ├── portfolio_tasks.py  # Watchlist, Scan, Allocation
│   │   ├── cycle_tasks.py      # Cycle Mgmt, Weekly Rebalance
│   │   └── reporting_tasks.py  # Summary, Export, Playbook
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
├── main.py                     # Entry Point (Single-Coin GridBot)
├── main_hybrid.py              # Entry Point (Hybrid Multi-Coin)
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
| **Multi-Coin Tabellen** | | |
| `watchlist` | Coin-Universe mit Kategorien | Multi-Coin Trading |
| `coin_performance` | Per-Coin Performance Metriken | Coin-spezifische Optimierung |
| `cohort_allocations` | Positionen pro Cohort | Portfolio Management |
| `opportunities` | Scanner-Ergebnisse | Opportunity Tracking |
| `trading_mode_history` | Mode-Wechsel History | Hybrid-System Tracking |
| **Data Provider Tabellen** | | |
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

### Multi-Coin Views

| View | Beschreibung |
|------|--------------|
| `v_coin_rankings` | Coins sortiert nach Performance (Win Rate × Trades) |
| `v_active_positions` | Alle aktiven Positionen mit P&L |
| `v_category_performance` | Performance aggregiert nach Kategorie |

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
docker compose up -d

# Bot starten
cd ..
python main.py
```

### Docker Setup (Empfohlen)

```bash
# Klassischer Single-Coin GridBot
cd docker
docker compose up -d

# ODER: Hybrid Multi-Coin System
docker compose --profile hybrid up -d

# Logs anzeigen
docker logs -f trading-bot       # Single-Coin
docker logs -f hybrid-bot        # Hybrid

# Status pruefen
docker compose ps
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
| **Hybrid-System Tasks** | | |
| Mode Evaluation | Stuendlich | Regime auswerten, Mode-Wechsel pruefen |
| Hybrid Rebalance | 6h | Allocation-Drift pruefen (>5%) |
| **Multi-Coin Tasks** | | |
| Watchlist Update | 30 Min | Marktdaten fuer alle Coins aktualisieren |
| Opportunity Scan | 2h | Alle Coins nach Opportunities scannen |
| Portfolio Rebalance | 06:00 | Allocation pruefen und anpassen |
| Coin Performance | 21:30 | Per-Coin Metriken aktualisieren |
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
| Stop-Loss Check | 5 Min | Aktive Stops pruefen + Market-Sell mit Retry |
| Drawdown Reset | 00:00 | Daily Drawdown Baseline zuruecksetzen |
| Outcome Update | 6h | Trade-Ergebnisse aktualisieren |
| System Health | 6h | DB, API, Memory pruefen |
| A/B Test Check | 23:00 | Statistische Signifikanz pruefen |
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

### Order Risk Pipeline

Jede Order (initial + follow-up) durchlaeuft vor Platzierung:

1. **Portfolio Drawdown Check** - Handel gestoppt bei >10% Tagesverlust (Baseline wird taeglich um Mitternacht zurueckgesetzt)
2. **CVaR Max Position** - Orderwert darf CVaR-Limit nicht ueberschreiten
3. **Allocation Constraints** - Cash-Reserve und Exposure-Limits eingehalten
4. **Circuit Breaker** - Emergency-Stop bei Flash-Crash (>10% Drop pro Check-Zyklus)

Bei Fehler der Risk-Module: Graceful Degradation (Order wird zugelassen).

### Stop-Loss Execution Pipeline

Bei Stop-Loss-Trigger durchlaeuft die Ausfuehrung:

1. **Balance Check** - Tatsaechliche Balance via API abfragen, `min(intended, actual)` verkaufen
2. **Step-Size Rounding** - Quantity auf Binance `step_size` runden
3. **Retry Loop** - 3 Versuche mit Backoff (2s, 5s, 10s). Bei INSUFFICIENT_BALANCE: Balance erneut abfragen und mit reduzierter Menge wiederholen
4. **Confirm/Reactivate** - Bei Erfolg: `confirm_trigger()` deaktiviert Stop. Bei Fehler: `reactivate()` haelt Stop aktiv fuer naechsten Tick
5. **Critical Alert** - Bei totalem Fehlschlag: CRITICAL Log + Telegram "Manual sell needed"

### Portfolio Risk

- **Max Daily Drawdown**: Automatischer Stop bei 10% Tagesverlust
- **Position Sizing**: Kelly Criterion fuer optimale Groesse
- **Diversifikation**: Markowitz Mean-Variance Optimization
- **Stop-Loss Persistenz**: Stops werden in PostgreSQL gespeichert und nach Neustart automatisch wiederhergestellt (Reconciliation bei `load_state()`)

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
