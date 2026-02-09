<h1 align="center">
  <br>
  AI-Enhanced Crypto Grid Trading Bot
  <br>
</h1>

<p align="center">
  <b>A regime-adaptive cryptocurrency trading system that autonomously switches between HOLD, GRID, and CASH modes using Hidden Markov Models, runs 6 parallel strategy cohorts, and continuously learns from its own trades.</b>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/></a>
  <a href="https://github.com/murriiii/binance-grid-bot/releases"><img src="https://img.shields.io/badge/version-1.20.0-green?style=flat-square" alt="Version"/></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License"/></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code_style-ruff-000000?style=flat-square" alt="Ruff"/></a>
  <img src="https://img.shields.io/badge/tests-1089_passed-brightgreen?style=flat-square" alt="Tests"/>
  <img src="https://img.shields.io/badge/coverage-60%25-yellowgreen?style=flat-square" alt="Coverage"/>
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-cohort-system--6-parallel-bots">Cohorts</a> •
  <a href="#-3-tier-portfolio-management">Portfolio</a> •
  <a href="#-hybrid-trading-system">Hybrid System</a> •
  <a href="#-multi-coin-trading-system">Multi-Coin</a> •
  <a href="#-installation">Install</a> •
  <a href="#-telegram-commands">Telegram</a> •
  <a href="#-development">Dev</a>
</p>

---

## ✨ Features

### Hybrid Trading System
- **Regime-Adaptive Modes** — Automatic switching between HOLD (Bull), GRID (Sideways) and CASH (Bear)
- **HMM Regime Detection** — Hidden Markov Model identifies market regimes (BULL/BEAR/SIDEWAYS)
- **Hysteresis Protection** — Prevents flip-flopping: minimum probability (75%), minimum duration (2 days), 24h cooldown, safety lock after 2 transitions/48h
- **Emergency Bear Exit** — Immediate switch to CASH when bear probability >= 85%
- **6 Transition Paths** — Graceful transitions between all modes (GRID↔HOLD, GRID↔CASH, HOLD↔CASH)

### Core Trading
- **Grid Trading Strategy** — Automated buying/selling within defined price bands
- **Decimal Precision** — All price/quantity calculations use `Decimal` instead of `float` (zero Binance rejections from rounding errors)
- **Fee-Aware Trading** — Binance taker fees (0.1%) automatically deducted from sell quantities, fee-aware grid spacing warning for grids that are too tight
- **Multi-Coin Trading** — Trade across 2-3 coins per cohort with intelligent capital distribution
- **Dynamic Grid Strategy** — ATR-based grid ranges per symbol (Range-Bridge: DynamicGridStrategy calculates range, GridStrategy maintains Decimal precision), auto grid rebuild on price drift (30 min check)
- **Dynamic Grid Count** — Volatility-based grid count (LOW=7, NORMAL=10, HIGH=12, EXTREME=15) instead of static configuration
- **Slippage Tracking** — Expected vs. filled price tracking in basis points per trade
- **AI-Enhanced Decisions** — DeepSeek integration for smarter trading decisions
- **Trading Playbook** — Self-learning "experience memory" that learns from trades
- **Memory System** — PostgreSQL-based RAG system with multi-dimensional similarity scoring (Gaussian F&G Decay, Regime-Match, Symbol-Match, Temporal Decay)

### Multi-Coin System
- **Watchlist Management** — 35+ coins across 7 categories (LARGE_CAP, MID_CAP, L2, DEFI, AI, GAMING, MEME)
- **Coin Scanner** — Opportunity detection with technical, volume and sentiment signals
- **Portfolio Allocator** — Kelly-based capital distribution with risk constraints
- **Category-Based Filtering** — Cohorts can be restricted to specific coin categories (`allowed_categories`)
- **Symbol Exclusion** — Each cohort trades unique coins (no overlap)
- **Pre-Feasibility Filter** — Coins are checked before allocation whether min_position_usd is achievable
- **Per-Coin Learning** — Optimal settings per coin learned automatically

### 3-Tier Portfolio Management
- **Cash Reserve Tier** — Configurable USDT safety buffer (default 10%)
- **Index Holdings Tier** — ETF-like buy-and-hold of CMC Top 20 by market cap, quarterly rebalance, 15% trailing stops
- **Trading Tier** — Wrapper around CohortOrchestrator, scales cohorts by available capital
- **Profit Redistribution** — Weekly profit redistribution when tier drift > 3%
- **AI Portfolio Optimizer** — Monthly DeepSeek recommendations for optimal tier weights with guard rails (learning mode for first 3 months)
- **Production Validator** — 9 criteria for go-live (trades, Sharpe, drawdown, win rate, signal accuracy, etc.)
- **Deployment Phases** — Gradual capital ramp-up: Paper → Alpha ($1K) → Beta ($3K) → Production ($5K+)
- **Feature Flag** — `PORTFOLIO_MANAGER=true` enables 3-tier system, otherwise falls back to CohortOrchestrator

### Learning & Optimization
- **Cohort System** — 6 parallel HybridOrchestrator instances each with $1,000 own capital (Conservative, Balanced, Aggressive, Baseline, DeFi Explorer, Meme Hunter)
- **AI Learning Loop** — Signal correctness (`was_correct`), trade decision quality (`was_good_decision`), multi-timeframe outcomes (1h/4h/24h/7d)
- **Signal Accuracy in Playbook** — Top signals by reliability, regime-stratified rules (BULL/BEAR/SIDEWAYS)
- **Cycle Management** — Weekly trading cycles with complete performance analysis
- **Bayesian Weight Learning** — Adaptive signal weighting via Dirichlet distribution
- **A/B Testing Framework** — Statistical significance tests (Welch t-test, Mann-Whitney U)
- **Regime Detection** — Hidden Markov Model for market regimes (BULL/BEAR/SIDEWAYS)

