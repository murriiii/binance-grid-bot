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

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Lint and format
ruff check src/ tests/ docker/scheduler.py main_hybrid.py
ruff format src/ tests/ docker/scheduler.py main_hybrid.py

# Type checking
mypy src/

# Pre-commit hooks (runs automatically on commit)
pre-commit run --all-files

# Start Docker services (classic single-coin GridBot)
cd docker && docker-compose up -d

# Start Docker services (hybrid multi-coin system)
cd docker && docker-compose --profile hybrid up -d
```

## Code Conventions

- **Line length**: 100 characters (Ruff formatter handles this)
- **Type hints**: Use `X | None` instead of `Optional[X]` (Ruff UP007/UP045). No quoted forward references (UP037).
- **Imports**: isort-ordered via Ruff. `src` is first-party.
- **Logging**: Always use `logger = logging.getLogger("trading_bot")`. Never use `print()` for operational logs.
- **Commits**: Conventional commits enforced by commitizen (`feat:`, `fix:`, `bump:`, etc.)
- **Test markers**: `@pytest.mark.slow`, `@pytest.mark.integration`
- **Coverage**: 60% minimum (`fail_under = 60` in pyproject.toml)
- **mypy**: Legacy modules have `ignore_errors = true` in pyproject.toml. New modules are strictly checked.

## Architecture Overview

### Two Entry Points

The system has two operational modes:

1. **`main.py`** - Classic single-coin GridBot (standalone)
2. **`main_hybrid.py`** - Hybrid multi-coin system with regime-adaptive mode switching

```
main_hybrid.py
     │
     ▼
HybridOrchestrator ──── ModeManager (hysteresis)
     │                       │
     ├── HOLD mode ──────── RegimeDetector (HMM)
     ├── GRID mode ──────── GridBot.tick() per symbol
     └── CASH mode ──────── Cancel orders, sell positions
     │
     ├── CoinScanner ────── Opportunity scoring
     ├── PortfolioAllocator  Kelly-based allocation
     └── BinanceClient ──── Shared across all symbols
```

### Hybrid Trading System

The HybridOrchestrator (`src/core/hybrid_orchestrator.py`) manages multi-coin trading across three regime-adaptive modes:

| Mode | Regime | Behavior |
|------|--------|----------|
| HOLD | BULL | Market-buy allocations, 7% trailing stop, ride the trend |
| GRID | SIDEWAYS | Grid trading via `GridBot.tick()` per symbol |
| CASH | BEAR | Cancel orders, sell positions, preserve capital in USDT |

**Mode switching** is controlled by `ModeManager` (`src/core/mode_manager.py`) with hysteresis protection:
- Requires regime probability >= 75% AND duration >= 2 days before switching
- 24h cooldown between mode switches
- Safety lock: >2 transitions in 48h forces GRID mode
- **Exception**: BEAR with probability >= 85% triggers immediate CASH (emergency capital protection)

**Per-symbol state** is tracked via `SymbolState` dataclass (mode, grid bot instance, hold quantity, allocation, stop-loss IDs). State is persisted to `config/hybrid_state.json` with atomic writes (temp + rename).

**6 transition paths**: GRID↔HOLD, GRID↔CASH, HOLD↔CASH. Each transition has specific cleanup logic (e.g., GRID→HOLD converts active orders to hold position; HOLD→CASH tightens trailing stop to 3%).

**Config**: `HybridConfig` (`src/core/hybrid_config.py`) loaded from `HYBRID_*` env vars. Key settings:
```
HYBRID_INITIAL_MODE, HYBRID_ENABLE_MODE_SWITCHING, HYBRID_TOTAL_INVESTMENT,
HYBRID_MAX_SYMBOLS, HYBRID_MIN_POSITION_USD, HYBRID_HOLD_TRAILING_STOP_PCT,
HYBRID_MODE_COOLDOWN_HOURS, HYBRID_MIN_REGIME_PROBABILITY, HYBRID_MIN_REGIME_DURATION_DAYS
```

### GridBot with tick()

`GridBot` (`src/core/bot.py`) exposes a `tick()` method extracted from the main loop. This allows:
- **Standalone**: `GridBot.run()` calls `tick()` in a loop (classic mode via `main.py`)
- **Orchestrated**: `HybridOrchestrator` calls `GridBot.tick()` per symbol in GRID mode
- GridBot accepts an optional external `BinanceClient` to share connections across symbols

### Singleton Services

Critical shared resources use the singleton pattern with `get_instance()` and `reset_instance()` methods:
- `get_config()` - Global configuration from environment
- `get_http_client()` - Centralized HTTP with retry/caching/file uploads
- `DatabaseManager.get_instance()` - PostgreSQL connection pooling (1-10 connections)
- `TelegramService.get_instance()` - Notification service (4096 char message limit with truncation)
- `ModeManager.get_instance()` - Regime-adaptive mode switching with hysteresis
- `MarketDataProvider.get_instance()` - Price data with caching
- `WatchlistManager.get_instance()` - Multi-coin universe management
- `CoinScanner.get_instance()` - Opportunity detection across coins
- `PortfolioAllocator.get_instance()` - Kelly-based capital allocation (regime-aware)
- `RegimeDetector.get_instance()` - HMM market regime detection
- `DynamicGridStrategy.get_instance()` - ATR-based grid spacing (cache with eviction policy, max 50 entries)
- `CohortManager.get_instance()`, `CycleManager.get_instance()`, `SignalAnalyzer.get_instance()`,
  `MetricsCalculator.get_instance()`, `BayesianWeightLearner.get_instance()`,
  `DivergenceDetector.get_instance()`, `ABTestingFramework.get_instance()`,
  `CVaRPositionSizer.get_instance()`

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

### Grid Strategy Logic

1. Calculate grid levels: `spacing = (upper - lower) / num_grids`
2. Each level gets `investment_per_grid / price` quantity
3. Validate against Binance min_qty and min_notional (percentage-based price matching: 0.1% tolerance)
4. On BUY fill → place SELL at next higher level
5. On SELL fill → place BUY at next lower level

### Multi-Coin Trading Pipeline

1. **WatchlistManager** maintains coin universe (25+ coins in 6 categories: LARGE_CAP, MID_CAP, L2, DEFI, AI, GAMING)
2. **CoinScanner** scores opportunities on 5 dimensions: technical (30%), volume (20%), sentiment (15%), whale (15%), momentum (20%)
3. **PortfolioAllocator** distributes capital via Kelly Criterion with regime-aware constraints
4. Constraint presets: `CONSERVATIVE_CONSTRAINTS`, `BALANCED_CONSTRAINTS`, `AGGRESSIVE_CONSTRAINTS`, `SMALL_PORTFOLIO_CONSTRAINTS`
5. ModeManager selects constraints based on current mode (HOLD→aggressive, GRID→balanced/small, CASH→conservative)

### Task Locking

Scheduled tasks use `@task_locked` from `src/utils/task_lock.py` to prevent concurrent execution:
```python
from src.utils.task_lock import task_locked

