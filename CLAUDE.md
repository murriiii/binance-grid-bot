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

# Lint and format (include both entry points)
ruff check src/ tests/ docker/scheduler.py main.py main_hybrid.py
ruff format src/ tests/ docker/scheduler.py main.py main_hybrid.py

# Type checking
mypy src/

# Pre-commit hooks (runs automatically on commit)
pre-commit run --all-files

# Start Docker services (classic single-coin GridBot)
cd docker && docker compose up -d

# Start Docker services (hybrid multi-coin system)
cd docker && docker compose --profile hybrid up -d
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

### GridBot Mixin Decomposition

`GridBot` (`src/core/bot.py`) uses multiple inheritance with three mixins:

```python
class GridBot(RiskGuardMixin, OrderManagerMixin, StateManagerMixin):
```

| Mixin | File | Responsibility |
|-------|------|----------------|
| `OrderManagerMixin` | `src/core/order_manager.py` | Order lifecycle, fill detection, follow-up orders (with retry/backoff), partial fills, downtime recovery |
| `StateManagerMixin` | `src/core/state_manager.py` | JSON state persistence (atomic writes), state loading with Binance verification, orphan order cleanup |
| `RiskGuardMixin` | `src/core/risk_guard.py` | CVaR/drawdown/allocation validation, circuit breaker, stop-loss, market sells |

Each mixin documents its expected host attributes in the class docstring. When adding methods, ensure they match the documented contract.

**tick() pattern**: `GridBot.tick()` executes one iteration (check orders → save state → check circuit breaker → check stops) and returns `bool` (True = continue). `run()` calls `tick()` in a loop for standalone mode; `HybridOrchestrator` calls `tick()` per symbol in GRID mode.

**Failed follow-up retry**: When a follow-up order fails (e.g., PLACE_SELL after BUY fill), it's retried with exponential backoff (2/5/15/30/60 min, max 5 attempts). Orders with `failed_followup=True` are handled separately at the start of `check_orders()` via `_retry_failed_followup()`. After max retries: CRITICAL log + Telegram alert, order removed.

**Downtime recovery**: `_pending_followups: list[dict]` queues follow-up actions for fills detected during downtime. `load_state()` detects FILLED/partially-CANCELED orders and queues follow-ups, which `_process_pending_followups()` executes after strategy initialization.

**State file per symbol**: In hybrid mode, each GridBot writes to `config/grid_state_{SYMBOL}.json` (passed via `config["state_file"]`). Default is `bot_state.json` for standalone mode.

**Config mismatch handling**: When `load_state()` detects a symbol or investment change, it cancels all orphaned orders at Binance via `_cancel_orphaned_orders()` before returning False. Corrupt JSON state files are caught separately (`json.JSONDecodeError`) and reset `active_orders` to `{}`.

**Atomic state writes**: Both `StateManagerMixin` and `HybridOrchestrator` use temp file + rename:
```python
temp_file = self.state_file.with_suffix(".tmp")
with open(temp_file, "w") as f:
    json.dump(state, f, indent=2)
temp_file.replace(self.state_file)
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
- Safety lock: >2 transitions in 48h forces GRID mode (auto-expires after 7 days via `_lock_activated_at`)
- **Exception**: BEAR with probability >= 85% triggers immediate CASH (emergency capital protection)

**Per-symbol state** is tracked via `SymbolState` dataclass (mode, grid bot instance, hold quantity, allocation, stop-loss IDs). State is persisted to `config/hybrid_state.json` with atomic writes.

**6 transition paths**: GRID↔HOLD, GRID↔CASH, HOLD↔CASH. Each transition has specific cleanup logic (e.g., GRID→HOLD converts active orders to hold position; HOLD→CASH tightens trailing stop to 3%).

**Config**: `HybridConfig` (`src/core/hybrid_config.py`) loaded from `HYBRID_*` env vars. Key settings:
```
HYBRID_INITIAL_MODE, HYBRID_ENABLE_MODE_SWITCHING, HYBRID_TOTAL_INVESTMENT,
HYBRID_MAX_SYMBOLS, HYBRID_MIN_POSITION_USD, HYBRID_HOLD_TRAILING_STOP_PCT,
HYBRID_MODE_COOLDOWN_HOURS, HYBRID_MIN_REGIME_PROBABILITY, HYBRID_MIN_REGIME_DURATION_DAYS
```

### Singleton Pattern

New singletons must extend `SingletonMixin` from `src/utils/singleton.py`:

```python
from src.utils.singleton import SingletonMixin

class MyService(SingletonMixin):
    def __init__(self): ...
    def close(self):  # optional — called by reset_instance()
        ...