### Risk Management
- **Risk Enforcement Pipeline** — Every order validated against CVaR limits, allocation constraints and portfolio drawdown
- **Circuit Breaker** — Emergency stop on >10% flash crash between check cycles
- **CVaR Position Sizing** — Conditional Value at Risk based position sizes
- **Stop-Loss Execution** — Retry logic (3 attempts with backoff), balance awareness (actual balance instead of target amount, auto re-fetch on INSUFFICIENT_BALANCE), step-size rounding, Telegram alert on total failure
- **Stop-Loss Lifecycle** — Two-phase trigger: `update()` detects trigger, `confirm_trigger()` deactivates only after successful market sell, `reactivate()` on sell failure
- **Fee-Adjusted Stop-Loss** — Stop-loss quantities reduced by taker fee (0.1%), prevents INSUFFICIENT_BALANCE on trigger
- **Trailing Distance Fix** — TRAILING stops use passed `stop_percentage` as trailing distance (HOLD=7%, GRID=5%)
- **Daily Drawdown Reset** — Automatic drawdown baseline reset at midnight (scheduler task + in-tick detection)
- **Partial Fill Handling** — Partially filled orders processed correctly instead of discarded
- **Downtime Fill Recovery** — On restart, orders filled during downtime are detected and follow-ups placed
- **Follow-Up Retry** — Failed follow-up orders retried with exponential backoff (2/5/15/30/60 min) up to 5x, no Telegram spam
- **Kelly Criterion** — Optimal position size calculation
- **Sharpe/Sortino Ratio** — Risk-adjusted performance metrics
- **Signal Breakdown** — 9-signal composite (F&G, RSI, MACD, Trend, Volume, Whale, Sentiment, Macro, AI) per trade fill stored in DB with AI signal validation (Enum, Confidence Clamping, Semantic Consistency)
- **Metrics Snapshots** — Daily Sharpe/CVaR/Kelly snapshots in `calculation_snapshots` table
- **Data Retention** — Automatic cleanup of old data (8 tables, configurable retention: 30-180 days)

### Data Sources
- **Fear & Greed Integration** — Sentiment-based trading signals
- **Social Sentiment** — LunarCrush, Reddit, Twitter with source-availability dampening and divergence detection
- **ETF Flow Tracking** — Bitcoin/Ethereum ETF inflows/outflows
- **Token Unlocks** — Supply events considered proactively
- **Whale Alert Tracking** — Monitoring large transactions
- **Economic Events** — FOMC, CPI, NFP automatically considered (DB persistence with deduplication)
- **Funding Rate Signal** — Binance Futures funding rate (5min cache, bearish at >0.05%, bullish at <-0.05%)
- **Correlation Matrix** — 60-day Pearson correlation between coin pairs, allocator penalty for highly correlated positions

### Technical Analysis
- **Divergence Detection** — RSI, MACD, Stochastic, MFI, OBV divergences
- **Technical Indicators** — RSI, MACD, Bollinger Bands, SMA/EMA
- **Support/Resistance** — Automatic level detection

### Infrastructure
- **Graceful Shutdown** — SIGTERM handling in all entry points (main.py, main_hybrid.py, scheduler.py) for clean Docker stop/restart
- **Heartbeat Health Checks** — Docker health checks via `data/heartbeat` file instead of HTTP endpoint (central `touch_heartbeat()` utility)
- **Config Validation** — `BotConfig.from_env()` with `validate()` checks all parameters before start, `validate_environment()` checks API keys and dependencies
- **Per-Symbol State Files** — Each GridBot instance in hybrid mode writes its own `grid_state_{SYMBOL}.json` (no overwriting in multi-coin)
- **State Corruption Recovery** — Corrupt JSON state files detected and cleanly reset instead of crash
- **Orphan Order Cleanup** — On config change (symbol/investment), old orders at Binance automatically canceled
- **Circuit Breaker Init** — `_last_known_price` set at `initialize()` (no false trigger on first tick)
- **Centralized DB Connections** — All modules use DatabaseManager connection pool instead of own connections
- **Comprehensive Logging** — JSON-structured logs for long-term analysis
- **Weekly Analysis Export** — Automatic reports for Claude Code optimization
- **Telegram Dashboard** — Emoji-based portfolio dashboard with compact price formatting, status emojis and per-cohort P&L
- **Telegram Notifications** — Real-time alerts and daily reports (TelegramNotifier delegates to TelegramService singleton)
- **SingletonMixin Pattern** — All services (DatabaseManager, HTTPClient, WatchlistManager, CoinScanner, TelegramService, MarketDataProvider etc.) use `SingletonMixin` with automatic `close()` lifecycle and `reset_instance()`. ModeManager is not a singleton (each cohort orchestrator has its own instance).
- **Atomic State Writes** — Temp-file + rename pattern for corruption-free state persistence (DecimalEncoder, temp-file cleanup on errors)
- **SchedulerConfig** — Scheduler times and intervals configurable via `SchedulerConfig` (`get_config().scheduler`) instead of hardcoded values

---

## 🏗 Architecture

```mermaid
graph TB
    PM[Portfolio Manager] --> CT[Cash Tier<br/>10% USDT]
    PM --> IT[Index Tier<br/>65% CMC Top 20]
    PM --> TT[Trading Tier<br/>25%]

    TT --> CO[Cohort Orchestrator]

    CO --> H1[Conservative]
    CO --> H2[Balanced]
    CO --> H3[Aggressive]
    CO --> H4[Baseline]
    CO --> H5[DeFi Explorer]
    CO --> H6[Meme Hunter]

    H1 & H2 & H3 & H4 & H5 & H6 --> MM[Mode Manager<br/>HMM Regime Detection]

    MM -->|Bull| HOLD[HOLD Mode<br/>Trailing Stops]
    MM -->|Sideways| GRID[GRID Mode<br/>ATR-based Grids]
    MM -->|Bear| CASH[CASH Mode<br/>Capital Preservation]

    GRID --> GB[GridBot.tick<br/>per symbol]

    subgraph Data Layer
        SA[Signal Analyzer<br/>9 signals] --> SC[Signal Components DB]
        MC[Market Data] --> SA
        WA[Whale Alerts] --> SA
        SS[Social Sentiment] --> SA
        EE[Economic Events] --> SA
    end

    GB --> SA
    HOLD --> SA

    subgraph Learning
        PB[Trading Playbook]
        BW[Bayesian Weights]
        RM[RAG Memory]
    end

    SA --> PB & BW & RM

    subgraph Risk
        CV[CVaR Sizing]
        SL[Stop-Loss Manager]
        KC[Kelly Criterion]
        SR[Sharpe / Sortino]
    end

    subgraph Multi-Coin
        WL[Watchlist Manager]
        CS[Coin Scanner]
        PA[Portfolio Allocator]
        PL[Per-Coin Learning]
    end

    style PM fill:#1a1b27,stroke:#70a5fd,color:#fff
    style CO fill:#1a1b27,stroke:#70a5fd,color:#fff
    style MM fill:#1a1b27,stroke:#bb9af7,color:#fff
    style HOLD fill:#9ece6a,stroke:#1a1b27,color:#1a1b27
    style GRID fill:#e0af68,stroke:#1a1b27,color:#1a1b27
    style CASH fill:#f7768e,stroke:#1a1b27,color:#1a1b27
```

