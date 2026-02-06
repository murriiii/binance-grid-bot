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