@task_locked
def my_scheduled_task():
    pass  # Skips if already running (non-blocking)
```

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

Hybrid-specific config in `src/core/hybrid_config.py` with `HYBRID_*` prefix.

## Docker Services

- `trading-bot` - Classic single-coin GridBot
- `hybrid-bot` - Hybrid multi-coin system (requires `--profile hybrid`)
- `telegram-handler` - Telegram commands (separate process)
- `scheduler` - Background tasks (see Key Scheduled Tasks)
- `postgres` - Trading memory database
- `redis` - Caching

### Key Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| Mode Evaluation | Hourly (:15) | Evaluate regime, check mode switch |
| Hybrid Rebalance | Every 6h | Check allocation drift (>5% threshold) |
| Cycle Management | Sun 00:00 | End/start weekly cycles |
| Watchlist Update | Every 30min | Update market data for all coins |
| Opportunity Scan | Every 2h | Scan coins for trading opportunities |
| Portfolio Rebalance | 06:00 daily | Check allocation constraints |
| Regime Detection | Every 4h | HMM market regime update |
| Signal Weights | 22:00 daily | Bayesian weight update |
| Divergence Scan | Every 2h | RSI/MACD divergences |
| Playbook Update | Sun 19:00 | Generate new playbook |
| Weekly Export | Sat 23:00 | Create analysis export |

## Testing Notes

Tests use fixtures from `tests/conftest.py`:
- `reset_singletons` - Resets original singleton instances between tests
- `reset_new_singletons` - Resets hybrid system singletons (ModeManager, etc.)
- `mock_env_vars` - Sets test environment variables (autouse)
- `sample_ohlcv_data` - OHLCV data for technical analysis tests
- `sample_returns` - Return data for risk calculation tests
- `sample_trade_history` - Trade history for signal analysis

Mock external APIs at module level: `@patch("src.module.get_http_client")`

Symbol info format for GridStrategy tests uses flat dict:
```python
{"symbol": "BTCUSDT", "min_qty": 0.00001, "step_size": 0.00001, "min_notional": 5.00}
```