---

## 🤖 Cohort System — 6 Parallel Bots

The **Cohort System** runs 6 independent `HybridOrchestrator` instances in parallel, each with its own strategy, capital and coins. All share one Binance testnet account; capital tracking is virtual per cohort.

```mermaid
graph LR
    CO[Cohort Orchestrator] --> C1["🛡️ Conservative<br/>$1,000 · Tight grids 2%<br/>High confidence >0.7<br/>Max 3 coins (LARGE_CAP)"]
    CO --> C2["⚖️ Balanced<br/>$1,000 · Standard grids 5%<br/>Medium confidence >0.5<br/>Max 3 coins"]
    CO --> C3["⚔️ Aggressive<br/>$1,000 · Wide grids 8%<br/>Low confidence >0.3<br/>Max 3 coins (all categories)"]
    CO --> C4["🧊 Baseline<br/>$1,000 · Standard grids 5%<br/>Frozen (no adjustments)<br/>Control group"]
    CO --> C5["🔬 DeFi Explorer<br/>$1,000 · Wide grids 10%<br/>Confidence >0.3<br/>DEFI + AI coins only"]
    CO --> C6["🎰 Meme Hunter<br/>$1,000 · Very wide grids 15%<br/>Confidence >0.2<br/>MEME coins only"]

    style CO fill:#1a1b27,stroke:#70a5fd,color:#fff
```

### Architecture
- **`CohortOrchestrator`** (`src/core/cohort_orchestrator.py`) loads cohorts from DB via `CohortManager`, creates a `HybridConfig.from_cohort()` and its own `HybridOrchestrator` per cohort
- **Isolated State Files**: `hybrid_state_{cohort}.json` + `grid_state_{symbol}_{cohort}.json`
- **Shared BinanceClient**: All cohorts use the same testnet client
- **ModeManager**: Not a singleton — each orchestrator has its own instance
- **Symbol Exclusion**: Each cohort trades unique coins — no overlap between cohorts
- **Category Override**: `allowed_categories` in CohortConfig restricts coins to specific categories (e.g., MEME only for meme_hunter)
- **Risk-Mapped Presets**: `risk_tolerance` mapped to constraint presets (low→conservative, medium→balanced, high→aggressive)

### Benefits
- 6x more data per week
- Direct comparison: Conservative vs Aggressive vs Small-Cap
- Baseline shows whether changes actually help
- Specialized bots for DeFi/AI and meme coins
- Faster statistical significance

### Cycle Management
Each cohort runs weekly cycles:
- **Sunday 00:00**: New cycle starts with fresh capital
- **Saturday 23:59**: Cycle ends, metrics computed
- **Automatic**: Sharpe, Sortino, Kelly, VaR, CVaR per cycle

---

## 💰 3-Tier Portfolio Management

The **3-Tier Portfolio System** (`PORTFOLIO_MANAGER=true`) manages capital strategically across three tiers:

```mermaid
graph TB
    PM[Portfolio Manager<br/>AI-Optimized 3-Tier Management] --> T1
    PM --> T2
    PM --> T3

    T1["💵 Tier 1: Cash Reserve (10%)<br/>Always USDT<br/>Safety buffer<br/>Underfunded <2% → Alert<br/>Overfunded >5% → Redistribute"]
    T2["📊 Tier 2: Index Holdings (65%)<br/>CMC Top 20 by Market Cap<br/>Quarterly Rebalance (90 days)<br/>15% Trailing Stops<br/>Max 30% per coin (BTC cap)<br/>Stablecoins excluded"]
    T3["🤖 Tier 3: Hybrid Trading (25%)<br/>CohortOrchestrator (6 bots)<br/>Capital budget from manager<br/>Cohort count scales with capital"]

    PM --> PRE["Profit Redistribution Engine<br/>Weekly (Sun 17:00)<br/>Rebalance when tier drift >3%<br/>Priority: Cash → Index → Trading<br/>Min $10 per transfer"]
    PM --> AI["AI Portfolio Optimizer<br/>Monthly (DeepSeek)<br/>Guard Rails: Cash 5-20%, Index 40-80%, Trading 10-40%<br/>Max 5pp shift per recommendation<br/>Auto-apply after 3+ recs at confidence >0.8"]

    style PM fill:#1a1b27,stroke:#70a5fd,color:#fff
    style T1 fill:#9ece6a,stroke:#1a1b27,color:#1a1b27
    style T2 fill:#7aa2f7,stroke:#1a1b27,color:#fff
    style T3 fill:#e0af68,stroke:#1a1b27,color:#1a1b27
```

### Deployment Phases

| Phase | Capital | Cohorts | Validation |
|-------|---------|---------|------------|
| Paper | $10,000 (virtual) | 6 | Not required |
| Alpha | $1,000 | 2 | ProductionValidator must pass |
| Beta | $3,000 | 4 | ProductionValidator must pass |
| Production | $5,000+ | 6 | ProductionValidator must pass |

### Production Validation (9 Criteria)

| Criterion | Threshold |
|-----------|-----------|
| Minimum Trades | 5,000 closed trade pairs |
| Sharpe Ratio | >= 0.5 (annualized) |
| Playbook Version | >= v4 |
| Signal Evaluations | >= 1,000 (`was_correct` populated) |
| Regime Transitions | >= 2 (BULL→BEAR or vice versa) |
| Max Drawdown | < 15% (no tier) |
| Win Rate | >= 45% |
| Index Tracking Error | < 5pp |
| AI Recommendations | >= 2 logged |

