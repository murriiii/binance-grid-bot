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
