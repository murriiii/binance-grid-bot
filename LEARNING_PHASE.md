# Learning Phase - Testnet Configuration

This document tracks all configuration changes made during the testnet learning phase.
Each entry specifies whether it's **temporary** (must be changed for production) or
**permanent** (intentional design decision that stays).

## Active Changes

### 1. LEARNING_MODE=true (Temporary)

**Where:** `.env` / `docker-compose.yml` (all services)
**Effect:** Suppresses most Telegram notifications. Only critical messages (errors,
stop-loss triggers, startup/shutdown) are sent via `force=True`.
**Production:** Set `LEARNING_MODE=false` in `.env`.

### 2. skip_portfolio_drawdown: True (Permanent)

**Where:** `src/core/hybrid_orchestrator.py` — `_create_grid_bot()` sets this in bot_config.
Also checked in `src/core/bot.py` (tick) and `src/core/risk_guard.py` (_validate_order_risk).
**Effect:** Disables portfolio-wide drawdown check for individual GridBots in hybrid/cohort mode.
**Reason:** Multiple GridBots share one Binance account. Each bot's locked USDT appears as
"lost capital" to the others, causing false drawdown triggers.
**Production:** Stays as-is. HybridOrchestrator has its own stop-loss management per cohort.

### 3. HYBRID_ENABLE_MODE_SWITCHING=false (Temporary)

**Where:** `.env` / `docker-compose.yml` L85
**Effect:** Locks all cohorts in GRID mode. No HOLD/CASH transitions.
**Reason:** Learning phase — observe grid behavior before enabling regime-adaptive switching.
**Production:** Set `HYBRID_ENABLE_MODE_SWITCHING=true`.

### 4. HYBRID_CONSTRAINTS_PRESET=small (Temporary)

**Where:** `.env` / `docker-compose.yml` L89
**Effect:** Uses SMALL_PORTFOLIO_CONSTRAINTS (higher single-asset caps: 40% vs 25%).
**Reason:** Small testnet capital ($1000/cohort) needs relaxed allocation limits.
**Production:** Set `HYBRID_CONSTRAINTS_PRESET=balanced` (or `conservative` for real capital).

### 5. NUM_GRIDS=5 (Temporary)

**Where:** `.env` / `docker-compose.yml` L92
**Effect:** 5 grid levels per symbol (6 total levels: 3 BUY + 3 SELL).
**Reason:** Increased from 3 to 5 — with NUM_GRIDS=3 only 4 levels were created (2 BUY + 2 SELL)
with 3.33% spacing, causing very low fill rates. NUM_GRIDS=5 gives 1.67% spacing at 5% range.
$24/level still meets min_notional.
**Production:** Increase to 7-10 depending on investment per symbol.

### 6. HYBRID_MAX_SYMBOLS=4 (Temporary)

**Where:** `.env` / `docker-compose.yml` L88
**Effect:** Each cohort trades max 4 coins simultaneously.
**Reason:** $1000/cohort / 4 symbols = $250/symbol, barely enough for 3 grid levels.
**Production:** Increase to 6-8 with larger capital.

### 7. BINANCE_TESTNET=true (Temporary)

**Where:** `.env` / `docker-compose.yml` L24
**Effect:** All Binance API calls go to testnet (no real money).
**Reason:** Learning phase — validate strategy before risking capital.
**Production:** Set `BINANCE_TESTNET=false` and configure production API keys
(`BINANCE_API_KEY`, `BINANCE_API_SECRET`).

### 8. HYBRID_TOTAL_INVESTMENT=400 per Cohort (Temporary)

**Where:** `.env` / `docker-compose.yml` L86
**Effect:** Each HybridOrchestrator instance allocates max $400 across its symbols.
**Reason:** Testnet capital is limited; $400 per cohort keeps allocations reasonable.
**Production:** Increase to actual investment amount per cohort.

### 9. Cohort starting_capital: $1000 (Temporary)