---

## 🔄 Hybrid Trading System

The **Hybrid System** automatically switches between three trading modes based on detected market regime:

```mermaid
graph LR
    subgraph Modes
        HOLD["🟢 HOLD (BULL)<br/>Market-buy allocations<br/>7% trailing stop<br/>Ride the trend<br/>No active trading"]
        GRID["🟡 GRID (SIDEWAYS)<br/>Grid trading per symbol<br/>ATR-based grid spacing<br/>BUY → SELL → BUY cycle<br/>Existing grid logic"]
        CASH["🔴 CASH (BEAR)<br/>Cancel open orders<br/>Sell positions<br/>Capital in USDT<br/>Regime monitoring only"]
    end

    GRID -->|"Bull detected"| HOLD
    HOLD -->|"Sideways detected"| GRID
    GRID -->|"Bear detected"| CASH
    CASH -->|"Sideways detected"| GRID
    HOLD -->|"Bear detected"| CASH
    CASH -->|"Bull detected"| HOLD

    style HOLD fill:#9ece6a,stroke:#1a1b27,color:#1a1b27
    style GRID fill:#e0af68,stroke:#1a1b27,color:#1a1b27
    style CASH fill:#f7768e,stroke:#1a1b27,color:#1a1b27
```

### Transition Details
- **GRID → HOLD**: Let grids expire
- **GRID → CASH**: Cancel orders
- **HOLD → CASH**: Tighten trailing stops
- **CASH → GRID**: New scanning
- **CASH → HOLD**: Market-buy
- **HOLD → GRID**: Build grid around position

### Mode Management with Hysteresis

The ModeManager prevents flip-flopping through multiple protection mechanisms:

| Rule | Value | Description |
|------|-------|-------------|
| Min. Regime Probability | 75% | Regime must be confidently detected |
| Min. Regime Duration | 2 days | Ignore short-term fluctuations |
| Cooldown After Switch | 24h | No immediate reversal |
| Max. Transitions / 48h | 2 | Safety lock to GRID on violation (auto-reset after 7 days) |
| Emergency Bear | 85% | Immediate CASH switch without cooldown |

### Regime-to-Mode Mapping

| Regime | Mode | Constraints |
|--------|------|-------------|
| BULL | HOLD | Aggressive (max 15% per coin) |
| SIDEWAYS | GRID | Balanced / Small Portfolio |
| BEAR | CASH | Conservative (min 30% cash) |
| TRANSITION | Keep current mode | Current constraints |
| None/Unknown | GRID (fallback) | Balanced |

### Starting

```bash
# Hybrid bot (multi-coin, regime-adaptive)
cd docker && docker compose --profile hybrid up -d

# Classic single-coin GridBot (still available)
cd docker && docker compose up -d
```

### Configuration

```env
# Hybrid System
HYBRID_INITIAL_MODE=GRID
HYBRID_ENABLE_MODE_SWITCHING=false     # First test multi-coin GRID only
HYBRID_TOTAL_INVESTMENT=400         # Overridden by cohort system ($1000/cohort)
HYBRID_MAX_SYMBOLS=8                # Set to 3 per cohort by from_cohort()
HYBRID_MIN_POSITION_USD=10
HYBRID_HOLD_TRAILING_STOP_PCT=7.0
HYBRID_MODE_COOLDOWN_HOURS=24
HYBRID_MIN_REGIME_PROBABILITY=0.75
HYBRID_MIN_REGIME_DURATION_DAYS=2
```

---

## 🌐 Multi-Coin Trading System

The **Multi-Coin System** enables diversified trading across multiple coins:

```mermaid
graph TB
    subgraph "Coin Universe (35+ Coins)"
        LC["💎 LARGE CAPS<br/>BTC, ETH<br/>Stable, high liquidity"]
        MC["🔷 MID CAPS<br/>SOL, AVAX, LINK, DOT<br/>Good moves, moderate risk"]
        L2["🔗 L2 ECOSYSTEM<br/>ARB, OP, MATIC<br/>Layer 2 growth"]
        DF["🏦 DEFI<br/>UNI, AAVE, MKR, CRV, LDO<br/>DYDX, INJ, ENA, PENDLE<br/>DeFi blue chips + explorer"]
        AI["🧠 AI TOKENS<br/>FET, RNDR, TAO, NEAR<br/>RENDER, WLD<br/>AI/Compute narrative"]
        GM["🎮 GAMING<br/>IMX, GALA, AXS, SAND<br/>Gaming/Metaverse"]
        MM["🐸 MEME<br/>DOGE, SHIB, PEPE, FLOKI, BONK, WIF<br/>Highly volatile, wide grids 15%"]
    end

    style LC fill:#f7768e,stroke:#1a1b27,color:#fff
    style MC fill:#bb9af7,stroke:#1a1b27,color:#fff
    style L2 fill:#7aa2f7,stroke:#1a1b27,color:#fff
    style DF fill:#73daca,stroke:#1a1b27,color:#1a1b27
    style AI fill:#e0af68,stroke:#1a1b27,color:#1a1b27
    style GM fill:#9ece6a,stroke:#1a1b27,color:#1a1b27
    style MM fill:#ff9e64,stroke:#1a1b27,color:#1a1b27
```

### Components

| Module | Function |
|--------|----------|
| **WatchlistManager** | Manages coin universe, updates market data, checks liquidity |
| **CoinScanner** | Scans for opportunities across 5 score dimensions |
| **PortfolioAllocator** | Distributes capital with Kelly Criterion and risk constraints |

### Opportunity Scoring

The CoinScanner analyzes each coin across 5 dimensions:

```
Total Score = Σ (Score × Weight)

┌────────────────────────────────────────────────────────────────┐
│  Technical (30%)  │ RSI, MACD, Bollinger Bands, Divergences    │
│  Volume (20%)     │ Volume spikes, anomalies                   │
│  Sentiment (15%)  │ Fear & Greed, social media                 │
│  Whale (15%)      │ Exchange in/outflows, accumulation         │
│  Momentum (20%)   │ 24h price change, trend strength           │
└────────────────────────────────────────────────────────────────┘
```

### Allocation Constraints

