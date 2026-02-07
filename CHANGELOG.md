## v1.20.0 (2026-02-07)

### Feat (Priorität B+C: 13 Optimierungen)

- C1: Multi-dimensional RAG similarity scoring (Gaussian F&G, regime, symbol, temporal decay)
- C2: CHECK constraints (9 columns), composite indexes (5), retention indexes (8), UNIQUE on economic_events
- C3: AI signal validation (enum, confidence clamp, semantic consistency, reasoning quality)
- C4: Sentiment source-availability dampening, volume-threshold dampening, divergence detection
- D1: Fee-aware grid spacing warning + MIN_PROFITABLE_SPACING_PCT classmethod
- D2: Data retention auto-cleanup task (8 tables, configurable retention days)
- D3: Dynamic grid count by ATR volatility regime (LOW=7, NORMAL=10, HIGH=12, EXTREME=15)
- D4: Slippage tracking in trades table (expected_price, slippage_bps)
- D5: Funding rate signal from Binance Futures API (5min cache)
- D6: Correlation matrix from 60-day daily returns + allocator penalty for correlated pairs
- F2: technical_indicators writer task (every 2h, watchlist symbols)
- F3: economic_events writer in task_macro_check (ON CONFLICT dedup)
- F4: ai_conversations writer in DeepSeekAssistant.ask()

## v1.15.0 (2026-02-07)

### Feat

- implement Phase 10-12 — AI Learning Loop, 3-Tier Portfolio, Production Readiness
- integrate DynamicGridStrategy, activate SignalAnalyzer + MetricsCalculator, use SchedulerConfig
- add trade pairs tracking, dashboard BUY/SELL split, stale detection
- add monitoring tasks, fix Decimal precision bug, document learning phase

### Fix

- increase grid activity — 6 fixes for low fill rates on testnet

## v1.14.5 (2026-02-06)

### Fix

- disable portfolio drawdown check in hybrid/cohort mode

## v1.14.4 (2026-02-06)

### Fix

- show open order counts instead of 0 trades in dashboard footer

## v1.14.3 (2026-02-06)

### Fix

- report uses grid state instead of account balance, suppress urgent spam

## v1.14.2 (2026-02-06)

### Fix

- enforce learning mode for all Telegram notifications

## v1.14.1 (2026-02-06)

### Fix

- increase allocation limits and add live unrealized P&L to dashboard

## v1.14.0 (2026-02-06)

### Feat

- add 2 small-cap cohorts, emoji dashboard report, MEME category

## v1.13.0 (2026-02-06)

### Feat

- unique coins per cohort + $1000 budget for learning phase

## v1.12.0 (2026-02-06)

### Feat

- add category-based coin differentiation per cohort risk level

## v1.11.0 (2026-02-06)

### Feat

- add min_confidence filtering for cohort coin differentiation

## v1.10.3 (2026-02-06)

### Fix

- show correct cohort portfolio breakdown with cash reserve

## v1.10.2 (2026-02-06)

### Fix

- resolve Decimal type error and per-cohort balance in /report

## v1.10.1 (2026-02-06)

### Fix

- mount hybrid_state volume in telegram-handler container

## v1.10.0 (2026-02-06)

### Feat

- add /report command for on-demand cohort status

## v1.19.0 (2026-02-07)

### Feat (Phase 12: Production Readiness)

- ProductionValidator with 9 go-live criteria (min trades, Sharpe, drawdown, win rate, etc.)
- GoLiveChecklist with 4 deployment phases (Paper → Alpha $1K → Beta $3K → Production $5K+)
- Telegram /validate command for production readiness check
- Daily production validation scheduler task (09:00)
- 20 tests for Phase 12

## v1.18.0 (2026-02-07)

### Feat (Phase 11: 3-Tier Portfolio Management)

