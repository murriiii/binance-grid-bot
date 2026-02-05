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

# Run backtest
python run_backtest.py
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

Critical shared resources use the singleton pattern:
- `get_config()` - Global configuration from environment
- `get_http_client()` - Centralized HTTP with retry/caching
- `TelegramService.get_instance()` - Notification service
- `MarketDataProvider.get_instance()` - Price data with caching

### Key Modules

| Module | Purpose |
|--------|---------|
| `src/core/bot.py` | Main GridBot orchestrator with error recovery |
| `src/core/config.py` | Dataclass configs loaded from env vars |
| `src/strategies/grid_strategy.py` | Grid level calculation and order logic |
| `src/data/memory.py` | PostgreSQL-based trading memory (RAG pattern) |
| `src/data/sentiment.py` | Fear & Greed Index, social sentiment |
| `src/data/playbook.py` | Self-learning Trading Playbook generator |
| `src/risk/stop_loss.py` | Stop-loss management (fixed, trailing, ATR) |
| `src/strategies/ai_enhanced.py` | DeepSeek AI integration with fallbacks |
| `src/core/logging_system.py` | Structured JSON logging (TradingLogger) |
| `src/analysis/weekly_export.py` | Weekly analysis export for optimization |

### Grid Strategy Logic

1. Calculate grid levels: `spacing = (upper - lower) / num_grids`
2. Each level gets `investment_per_grid / price` quantity
3. Validate against Binance min_qty and min_notional
4. On BUY fill → place SELL at next higher level
5. On SELL fill → place BUY at next lower level

### Data Flow

Trades are stored with full context in PostgreSQL:
- Entry conditions (fear_greed, btc_price, trend)
- Decision signals (math_signal, ai_signal, confidence)
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

### Weekly Analysis Export

Automatic export every Saturday 23:00 to `analysis_exports/week_YYYYMMDD/`:
- `analysis_export.json` - Structured performance data
- `ANALYSIS_REPORT.md` - Human-readable summary
- Used for Claude Code optimization workflow

### External APIs

| API | Module | Notes |
|-----|--------|-------|
| Binance | `src/api/binance_client.py` | Rate limited (1000/min) |
| DeepSeek | `src/strategies/ai_enhanced.py` | 30s timeout, 3 retries |
| Alternative.me | `src/data/sentiment.py` | Fear & Greed Index |
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
- `scheduler` - Background tasks (daily summaries, market snapshots, playbook updates, weekly exports)
- `postgres` - Trading memory database
- `redis` - Caching

### Key Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| Pattern Learning | 21:00 daily | Analyze new trades |
| Playbook Update | Sun 19:00 | Generate new playbook |
| Weekly Export | Sat 23:00 | Create analysis export |
| Outcome Update | Every 6h | Update trade outcomes |

## Testing Notes

Tests use fixtures from `tests/conftest.py`:
- `reset_singletons` - Resets all singleton instances between tests
- `mock_env_vars` - Sets test environment variables
- Sample response fixtures for API mocking

Symbol info format for GridStrategy tests uses flat dict:
```python
{"symbol": "BTCUSDT", "min_qty": 0.00001, "step_size": 0.00001, "min_notional": 5.00}
```