svc = MyService.get_instance()
MyService.reset_instance()  # calls close() if defined
```

`__init_subclass__` ensures each subclass gets its own `_instance`. Tests use the `reset_new_singletons` fixture which recursively resets ALL `SingletonMixin` subclasses.

**Legacy singletons** (not migrated): `AppConfig` / `get_config()` in `src/core/config.py`. Uses a module-level `_config` variable with a `get_config()` factory function (dataclass with `from_env()` doesn't fit `SingletonMixin`). Reset via the `reset_singletons` fixture.

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

### Trade Pair Tracking

`TradePairTracker` (`src/data/trade_pairs.py`) links BUY fills to SELL fills for realized P&L:
- On BUY fill: `open_pair(symbol, trade_id, price, qty, fee)` → creates open pair in `trade_pairs` table
- On SELL fill: `close_pair(symbol, trade_id, price, qty, fee)` → closes oldest open pair (FIFO), calculates P&L
- On stop-loss/cash exit: `close_pairs_by_symbol(symbol, price, qty, reason)` → closes all open pairs

Initialized in `GridBot.__init__()` via `config["cohort_id"]`. Also used by `HybridOrchestrator` for stop-loss and cash exit P&L tracking.

### Dynamic Grid Range (ATR-based)

`DynamicGridStrategy` (`src/strategies/dynamic_grid.py`) provides ATR-based adaptive grid ranges. Instead of static cohort-level `grid_range_percent`, each symbol gets a volatility-adjusted range.

**Integration flow** (Range-Bridge pattern — DynamicGridStrategy calculates range, GridStrategy handles Decimal precision):
```
DynamicGridStrategy.calculate_dynamic_range(symbol, price, base_range, regime)
    → ATR → adjusted_spacing (0.5-2.0x ATR factor + regime multiplier)
        → HybridOrchestrator._create_grid_bot(grid_range_percent=dynamic_pct)
            → GridBot.initialize() → GridStrategy(lower, upper, ...) [unchanged]
```

**Grid rebuild**: `_execute_grid()` checks every 30 min if price has drifted near or outside grid range (10% margin). If so, cancels orders and recreates the grid with a fresh ATR-based range.

**OHLCV source**: Uses mainnet Binance API (`api.binance.com/api/v3/klines`) for real market volatility, even when trading on testnet. 5-minute cache per symbol.

**Fallback**: If OHLCV fetch fails, falls back to the static `HybridConfig.grid_range_percent`.

### Grid Strategy Logic

1. Calculate grid levels: `spacing = (upper - lower) / num_grids`
2. Each level gets `investment_per_grid / price` quantity
3. Validate against Binance min_qty and min_notional (percentage-based price matching: 0.1% tolerance)
4. On BUY fill → place SELL at next higher level
5. On SELL fill → place BUY at next lower level
6. Fee handling: `TAKER_FEE_RATE` from `grid_strategy.py` applied to sell quantities

### Stop-Loss Execution

All stop-loss market sells go through `execute_stop_loss_sell()` in `src/risk/stop_loss_executor.py`:
1. Queries actual balance to avoid selling more than held
2. Rounds quantity to `step_size`
3. Retries up to 3 times with backoff (2s, 5s, 10s). On `INSUFFICIENT_BALANCE`: re-fetches actual balance and retries with reduced quantity
4. On total failure: CRITICAL log + Telegram alert ("Manual sell needed")
5. Returns `{"success": bool, "order": dict|None, "error": str|None}`

**Fee-adjusted stop-loss quantities**: When creating stop-losses for BUY fills, the quantity is reduced by `TAKER_FEE_RATE` (0.1%) to prevent `INSUFFICIENT_BALANCE` when the stop triggers. This applies in `check_orders()`, `_process_partial_fill()`, and downtime recovery in `load_state()`.

**Trailing distance**: `StopLossManager.create_stop()` accepts `trailing_distance: float | None`. For TRAILING stops, if not provided, `stop_percentage` is used as the trailing distance. This ensures HOLD mode (7%) and GRID mode (5%) get correct trailing percentages instead of the dataclass default (3%).

**Two-phase stop-loss lifecycle** in `src/risk/stop_loss.py`:
- `StopLossOrder.update(price)` → detects trigger condition, returns `True` but keeps stop active
- `StopLossOrder.confirm_trigger()` → deactivates after successful sell
- `StopLossOrder.reactivate()` → re-enables if sell failed

Callers (`RiskGuardMixin._check_stop_losses()`, `HybridOrchestrator._update_stop_losses()`, `task_check_stops()`) follow this pattern:
```python
if stop.update(current_price):
    result = execute_stop_loss_sell(client, symbol, stop.quantity, telegram)
    if result["success"]:
        stop.confirm_trigger()
    else:
        stop.reactivate()