- DB schema: portfolio_tiers, tier_allocation_history, index_holdings, profit_redistributions, ai_portfolio_recommendations
- PortfolioManager: top-level 3-tier orchestrator with PORTFOLIO_MANAGER feature flag
- CashReserveTier: USDT safety buffer (10%, underfunded/overfunded thresholds)
- IndexHoldingsTier: CMC Top 20 buy-and-hold with quarterly rebalance, 15% trailing stops
- TradingTier: CohortOrchestrator wrapper with capital budget scaling
- ProfitRedistributionEngine: weekly tier rebalancing when drift > 3%
- AIPortfolioOptimizer: monthly DeepSeek allocation with guard rails (learning mode, auto-apply)
- CoinGecko market cap API client for index composition
- Telegram /portfolio command with tier breakdown and drift display
- Tier health check task (2h), profit redistribution (weekly), AI optimizer (monthly)
- Tier section in daily summary report
- 53 tests for Phase 11

## v1.17.0 (2026-02-07)

### Feat (Phase 10: AI Learning Loop Fix)

- Signal correctness evaluation: populate signal_components.was_correct (6h scheduler task)
- Trade decision quality: populate trades.was_good_decision via trade_pairs P&L (daily task)
- Multi-timeframe outcomes: outcome_1h (hourly), outcome_4h (4h), outcome_7d (daily) alongside existing 24h
- Discovery evaluation accelerated from 30 to 7 days
- Signal accuracy integrated into Playbook (top signals by reliability per regime)
- Regime-stratified Playbook rules (separate BULL/BEAR/SIDEWAYS sections)
- Portfolio snapshots task (hourly) for equity curve tracking
- 31 tests for Phase 10

## v1.16.0 (2026-02-07)

### Feat

- E2: per-coin unrealized P&L in dashboard (cost basis from open trade_pairs)
- E3: cohort comparison ranking with /compare Telegram command + daily summary integration
- E1: AI-enhanced auto-discovery with DeepSeek feedback loop (coin_discoveries table, learning from past decisions)
- E4: paper trading client (PaperBinanceClient) with real mainnet prices and simulated order matching
- E5: monitoring extensions — paper-mode awareness, discovery health check task, stale detection tests
- E6: client.client.get_open_orders refactored to client.get_open_orders, paper-mode in reporting

## v1.15.0 (2026-02-07)

### Fix

- increase NUM_GRIDS from 3 to 5: doubles fill opportunities (6 levels instead of 4)
- save state immediately after place_initial_orders() to prevent orphaned "unknown" orders
- add startup order reconciliation: cancels Binance orders not tracked in local state
- increase grid rebuild interval from 30min to 60min, tighten margin from 10% to 5%
- reduce ATR regime multipliers: BEAR 1.3→1.1, TRANSITION 1.2→1.0 to prevent grid over-expansion
- fix price formatting for micro-price coins (PEPE/SHIB/BONK): dynamic precision instead of fixed .4f

## v1.14.9 (2026-02-06)

### Feat

- integrate DynamicGridStrategy: ATR-based grid ranges per symbol replace static cohort percentages
- auto grid rebuild when price drifts near or outside grid range (30 min check interval)
- activate MetricsCalculator: Sharpe/CVaR/Kelly snapshots stored in daily summary
- activate SignalAnalyzer: 9-signal composite breakdown stored per trade fill
- scheduler reads from SchedulerConfig instead of hardcoded times/intervals

### Docs

- TODO.md: add F1-F4 unused DB tables (portfolio_snapshots, technical_indicators, economic_events, ai_conversations)

## v1.14.8 (2026-02-06)

### Feat

- add trade pair tracking: BUY→SELL pairs with realized P&L (gross, net, hold duration)
- dashboard footer shows BUY/SELL order split (e.g. "174 Orders (90B/84S)")
- add stale detection monitoring: alert if no order activity for 30 min
- write fee_usd to trades table for accurate cost tracking

## v1.14.7 (2026-02-06)

### Fix

- fix P&L calculation: include BUY order cost basis + SELL order market value instead of always showing ±0.0%
- allow MID_CAP coins for conservative cohort (was LARGE_CAP only, too few coins on testnet)

## v1.14.6 (2026-02-06)

### Fix

- fix Decimal precision bug in _to_decimal causing order placement failures for low-price coins (FET, CRV, ARB, ADA)

### Feat