**Where:** DB `cohorts` table, also in `src/core/cohort_manager.py` defaults.
**Effect:** Each cohort starts with $1000 virtual capital.
**Reason:** Testnet testing amount.
**Production:** Update DB records and default config to match real capital allocation.

### 10. TelegramNotifier.send() no force=True for urgent (Permanent)

**Where:** `src/core/bot.py` — `TelegramNotifier.send()` method
**Effect:** Urgent messages (emergency stops etc.) respect LEARNING_MODE and are suppressed.
**Reason:** In learning mode, emergency stops fire frequently (false positives from shared
account drawdown). The learning mode gate in TelegramService handles force correctly.
**Production:** Stays as-is. When LEARNING_MODE=false, all messages are sent normally.

---

## Production Migration Checklist

Follow this order when switching to production:

```
1. [ ] Stop all Docker containers
       cd docker && docker compose --profile hybrid down

2. [ ] Update .env file:
       BINANCE_TESTNET=false
       BINANCE_API_KEY=<production key>
       BINANCE_API_SECRET=<production secret>
       LEARNING_MODE=false
       HYBRID_ENABLE_MODE_SWITCHING=true
       HYBRID_CONSTRAINTS_PRESET=balanced
       HYBRID_TOTAL_INVESTMENT=<real amount per cohort>
       HYBRID_MAX_SYMBOLS=6
       NUM_GRIDS=5

3. [ ] Update DB cohort capital:
       UPDATE cohorts SET starting_capital = <real_amount>;

4. [ ] Clear testnet state files:
       rm config/grid_state_*.json config/hybrid_state_*.json

5. [ ] Reset stop-loss orders:
       TRUNCATE stop_loss_orders;

6. [ ] Verify Binance production API permissions:
       - Spot trading enabled
       - IP whitelist configured
       - No withdrawal permission

7. [ ] Start with one cohort first:
       docker compose --profile hybrid up -d
       Monitor for 24h before enabling all cohorts

8. [ ] Verify monitoring tasks are running:
       docker logs trading-scheduler | grep "task_reconcile"
```

### 11. Startup Order Reconciliation (Permanent)

**Where:** `src/core/hybrid_orchestrator.py` — `_reconcile_startup_orders()` called in `run()`.
**Effect:** At startup, cancels any open orders on Binance that are not tracked in local state files.
**Reason:** Orders placed but not persisted before crash/restart remain on Binance as orphans,
blocking capital the bot doesn't know about.
**Production:** Stays as-is. Essential safety net for any environment.

### 12. Grid Rebuild Interval 60min / 5% Margin (Temporary)

**Where:** `src/core/hybrid_orchestrator.py` — `_execute_grid()` and `_should_rebuild_grid()`.
**Effect:** Grid rebuild check runs every 60 minutes (was 30) and only triggers when price is
within 5% of the grid edge (was 10%).
**Reason:** With NUM_GRIDS=5 and tighter grids, orders need more time to fill before being
cancelled by a rebuild. 30-min interval was destroying orders before they could execute.
**Production:** May adjust back to 30min with higher grid counts and more capital.

### 13. ATR Regime Multipliers Reduced (Temporary)

**Where:** `src/strategies/dynamic_grid.py` — `_calculate_adjusted_spacing()`.
**Effect:** BEAR multiplier reduced from 1.3x to 1.1x, TRANSITION from 1.2x to 1.0x.
**Reason:** High multipliers were expanding grid ranges excessively, especially for cohorts
with already wide base ranges (MEME 15%). Over-expansion reduces fill probability.
**Production:** May restore original values with larger capital and more grid levels.

## Items That Stay Unchanged

- `skip_portfolio_drawdown: True` — permanent for hybrid/cohort mode
- `TelegramNotifier.send()` without force — permanent, learning mode gate works correctly
- Monitoring tasks — permanent, useful in production too
- Startup order reconciliation — permanent, safety net for all environments