```python
# Diversification
max_per_coin_pct = 10.0      # Max 10% per coin
max_per_category_pct = 30.0  # Max 30% per category
min_cash_reserve_pct = 20.0  # At least 20% cash

# Limits
max_open_positions = 10      # Max concurrent positions
min_position_usd = 10.0      # Minimum position

# Risk-Adjusted Sizing
kelly_fraction = 0.5         # Half-Kelly for conservative sizing
```

### Expected Data Collection (3-4 Months)

With 6 cohorts × 18 unique coins × 24/7 trading:

| Metric | Expected Volume |
|--------|----------------|
| Trades | ~30,000 |
| Signal Data Points | ~450,000 |
| Market Snapshots | ~45,000 |
| Per-Coin Optimizations | 20+ sets |

---

## 📖 Trading Playbook — The Heart

The **Trading Playbook** is a self-learning experience memory:

```
config/TRADING_PLAYBOOK.md          ← Current playbook
config/playbook_history/            ← All historical versions
├── playbook_v1_20260205.md
├── playbook_v2_20260212.md
└── ...
```

### How It Works

1. **Daily Learning** (21:00): Analyzes new trades
2. **Weekly Update** (Sunday 19:00): Generates new playbook
3. **Pattern Recognition**: Identifies successful/failed strategies
4. **AI Integration**: Playbook is passed as context to DeepSeek

### What the Playbook Contains

- Fear & Greed rules with success rates
- Whale alert interpretation
- Economic event reactions
- Technical analysis rules
- Anti-patterns (what to avoid)
- Successful strategies

---

## 📊 Logging & Analysis

### Structured Logs

```
logs/
├── error.log          # Errors with full context
├── trade.log          # Every trade with market data
├── decision.log       # AI decisions with reasoning
├── performance.log    # Daily/weekly performance
├── playbook.log       # Playbook updates & rules
├── api.log            # API calls for rate limit analysis
└── combined.log       # Everything combined
```

All logs are JSON-formatted for easy parsing:

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

Every Saturday at 23:00, an export is created for Claude Code analysis:

```
analysis_exports/
└── week_20260205/
    ├── analysis_export.json    # Structured data
    ├── ANALYSIS_REPORT.md      # Readable summary
    └── logs/                   # Relevant log excerpts
```

See [docs/CLAUDE_ANALYSIS_GUIDE.md](docs/CLAUDE_ANALYSIS_GUIDE.md) for the analysis workflow.

---

## 📁 Project Structure

```
binance-grid-bot/
├── src/
│   ├── core/
│   │   ├── bot.py              # GridBot with tick() method
│   │   ├── order_manager.py    # OrderManagerMixin (order lifecycle)
│   │   ├── state_manager.py    # StateManagerMixin (state persistence)
│   │   ├── risk_guard.py       # RiskGuardMixin (risk validation)
│   │   ├── config.py           # Central configuration with validation
│   │   ├── hybrid_orchestrator.py # Hybrid system orchestrator
│   │   ├── hybrid_config.py    # Hybrid system config (from_cohort())
│   │   ├── mode_manager.py     # Mode management with hysteresis (not singleton)
│   │   ├── trading_mode.py     # TradingMode enum, ModeState
│   │   ├── logging_system.py   # Structured logging
│   │   ├── cohort_manager.py   # Cohort definitions & DB access
│   │   ├── cohort_orchestrator.py # Top-level: 6 HybridOrchestrators in parallel
│   │   └── cycle_manager.py    # Weekly cycles
│   ├── api/
│   │   ├── binance_client.py   # Binance API wrapper
│   │   └── http_client.py      # HTTP client with retry/caching
│   ├── strategies/
│   │   ├── grid_strategy.py    # Grid trading logic
│   │   ├── dynamic_grid.py     # ATR-based grids
│   │   ├── ai_enhanced.py      # DeepSeek AI + playbook integration
│   │   └── portfolio_rebalance.py
│   ├── data/
│   │   ├── market_data.py      # Central market data provider
│   │   ├── watchlist.py        # Multi-coin watchlist manager
│   │   ├── sentiment.py        # Fear & Greed, CoinGecko
│   │   ├── social_sentiment.py # LunarCrush, Reddit, Twitter
│   │   ├── etf_flows.py        # Bitcoin/ETH ETF tracking
│   │   ├── token_unlocks.py    # Supply events
│   │   ├── whale_alert.py      # Whale tracking
│   │   ├── economic_events.py  # FOMC, CPI, NFP events
│   │   ├── memory.py           # Trading memory system (RAG)
│   │   ├── playbook.py         # Trading playbook generator (regime-stratified)
│   │   ├── market_cap.py       # CoinGecko market cap API
│   │   └── fetcher.py          # Historical data
│   ├── scanner/                # Multi-coin opportunity scanner
│   │   ├── coin_scanner.py     # Opportunity detection
│   │   ├── coin_discovery.py   # AI auto-discovery (DeepSeek)
│   │   └── opportunity.py      # Opportunity dataclass
│   ├── portfolio/              # Portfolio management
│   │   ├── allocator.py        # Kelly-based capital distribution
│   │   ├── constraints.py      # Allocation rules & limits
│   │   ├── portfolio_manager.py # 3-tier orchestrator (PORTFOLIO_MANAGER=true)
│   │   ├── profit_engine.py    # Weekly profit redistribution
│   │   ├── ai_optimizer.py     # Monthly DeepSeek tier optimization
│   │   ├── validation.py       # ProductionValidator (9 go-live criteria)
│   │   ├── go_live.py          # GoLiveChecklist + DeploymentPhases
│   │   └── tiers/
│   │       ├── cash_reserve.py # Cash reserve tier (USDT)
│   │       ├── index_holdings.py # Index tier (CMC Top 20)
│   │       └── trading_tier.py # Trading tier (CohortOrchestrator)
│   ├── risk/
│   │   ├── stop_loss.py        # Stop-loss management (lifecycle: confirm/reactivate)
│   │   ├── stop_loss_executor.py # Retry + balance-aware market sell
│   │   └── cvar_sizing.py      # CVaR position sizing
│   ├── analysis/
│   │   ├── technical_indicators.py
│   │   ├── weekly_export.py    # Weekly analysis export
│   │   ├── signal_analyzer.py  # Signal breakdown storage
│   │   ├── metrics_calculator.py # Sharpe, Sortino, Kelly
│   │   ├── regime_detection.py # HMM market regime
│   │   ├── bayesian_weights.py # Adaptive signal weights
│   │   ├── divergence_detector.py # RSI/MACD divergences
│   │   └── correlation_matrix.py # 60-day Pearson correlation
│   ├── optimization/
│   │   └── ab_testing.py       # A/B testing framework
│   ├── models/
│   │   └── portfolio.py        # Markowitz, Kelly Criterion
│   ├── notifications/
│   │   ├── telegram_service.py # Central Telegram service
│   │   ├── telegram_bot.py     # Telegram bot commands
│   │   ├── charts.py           # Performance charts
│   │   └── ai_assistant.py     # AI chat integration
│   ├── utils/
│   │   ├── singleton.py        # SingletonMixin base class (all services)
│   │   ├── heartbeat.py        # Docker health-check heartbeat
│   │   └── task_lock.py        # Thread-safe task locking
│   ├── tasks/                  # Domain-specific scheduler tasks
│   │   ├── base.py             # Shared infra (DB connection via pool)
│   │   ├── system_tasks.py     # Health, stops, drawdown reset
│   │   ├── analysis_tasks.py   # Regime, weights, divergence
│   │   ├── market_tasks.py     # Snapshots, sentiment
│   │   ├── data_tasks.py       # ETF, social, whale, unlocks
│   │   ├── hybrid_tasks.py     # Mode eval, rebalance
│   │   ├── portfolio_tasks.py  # Watchlist, scan, allocation
│   │   ├── cycle_tasks.py      # Cycle mgmt, weekly rebalance
│   │   ├── reporting_tasks.py  # Summary, export, playbook
│   │   ├── monitoring_tasks.py # Order reconciliation, grid health
│   │   └── retention_tasks.py  # Data retention auto-cleanup
│   └── backtest/
│       └── engine.py           # Backtesting engine
├── docker/
│   ├── docker-compose.yml      # PostgreSQL, Redis, Bot
│   ├── scheduler.py            # Scheduled tasks (extended)
│   ├── telegram_bot_handler.py # Telegram command handler
│   └── init.sql                # Database schema (extended)
├── config/
│   ├── bot_state.json          # Persistent bot state (single-coin)
│   ├── hybrid_state_{cohort}.json  # Per-cohort orchestrator state
│   ├── grid_state_{sym}_{cohort}.json # Per-cohort grid bot state
│   ├── TRADING_PLAYBOOK.md     # Current playbook
│   └── playbook_history/       # Playbook versions
├── logs/                       # Structured logs (gitignored)
├── analysis_exports/           # Weekly exports (gitignored)
├── docs/
│   └── CLAUDE_ANALYSIS_GUIDE.md
├── main.py                     # Entry point (single-coin GridBot)
├── main_hybrid.py              # Entry point (hybrid multi-coin)
├── requirements.txt
├── pyproject.toml              # Linting/formatting config
└── .github/
    └── workflows/
        └── ci.yml              # CI/CD pipeline with auto-release
```

