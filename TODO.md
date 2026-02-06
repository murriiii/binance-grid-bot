# Trading Bot - Hybrid System Umbau

## Status: In Progress
## Ziel: Regime-adaptives Hybrid-Trading-System

### Aktueller Fokus: Phase 7 abgeschlossen - Deploy vorbereiten

---

## Phase A: KRITISCH - Erledigt

- [x] **A1**: Risk Enforcement in Order-Pipeline (`bot.py`)
- [x] **A2**: Partial-Fill-Handling (`bot.py`)
- [x] **A3**: Downtime-Fill-Recovery (`bot.py`)
- [x] **A4**: Stop-Loss in DB persistieren (`bot.py`, `stop_loss.py`)
- [x] **A5**: Float → Decimal für Crypto-Quantities (`grid_strategy.py`, `binance_client.py`)
- [x] **A6**: Binance Rate-Limit Error-Codes fixen (`binance_client.py`)
- [x] **A7**: Fee-Berechnung einbauen (`bot.py`, `grid_strategy.py`)

## Phase 0: Prerequisites (Bugfixes + Grundlagen)

- [x] **0.1**: B1 - Price-Matching prozentual statt 0.01 (`grid_strategy.py`)
- [x] **0.2**: B2 - Cycle-Duration .days Bug (`cycle_manager.py`)
- [x] **0.3**: B5 - Connection Leaks fixen (diverse Singletons)
- [x] **0.4**: B7 - Kelly Confidence Double-Counting (`cvar_sizing.py`)
- [x] **0.5**: C5 - Regime-Detection None-Handling (`scheduler.py`)
- [x] **0.6**: C6 - Scanner Division-by-Zero (`coin_scanner.py`)
- [x] **0.7**: SMALL_PORTFOLIO_CONSTRAINTS Preset (`constraints.py`)

## Phase 1: Foundation - Neue Typen und Config

- [x] **1.1**: TradingMode Enum + ModeState/ModeTransitionEvent Dataclasses (`trading_mode.py`)
- [x] **1.2**: HybridConfig Dataclass + Integration in AppConfig (`hybrid_config.py`, `config.py`)
- [x] **1.3**: DB-Schema: trading_mode_history Tabelle (`init.sql`)
- [x] **1.4**: Tests für Phase 1 (`test_trading_mode.py`, `test_hybrid_config.py`)

## Phase 2: Mode Management

- [x] **2.1**: ModeManager Singleton mit Hysteresis-Logik (`mode_manager.py`)
- [x] **2.2**: PortfolioAllocator regime-aware machen (`allocator.py`)
- [x] **2.3**: Tests für ModeManager (`test_mode_manager.py`)

## Phase 3: GridBot Refactoring

- [x] **3.1**: tick() Methode aus run() extrahieren (`bot.py`)
- [x] **3.2**: Optionaler externer BinanceClient (`bot.py`)
- [x] **3.3**: Bestehende Tests weiterhin grün + neue tick() Tests

## Phase 4: HybridOrchestrator

- [x] **4.1**: Orchestrator-Klasse mit Main-Loop (`hybrid_orchestrator.py`)
- [x] **4.2**: HOLD-Modus: Buy + Trailing Stop
- [x] **4.3**: GRID-Modus: Delegiert an GridBot.tick() pro Symbol
- [x] **4.4**: CASH-Modus: Cancel + Sell
- [x] **4.5**: 6 Transition-Pfade (GRID<->HOLD, GRID<->CASH, HOLD<->CASH)
- [x] **4.6**: State-Persistenz (hybrid_state.json)
- [x] **4.7**: Tests für Orchestrator (`test_hybrid_orchestrator.py`)

## Phase 5: Multi-Coin Integration

- [x] **5.1**: CoinScanner + Allocator in Orchestrator integrieren
- [x] **5.2**: Per-Symbol GridBot mit shared BinanceClient
- [x] **5.3**: Kapital-Rebalancing (alle 6h, >5% Abweichung)

## Phase 6: Entry Point und Scheduler

- [x] **6.1**: main_hybrid.py Entry Point
- [x] **6.2**: Scheduler: Mode-Evaluation (1h) + Rebalance (6h) + Task-Locking (B3)
- [x] **6.3**: Telegram: Mode-Switch Notifications + Message-Length Validation (B4)
- [x] **6.4**: Docker-Compose Update

## Phase 7: Testing und Verifikation

- [x] **7.1**: B6 - DynamicGrid Cache Memory-Leak fixen (`dynamic_grid.py`)
- [x] **7.2**: Integration Tests (Full-Lifecycle, Multi-Coin, Transitions) (`test_integration.py`)
- [x] **7.3**: `pytest tests/ -v` alle grün (508 tests passed)
- [x] **7.4**: `ruff check src/ tests/ docker/` keine Fehler
- [x] **7.5**: `mypy src/` keine Fehler (63 source files)
- [ ] **7.6**: 2 Wochen Testnet mit `enable_mode_switching=false` (Multi-Coin GRID)
- [ ] **7.7**: Dann `enable_mode_switching=true` aktivieren

## Spätere Verbesserungen (während Testmonate)

- [ ] C1: RAG-Similarity verbessern (`memory.py`)
- [ ] C2: DB Retention + Indexes + Constraints (`init.sql`)
- [ ] C3: AI-Output validieren (`ai_enhanced.py`)
- [ ] C4: Sentiment Single-Source Dampening (`social_sentiment.py`)
- [ ] D1: Fee-Aware Grid Calculation
- [ ] D2: Data Retention Auto-Cleanup
- [ ] D3: Dynamic Grid Count basierend auf ATR
- [ ] D4: Slippage Tracking
- [ ] D5: Funding Rate Signal
- [ ] D6: Echte Korrelations-Matrix

---

## Fortschritt

| Phase | Items | Erledigt | Status |
|-------|-------|----------|--------|
| A     | 7     | 7        | done   |
| 0     | 7     | 7        | done   |
| 1     | 4     | 4        | done   |
| 2     | 3     | 3        | done   |
| 3     | 3     | 3        | done   |
| 4     | 7     | 7        | done   |
| 5     | 3     | 3        | done   |
| 6     | 4     | 4        | done   |
| 7     | 7     | 5        | deploy |

## Deployment-Strategie

1. Phase 0-3: Keine Änderung am laufenden System
2. Phase 4-5: main_hybrid.py als separater Entry Point (altes main.py bleibt)
3. Phase 6: Docker-Compose umstellen auf hybrid
4. Phase 7: Testnet mit mode_switching=false, dann true
