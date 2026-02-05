# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run single test file
pytest tests/test_grid_strategy.py -v

# Run specific test
pytest tests/test_grid_strategy.py::TestGridStrategy::test_initialization -v

# Lint and format
ruff check src/ tests/ docker/
ruff format src/ tests/ docker/

# Type checking
mypy src/

# Pre-commit hooks (runs automatically on commit)
pre-commit run --all-files

# Start Docker services
cd docker && docker-compose up -d

# View bot logs
docker logs -f trading-bot
```

## Architecture Overview

### Core Components

The bot is built around a **GridBot** orchestrator (`src/core/bot.py`) that manages the trading lifecycle:

```
GridBot → GridStrategy → BinanceClient → Trade Execution
    ↓                         ↓
TradingMemory (PostgreSQL) ← Market Data ← External APIs
    ↓
DeepSeek AI (optional enhancement)
```

### Singleton Services

Critical shared resources use the singleton pattern with `get_instance()` and `reset_instance()` methods:
- `get_config()` - Global configuration from environment
- `get_http_client()` - Centralized HTTP with retry/caching/file uploads
- `DatabaseManager.get_instance()` - PostgreSQL connection pooling (1-10 connections)
- `TelegramService.get_instance()` - Notification service
- `MarketDataProvider.get_instance()` - Price data with caching
- `WatchlistManager.get_instance()` - Multi-coin universe management
- `CoinScanner.get_instance()` - Opportunity detection across coins
- `PortfolioAllocator.get_instance()` - Kelly-based capital allocation
- `CohortManager.get_instance()` - Parallel strategy variants
- `CycleManager.get_instance()` - Weekly trading cycles
- `SignalAnalyzer.get_instance()` - Signal breakdown storage
- `MetricsCalculator.get_instance()` - Risk metrics (Sharpe, Sortino, Kelly)
- `RegimeDetector.get_instance()` - HMM market regime detection
- `BayesianWeightLearner.get_instance()` - Adaptive signal weights
- `DivergenceDetector.get_instance()` - Technical divergences
- `ABTestingFramework.get_instance()` - A/B testing with statistics
- `CVaRPositionSizer.get_instance()` - Risk-based position sizing
- `DynamicGridStrategy.get_instance()` - ATR-based grid spacing

### HTTP Client Pattern

All HTTP requests go through the centralized HTTPClient (`src/api/http_client.py`):
```python
from src.api.http_client import HTTPClientError, get_http_client

http = get_http_client()
data = http.get(url, params=params, api_type="binance")
data = http.post(url, json=payload, api_type="deepseek", files=files)
```
API types with default timeouts: `default` (10s), `deepseek` (30s), `telegram` (10s), `binance` (10s), `blockchain` (15s)

### Database Access

Use `DatabaseManager` from `src/data/database.py` for all PostgreSQL access:
```python
from src.data.database import get_db

db = get_db()
with db.get_cursor() as cur:
    cur.execute("SELECT * FROM trades WHERE symbol = %s", (symbol,))
    rows = cur.fetchall()
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `src/core/bot.py` | Main GridBot orchestrator with error recovery |
| `src/core/config.py` | Dataclass configs loaded from env vars |
| `src/core/cohort_manager.py` | Parallel strategy variants (conservative/balanced/aggressive/baseline) |
| `src/core/cycle_manager.py` | Weekly trading cycles with performance tracking |
| `src/api/http_client.py` | Centralized HTTP with retries, rate limits, file uploads |
| `src/data/database.py` | PostgreSQL connection pooling (DatabaseManager) |
| `src/data/watchlist.py` | Multi-coin universe (25+ coins, 6 categories) |
| `src/scanner/coin_scanner.py` | Opportunity detection (technical, volume, sentiment scores) |
| `src/portfolio/allocator.py` | Kelly-based allocation with constraints |
| `src/strategies/grid_strategy.py` | Grid level calculation and order logic |
| `src/strategies/dynamic_grid.py` | ATR-based grid spacing, asymmetric grids |
| `src/data/memory.py` | PostgreSQL-based trading memory (RAG pattern) |
| `src/data/playbook.py` | Self-learning Trading Playbook generator |
| `src/analysis/signal_analyzer.py` | Signal breakdown persistence per trade |
| `src/analysis/metrics_calculator.py` | Sharpe, Sortino, Kelly, VaR, CVaR |
| `src/analysis/regime_detection.py` | HMM for BULL/BEAR/SIDEWAYS detection |
| `src/analysis/bayesian_weights.py` | Dirichlet-based adaptive signal weights |
| `src/analysis/divergence_detector.py` | RSI, MACD, Stochastic, MFI, OBV divergences |
| `src/optimization/ab_testing.py` | Statistical A/B testing (Welch t-test, Mann-Whitney U) |
| `src/risk/cvar_sizing.py` | CVaR-based position sizing |
| `src/risk/stop_loss.py` | Stop-loss management (fixed, trailing, ATR) |
| `src/strategies/ai_enhanced.py` | DeepSeek AI integration with fallbacks |

### Grid Strategy Logic

1. Calculate grid levels: `spacing = (upper - lower) / num_grids`
2. Each level gets `investment_per_grid / price` quantity
3. Validate against Binance min_qty and min_notional
4. On BUY fill → place SELL at next higher level
5. On SELL fill → place BUY at next lower level