```

### Multi-Coin Trading Pipeline

1. **WatchlistManager** maintains coin universe (25+ coins in 6 categories: LARGE_CAP, MID_CAP, L2, DEFI, AI, GAMING)
2. **CoinScanner** scores opportunities on 5 dimensions: technical (30%), volume (20%), sentiment (15%), whale (15%), momentum (20%)
3. **PortfolioAllocator** distributes capital via Kelly Criterion with regime-aware constraints
4. Constraint presets in `src/portfolio/constraints.py`: `CONSERVATIVE_CONSTRAINTS`, `BALANCED_CONSTRAINTS`, `AGGRESSIVE_CONSTRAINTS`, `SMALL_PORTFOLIO_CONSTRAINTS`
5. ModeManager selects constraints based on current mode (HOLD→aggressive, GRID→balanced/small, CASH→conservative)

### Scheduled Tasks (`src/tasks/`)

Tasks are organized in domain-specific modules under `src/tasks/`, registered by `docker/scheduler.py`:

| Module | Tasks |
|--------|-------|
| `hybrid_tasks.py` | Mode evaluation (hourly), hybrid rebalance (6h) |
| `portfolio_tasks.py` | Watchlist update (30min), opportunity scan (2h), portfolio rebalance (daily), coin performance (daily) |
| `analysis_tasks.py` | Regime detection (4h), signal weights (daily), divergence scan (2h), pattern learning (daily) |
| `cycle_tasks.py` | Cycle management (weekly), weekly rebalance, A/B test check (daily) |
| `data_tasks.py` | ETF flows, social sentiment, token unlocks, whale checks |
| `market_tasks.py` | Market snapshots (hourly), sentiment checks (4h) |
| `reporting_tasks.py` | Daily summary, playbook update (weekly), weekly export |
| `system_tasks.py` | Stop-loss check (5min), health check (6h), macro events, outcome updates |
| `monitoring_tasks.py` | Order reconciliation (30min), order timeout (1h), portfolio plausibility (2h), grid health (4h), stale detection (30min) |

Shared infrastructure in `src/tasks/base.py` provides `get_db_connection()`. All tasks use `@task_locked` from `src/utils/task_lock.py` to prevent concurrent execution (non-blocking skip).

### Utilities (`src/utils/`)

- `singleton.py` — `SingletonMixin` base class (see Singleton Pattern above)
- `task_lock.py` — `@task_locked` decorator for scheduled tasks
- `heartbeat.py` — `touch_heartbeat()` creates `data/heartbeat` for Docker health checks. Used by both `GridBot.tick()` and `HybridOrchestrator.tick()`

### Task Locking

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
- Circuit breaker: >10% flash crash triggers emergency stop (initialized with current price in `initialize()` to prevent false trigger on first tick)

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
- `scheduler` - Background tasks (see Scheduled Tasks above)
- `postgres` - Trading memory database
- `redis` - Caching

## Testing Notes

Tests use fixtures from `tests/conftest.py`:
- `mock_env_vars` (autouse) - Sets all required env vars (BINANCE_TESTNET, TRADING_PAIR, etc.)
- `bot` - Fully mocked GridBot (patches BinanceClient, TelegramNotifier, memory, stop-loss, risk modules)
- `bot_config` - Minimal config dict: `{"symbol": "BTCUSDT", "investment": 100, "num_grids": 3, ...}`
- `mock_binance` - MagicMock BinanceClient with sensible defaults (price 50000, balance 1000)
- `reset_singletons` - Resets AppConfig only (sole remaining legacy singleton)
- `reset_new_singletons` - Resets ALL `SingletonMixin` subclasses via recursive `__subclasses__()` walk + AppConfig
- `sample_ohlcv_data` - 100 periods OHLCV data (numpy seed 42)
- `sample_returns` - 100 days of return data
- `sample_trade_history` - 8 trades with win/loss data

Mock external APIs at module level: `@patch("src.module.get_http_client")`

Symbol info format for GridStrategy tests uses flat dict:
```python
{"symbol": "BTCUSDT", "min_qty": 0.00001, "step_size": 0.00001, "min_notional": 5.00}
```

**GridStrategy price matching**: Uses 0.1% tolerance when matching prices to grid levels. Tests that create orders at specific prices must use actual `bot.strategy.levels[N].price` values, not hardcoded numbers.

## Mandatory Documentation Maintenance

Three documentation files MUST be kept up-to-date with every change. This is not optional.

### LEARNING_PHASE.md — Learning Phase Tracking

**When to update:** After any change that is specific to the testnet/learning phase, or any change that affects production migration.

- Document temporary flags, workarounds, or test-specific settings
- Mark each entry as "Temporary" or "Permanent" with reason
- Update the production migration checklist when adding new temporary changes
- Examples: enabling/disabling features via env vars, adjusting thresholds for testing, adding skip flags

### CHANGELOG.md — Internal Change Log

**When to update:** After every commit or logical change, add an entry.

- Format: `## vX.Y.Z (YYYY-MM-DD)` with `### Feat`, `### Fix`, `### Refactor` subsections
- Keep entries concise (one line per change)
- Version is bumped automatically by commitizen on release

### TODO.md — Development Roadmap

**When to update:** After completing any phase/task listed in the file, or when identifying new work items.

- Mark completed items with `[x]`
- Add new phases or tasks as they emerge
- Update the test count and status line when tests change significantly
- Review periodically to identify tasks that can now be implemented