---

## 🗄 Database Schema

### Table Overview

| Table | Description | Primary Use |
|-------|-------------|-------------|
| `trades` | All executed trades | Trade history, performance analysis |
| `cohorts` | Parallel strategy variants | A/B/C/D testing |
| `trading_cycles` | Weekly trading cycles | Performance per cycle |
| `signal_components` | Signal breakdown per trade | Signal performance analysis |
| `calculation_snapshots` | Kelly, VaR, CVaR calculations | Risk tracking |
| `trade_pairs` | BUY/SELL pairs | Realized P&L tracking |
| `regime_history` | Market regime changes | Regime-based adjustments |
| **Multi-Coin Tables** | | |
| `watchlist` | Coin universe with categories | Multi-coin trading |
| `coin_performance` | Per-coin performance metrics | Coin-specific optimization |
| `cohort_allocations` | Positions per cohort | Portfolio management |
| `opportunities` | Scanner results | Opportunity tracking |
| `trading_mode_history` | Mode switch history | Hybrid system tracking |
| **Data Provider Tables** | | |
| `social_sentiment` | Social media tracking | Sentiment signals |
| `etf_flows` | BTC/ETH ETF inflows | Institutional flows |
| `token_unlocks` | Token supply events | Supply-based signals |
| `market_snapshots` | Hourly market data | Historical analysis |
| `whale_alerts` | Large transactions | Sentiment analysis |
| `economic_events` | Macro events (FOMC, CPI) | Event-based trading |
| `learned_patterns` | Successful patterns | AI context |
| `portfolio_snapshots` | Portfolio state | Performance tracking |
| `stop_loss_orders` | Stop-loss tracking | Risk management |
| `technical_indicators` | Computed indicators | Technical analysis |
| `ai_conversations` | Telegram AI chat | Context for AI responses |
| **Portfolio Tier Tables** | | |
| `portfolio_tiers` | Tier target allocations (cash/index/trading) | 3-tier management |
| `tier_allocation_history` | Change history per tier | Audit trail |
| `index_holdings` | CMC Top 20 positions + trailing stops | Index tier |
| `profit_redistributions` | Profit redistribution log | Rebalancing |
| `ai_portfolio_recommendations` | DeepSeek tier recommendations | AI optimizer |
| `coin_discoveries` | AI auto-discovery results | Coin discovery |

### Multi-Coin Views

| View | Description |
|------|-------------|
| `v_coin_rankings` | Coins sorted by performance (Win Rate × Trades) |
| `v_active_positions` | All active positions with P&L |
| `v_category_performance` | Performance aggregated by category |