- add 4 monitoring tasks: order reconciliation, order timeout, portfolio plausibility, grid health summary
- add LEARNING_PHASE.md documenting all testnet-specific configuration changes
- scheduler now has Binance API keys, hybrid_state volume, and Redis access
- CLAUDE.md: add mandatory documentation maintenance instructions for LEARNING_PHASE.md, CHANGELOG.md, TODO.md

## v1.14.5 (2026-02-06)

### Fix

- disable portfolio drawdown check in hybrid/cohort mode

## v1.14.4 (2026-02-06)

### Fix

- show open order counts instead of 0 trades in dashboard footer

## v1.14.3 (2026-02-06)

### Fix

- report uses grid state instead of account balance, suppress urgent spam

## v1.14.2 (2026-02-06)

### Fix

- enforce learning mode for all Telegram notifications

## v1.14.1 (2026-02-06)

### Fix

- increase allocation limits and add live unrealized P&L to dashboard

## v1.14.0 (2026-02-06)

### Feat

- add 2 small-cap cohorts, emoji dashboard report, MEME category

## v1.13.0 (2026-02-06)

### Feat

- unique coins per cohort + $1000 budget for learning phase

## v1.12.0 (2026-02-06)

### Feat

- add category-based coin differentiation per cohort risk level

## v1.11.0 (2026-02-06)

### Feat

- add min_confidence filtering for cohort coin differentiation

## v1.10.3 (2026-02-06)

### Fix

- show correct cohort portfolio breakdown with cash reserve

## v1.10.2 (2026-02-06)

### Fix

- resolve Decimal type error and per-cohort balance in /report

## v1.10.1 (2026-02-06)

### Fix

- mount hybrid_state volume in telegram-handler container

## v1.10.0 (2026-02-06)

### Feat

- add /report command for on-demand cohort status

## v1.9.0 (2026-02-06)

### Feat

- implement cohort-based multi-bot system with 4 parallel strategies

## v1.8.3 (2026-02-06)

### Fix

- resolve mypy errors and raise test coverage to 60%

## v1.8.2 (2026-02-06)

### Fix

- pre-testphase hardening — 18 issues across 3 phases

### Refactor

- consolidate singleton test fixtures
- migrate HTTPClient to SingletonMixin
- migrate CoinScanner to SingletonMixin
- migrate WatchlistManager to SingletonMixin
- migrate DatabaseManager to SingletonMixin

## v1.8.1 (2026-02-06)

### Fix

- pre-testphase hardening — 13 issues across 6 phases

## v1.8.0 (2026-02-06)

### Fix

- production readiness — stop-loss safety, SIGTERM, Docker infra, DB consolidation

## v1.7.1 (2026-02-06)

### Refactor

- decompose GridBot into OrderManager, StateManager, RiskGuard
- split scheduler.py into domain-specific task modules
- extract SingletonMixin, consolidate test fixtures

## v1.7.0 (2026-02-06)

### Feat

- add regime-adaptive Hybrid Trading System (HOLD/GRID/CASH)

## v1.6.0 (2026-02-05)

### Feat

- complete Phase A - all critical pre-testing fixes

## v1.5.1 (2026-02-05)

### Refactor

- centralize HTTP requests through HTTPClient

## v1.5.0 (2026-02-05)

### Feat

- add Phase 6 Multi-Coin Trading System

## v1.4.0 (2026-02-05)

### Feat

- add LEARNING_MODE for reduced notifications

## v1.3.2 (2026-02-05)

### Fix

- remove all remaining mock data from production code

## v1.3.1 (2026-02-05)

### Fix

- remove mock data from production code

## v1.3.0 (2026-02-05)

### Feat

- add comprehensive trading bot enhancement (Phase 1-5)

## v1.2.0 (2026-02-05)

### Feat

- add comprehensive logging system and weekly analysis export
- add Trading Playbook learning system

## v1.1.1 (2026-02-05)

### Fix

- add RUF059 to ignore list and enable GitHub releases

## v1.1.0 (2026-02-05)

### Feat

- Initial release of Binance Grid Trading Bot

### Fix

- resolve ruff linting errors and add comprehensive test suite