### Cohort System

Parallel strategy testing with 4 cohorts running simultaneously:
- **Conservative**: Tight grids (2%), high confidence (>0.7), only F&G < 40
- **Balanced**: Standard grids (5%), medium confidence (>0.5), playbook-driven
- **Aggressive**: Wide grids (8%), low confidence ok, trades at F&G > 60
- **Baseline**: No changes, week 1 strategy for comparison

Each cohort has separate trades tracked via `cohort_id` in the database.

### Cycle Management

Weekly trading cycles (Sunday 00:00 - Saturday 23:59):
- Fresh capital allocation per cycle
- Full metrics calculated at cycle end (Sharpe, Sortino, Kelly, VaR, CVaR)
- Cycle-to-cycle comparison for learning

### Data Flow

Trades are stored with full context in PostgreSQL:
- Entry conditions (fear_greed, btc_price, trend)
- Decision signals (math_signal, ai_signal, confidence)
- Signal components breakdown via `signal_components` table
- Outcomes tracked at 1h, 24h, 7d intervals

The Memory System (`TradingMemory`) retrieves similar historical trades for AI context generation.

### Trading Playbook

The Playbook (`config/TRADING_PLAYBOOK.md`) is a self-learning "experience memory":
- Auto-generated weekly from trade outcomes (Sundays 19:00)
- Included in DeepSeek prompts as system context
- Contains Fear & Greed rules, success rates, anti-patterns
- Historical versions stored in `config/playbook_history/`

### Logging System

All logs are JSON-structured in `logs/` directory:
- `error.log` - Exceptions with full context
- `trade.log` - Every trade with market data
- `decision.log` - AI decisions with reasoning
- `performance.log` - Daily/weekly metrics
- `playbook.log` - Playbook updates

### External APIs

| API | Module | Notes |
|-----|--------|-------|
| Binance | `src/api/binance_client.py` | Rate limited (1000/min) |
| DeepSeek | `src/strategies/ai_enhanced.py` | 30s timeout, 3 retries |
| Alternative.me | `src/data/sentiment.py` | Fear & Greed Index |
| LunarCrush | `src/data/social_sentiment.py` | Galaxy Score, social volume |
| Reddit (PRAW) | `src/data/social_sentiment.py` | Mentions, sentiment |
| Farside Investors | `src/data/etf_flows.py` | Bitcoin ETF flows |
| TokenUnlocks.app | `src/data/token_unlocks.py` | Supply events |
| Blockchain.com | `src/data/whale_alert.py` | BTC whale tracking |
| Telegram | `src/notifications/telegram_service.py` | Bot notifications |

### Error Handling

- Exponential backoff: 30s → 300s max
- Consecutive error limit: 5 errors → emergency stop
- Graceful degradation: Bot continues if Memory/Stop-Loss unavailable
- AI fallback: Returns NEUTRAL signal on any failure

## Configuration

All settings via environment variables. Key configs in `src/core/config.py`:

```
TRADING_PAIR, INVESTMENT_AMOUNT, NUM_GRIDS, GRID_RANGE_PERCENT
RISK_TOLERANCE (low/medium/high), MAX_DAILY_DRAWDOWN, STOP_LOSS_PERCENT
DEEPSEEK_API_KEY, TELEGRAM_BOT_TOKEN, BINANCE_API_KEY
DATABASE_URL, REDIS_URL
```

## Docker Services

- `trading-bot` - Main GridBot
- `telegram-handler` - Telegram commands (separate process)
- `scheduler` - Background tasks (see Key Scheduled Tasks)
- `postgres` - Trading memory database
- `redis` - Caching

### Key Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| Cycle Management | Sun 00:00 | End/start weekly cycles |
| Watchlist Update | Every 30min | Update market data for all coins |
| Opportunity Scan | Every 2h | Scan coins for trading opportunities |
| Portfolio Rebalance | 06:00 daily | Check allocation constraints |
| Coin Performance | 21:30 daily | Update per-coin metrics |
| Regime Detection | Every 4h | HMM market regime update |
| Signal Weights | 22:00 daily | Bayesian weight update |
| Divergence Scan | Every 2h | RSI/MACD divergences |
| Social Sentiment | Every 4h | LunarCrush, Reddit |
| ETF Flows | 10:00 daily | Bitcoin/ETH ETF tracking |
| Token Unlocks | 08:00 daily | Supply events |
| A/B Test Check | 23:00 daily | Statistical significance |
| Playbook Update | Sun 19:00 | Generate new playbook |
| Weekly Export | Sat 23:00 | Create analysis export |

## Testing Notes

Tests use fixtures from `tests/conftest.py`:
- `reset_singletons` - Resets original singleton instances between tests
- `reset_new_singletons` - Resets Phase 1-5 singleton instances
- `mock_env_vars` - Sets test environment variables (autouse)
- `sample_ohlcv_data` - OHLCV data for technical analysis tests
- `sample_returns` - Return data for risk calculation tests
- `sample_trade_history` - Trade history for signal analysis
- Sample response fixtures for API mocking

Symbol info format for GridStrategy tests uses flat dict:
```python
{"symbol": "BTCUSDT", "min_qty": 0.00001, "step_size": 0.00001, "min_notional": 5.00}
```