### `trades` — Trade History with Context

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Trade Details
    action VARCHAR(10),       -- BUY, SELL, HOLD
    symbol VARCHAR(20),       -- e.g. BTCUSDT
    price DECIMAL(20, 8),
    quantity DECIMAL(20, 8),
    value_usd DECIMAL(20, 2),

    -- Market Context (at time of trade)
    fear_greed_at_entry INTEGER,  -- 0-100
    btc_price_at_entry DECIMAL(20, 2),
    market_trend VARCHAR(20),     -- BULL, BEAR, SIDEWAYS

    -- Decision Context
    math_signal JSONB,            -- Markowitz/Portfolio output
    ai_signal JSONB,              -- DeepSeek analysis
    reasoning TEXT,               -- Reasoning for trade
    confidence DECIMAL(3, 2),     -- 0.00 - 1.00

    -- Outcome (updated later for playbook learning)
    outcome_1h DECIMAL(10, 4),    -- Return after 1h
    outcome_24h DECIMAL(10, 4),   -- Return after 24h
    outcome_7d DECIMAL(10, 4),    -- Return after 7d
    was_good_decision BOOLEAN     -- Automatically calculated
);
```

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Binance Account (Testnet or Live)
- Optional: DeepSeek API Key, Telegram Bot

### Quick Start

```bash
# Clone repository
git clone https://github.com/murriiii/binance-grid-bot.git
cd binance-grid-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start Docker services (PostgreSQL, Redis)
cd docker
docker compose up -d

# Start bot
cd ..
python main.py
```

### Docker Setup (Recommended)

```bash
# Classic single-coin GridBot
cd docker
docker compose up -d

# OR: Hybrid multi-coin system
docker compose --profile hybrid up -d

# View logs
docker logs -f trading-bot       # Single-coin
docker logs -f hybrid-bot        # Hybrid

# Check status
docker compose ps
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```env
# === BINANCE ===
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_SECRET=your_testnet_secret
BINANCE_API_KEY=your_live_key       # Only for live trading
BINANCE_SECRET=your_live_secret

# === TRADING ===
TRADING_PAIR=BTCUSDT
INVESTMENT_AMOUNT=10                 # USDT
NUM_GRIDS=3
GRID_RANGE_PERCENT=5

# === RISK ===
RISK_TOLERANCE=medium               # low, medium, high
MAX_DAILY_DRAWDOWN=10               # Percent
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

---

## 📱 Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Current bot status and portfolio |
| `/report` | Portfolio dashboard with emoji status per cohort, P&L and coin details |
| `/market` | Market overview (F&G, BTC, trending) |
| `/ta BTCUSDT` | Technical analysis for symbol |
| `/whale` | Latest whale alerts |
| `/events` | Upcoming macro events |
| `/performance` | 30-day performance |
| `/playbook` | Show current trading playbook |
| `/playbook_stats` | Playbook statistics |
| `/playbook_update` | Trigger manual playbook update |
| `/compare` | Cohort comparison ranking |
| `/portfolio` | 3-tier portfolio breakdown with drift display |
| `/validate` | Production readiness check (9 criteria) |
| `/stop` | Stop bot |

---

## ⏰ Scheduler Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| **Hybrid System Tasks** | | |
| Mode Evaluation | Hourly | Evaluate regime, check mode switch |
| Hybrid Rebalance | 6h | Check allocation drift (>5%) |
| **Multi-Coin Tasks** | | |
| Watchlist Update | 30 min | Update market data for all coins |
| Opportunity Scan | 2h | Scan all coins for opportunities |
| Portfolio Rebalance | 06:00 | Check and adjust allocation |
| Coin Performance | 21:30 | Update per-coin metrics |
| **Data Collection** | | |
| Market Snapshot | Hourly | Store market data |
| Whale Check | Hourly | Large transactions |
| Sentiment Check | 4h | F&G extreme alert |
| Social Sentiment | 4h | LunarCrush, Reddit, Twitter |
| ETF Flows | 10:00 | Bitcoin/ETH ETF tracking |
| Token Unlocks | 08:00 | Supply events |
| Macro Check | 08:00 | Check FOMC/CPI events |
| **Analysis** | | |
| Regime Detection | 4h | HMM market regime update |
| Divergence Scan | 2h | RSI/MACD divergences |
| Technical Indicators | 2h | Compute indicators and write to DB |
| Signal Weights | 22:00 | Bayesian weight update |
| Pattern Learning | 21:00 | Daily trade analysis |
| **Risk & Performance** | | |
| Stop-Loss Check | 5 min | Check active stops + market sell with retry |
| Drawdown Reset | 00:00 | Reset daily drawdown baseline |
| Outcome Update | 6h | Update trade outcomes |
| System Health | 6h | Check DB, API, memory |
| A/B Test Check | 23:00 | Check statistical significance |
| **Monitoring** | | |
| Order Reconciliation | 30 min | Compare state files with Binance orders |
| Order Timeout | Hourly | Detect stale orders (>6h, >24h) |
| Portfolio Plausibility | 2h | Verify allocation math |
| Grid Health | 4h | BUY/SELL counts, failed follow-ups |
| **Reports** | | |
| Daily Summary | 20:00 | Portfolio report (incl. tier breakdown) |
| Weekly Export | Sat 23:00 | Create analysis export |
| **Weekly Tasks** | | |
| Cycle Management | Sun 00:00 | End/start cycle |
| Weekly Rebalance | Sun 18:00 | Portfolio rebalancing |
| Playbook Update | Sun 19:00 | Regenerate playbook |
| **AI Learning Loop** | | |
| Outcome 1h | Hourly | Calculate 1h trade outcome |
| Outcome 4h | 4h | Calculate 4h trade outcome |
| Outcome 24h | 6h | Calculate 24h trade outcome (existing) |
| Outcome 7d | 12:00 | Calculate 7d trade outcome |
| Signal Correctness | 6h | `was_correct` for signal components |
| Trade Decisions | 22:30 | `was_good_decision` via trade_pairs P&L |
| Portfolio Snapshot | Hourly | Equity curve + Sharpe calculation |
| **Portfolio Tier Tasks** | | |
| Tier Health Check | 2h | Cash level, drift, trading activity |
| Profit Redistribution | Sun 17:00 | Tier rebalancing when drift > 3% |
| AI Portfolio Optimizer | 1st of month | DeepSeek tier weight recommendation |
| Production Validation | 09:00 | Go-live readiness check |
| **Data Maintenance** | | |
| Data Retention Cleanup | 03:00 | Clean old data (8 tables, 30-180 days) |

---

## 🔄 Weekly Optimization Workflow

```bash
# Every Sunday after the automatic export:
cd /home/murriiii/dev/private/trading/binance-grid-bot
claude

# Ask Claude Code:
"Analyze the latest weekly export in analysis_exports/ and suggest:
1. Playbook rule updates based on trade outcomes
2. Code improvements for common errors
3. Risk management adjustments"
```

Detailed guide: [docs/CLAUDE_ANALYSIS_GUIDE.md](docs/CLAUDE_ANALYSIS_GUIDE.md)

---

## 🤖 AI-Enhanced Trading

### DeepSeek + Playbook Integration

```python
from src.strategies.ai_enhanced import AITradingEnhancer

ai = AITradingEnhancer()

# System prompt automatically includes the playbook:
# - Fear & Greed rules
# - Historical success rates
# - Anti-patterns to avoid

signal = ai.analyze_news([
    {"title": "Fed signals rate cut", "summary": "..."}
])
print(signal.direction)    # BULLISH
print(signal.confidence)   # 0.75
print(signal.reasoning)    # "Fed dovish → Risk-On, Playbook says BUY at F&G < 40..."
```

---

## 🛡 Risk Management

### Stop-Loss Types

| Type | Description |
|------|-------------|
| `FIXED` | Fixed percentage below entry |
| `TRAILING` | Follows price upward |
| `ATR` | Volatility-based (14-period ATR) |
| `BREAK_EVEN` | Set to entry after X% profit |

### Order Risk Pipeline

Every order (initial + follow-up) goes through before placement:

1. **Portfolio Drawdown Check** — Trading stopped at >10% daily loss (baseline reset daily at midnight)
2. **CVaR Max Position** — Order value must not exceed CVaR limit
3. **Allocation Constraints** — Cash reserve and exposure limits maintained
4. **Circuit Breaker** — Emergency stop on flash crash (>10% drop per check cycle)

On risk module failure: graceful degradation (order is allowed).

### Stop-Loss Execution Pipeline

When a stop-loss triggers:

1. **Balance Check** — Query actual balance via API, sell `min(intended, actual)`
2. **Step-Size Rounding** — Round quantity to Binance `step_size`
3. **Retry Loop** — 3 attempts with backoff (2s, 5s, 10s). On INSUFFICIENT_BALANCE: re-fetch balance and retry with reduced amount
4. **Confirm/Reactivate** — On success: `confirm_trigger()` deactivates stop. On failure: `reactivate()` keeps stop active for next tick
5. **Critical Alert** — On total failure: CRITICAL log + Telegram "Manual sell needed"

### Portfolio Risk

- **Max Daily Drawdown**: Automatic stop at 10% daily loss
- **Position Sizing**: Kelly Criterion for optimal size
- **Diversification**: Markowitz Mean-Variance Optimization
- **Stop-Loss Persistence**: Stops stored in PostgreSQL and automatically restored after restart (reconciliation at `load_state()`)

---

## 🛠 Development

### Code Style

```bash
# Linting with Ruff
ruff check src/

# Formatting with Ruff
ruff format src/

# Type checking
mypy src/
```

### Tests

```bash
# Run all tests (1089 tests)
pytest tests/ -v

# With coverage (minimum: 60%)
pytest tests/ --cov=src --cov-report=term-missing

# Single test file
pytest tests/test_grid_strategy.py -v
```

#### Test Coverage

| Area | Coverage | Tests |
|------|----------|-------|
| Core (bot, orchestrator, mode) | 52-99% | GridBot, Hybrid, ModeManager |
| Strategies | 47-99% | Grid, Dynamic, AI-Enhanced, Rebalance |
| Tasks | 75-100% | All 8 task modules |
| Notifications | 61-90% | Telegram, Charts, AI Assistants |
| Data Providers | 21-73% | Market, Sentiment, Whale, ETF |
| Risk | 49-94% | CVaR, Stop-Loss, Risk Guard |
| API | 20-76% | Binance Client, HTTP Client |
| Scanner/Portfolio | 43-97% | CoinScanner, Allocator |
| Monitoring | 100% | Order Reconciliation, Grid Health, Tier Health |
| Portfolio Tiers | 90%+ | PortfolioManager, Tiers, Profit Engine, AI Optimizer |
| Production | 100% | ProductionValidator, GoLiveChecklist |
| **Total** | **60%** | **1089 Tests** |

### Pre-commit Hooks

```bash
# Installation
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## 🔄 CI/CD Pipeline

The GitHub Actions pipeline:

1. **Lint & Format**: Ruff checks (0 errors)
2. **Type Check**: mypy strict mode (0 errors)
3. **Tests**: 1089 tests with coverage >= 60%
4. **Auto-Release**: On version bump in pyproject.toml, a GitHub Release is automatically created

---

## 📝 Conventional Commits

```
feat: Add whale alert integration
fix: Correct min_qty validation
docs: Update README with database schema
refactor: Extract HTTP client to separate module
test: Add tests for grid strategy
chore: Update dependencies
```

### Automatic Versioning

| Prefix | Version Bump |
|--------|-------------|
| `feat:` | Minor (0.X.0) |
| `fix:` | Patch (0.0.X) |
| `BREAKING CHANGE:` | Major (X.0.0) |

---

## 🔌 API Integration

| API | Purpose | Auth |
|-----|---------|------|
| Binance Spot | Trading, prices | API Key |
| Binance Futures | Funding rate signal | None (public) |
| Alternative.me | Fear & Greed Index | None |
| CoinGecko | Social stats, trending, market cap (Index Tier) | None |
| LunarCrush | Social sentiment, Galaxy Score | API Key |
| Reddit (PRAW) | Reddit mentions, sentiment | OAuth |
| Farside Investors | Bitcoin ETF flows | None |
| SoSoValue | ETH ETF flows | None |
| TokenUnlocks.app | Token unlock events | None |
| Blockchain.com | Whale tracking (BTC) | None |
| TradingView | Economic calendar | None |
| DeepSeek | AI analysis | API Key |
| Telegram | Notifications | Bot Token |

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

## ⚠️ Disclaimer

**This project is for educational purposes only.**

- Not financial advice
- Trading involves risk
- Always use testnet first
- Only invest what you can afford to lose

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: Add amazing feature'`)
4. Push branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

<p align="center">
  Built with <a href="https://claude.ai/code">Claude Code</a> by <a href="https://github.com/murriiii">murriiii</a>
</p>
