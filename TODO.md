# Trading Bot - Hybrid Multi-Coin System

## Status: Testnet Learning Phase
## Ziel: Regime-adaptives Hybrid-Trading-System mit Multi-Strategie Cohorts

### Aktueller Fokus: 6 Cohorts auf Testnet (898 Tests)

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
- [x] **7.3**: `pytest tests/ -v` alle grün (898 tests passed)
- [x] **7.4**: `ruff check src/ tests/ docker/` keine Fehler
- [x] **7.5**: `mypy src/` keine Fehler (63 source files)
- [ ] **7.6**: 2 Wochen Testnet mit `enable_mode_switching=false` (Multi-Coin GRID)
- [ ] **7.7**: Dann `enable_mode_switching=true` aktivieren

## Phase 8: Cohort-System (A/B Testing)

- [x] **8.1**: CohortManager + CohortOrchestrator (`cohort_manager.py`, `cohort_orchestrator.py`)
- [x] **8.2**: HybridConfig.from_cohort() mit Risk-Mapping
- [x] **8.3**: Kategorie-basierte Coin-Differenzierung (LARGE_CAP, MID_CAP, DEFI, etc.)
- [x] **8.4**: Symbol-Exclusion zwischen Cohorts (unique Coins pro Bot)
- [x] **8.5**: Pre-Feasibility-Filter im Allocator
- [x] **8.6**: Telegram /report mit DB-basiertem P&L
- [x] **8.7**: Decimal-Type-Fix in Report und RiskGuard
- [x] **8.8**: SingletonMixin Migration (HTTPClient, alle Services)

## Phase 9: Small-Cap Expansion + Dashboard (aktuell)

- [x] **9.1**: Report-Dashboard Redesign mit Emojis
- [x] **9.2**: `allowed_categories` Override in CohortConfig
- [x] **9.3**: 2 neue Cohorts: defi_explorer + meme_hunter
- [x] **9.4**: 12 neue Watchlist-Coins (MEME, DEFI, AI)
- [x] **9.5**: MEME-Kategorie in Constraints
- [ ] **9.6**: Deploy + Verifikation (6 Cohorts mit unique Coins)

---

## Spätere Verbesserungen (während Testmonate)

### Priorität A: Nächste Features

- [ ] **E1: Auto-Discovery** — Automatische Watchlist-Erweiterung
  - `BinanceClient.get_all_tickers()` Methode
  - Scheduled Task (1x täglich): Alle USDT-Paare scannen
  - Filter: Min. 24h-Volume, Marktkapitalisierung, Testnet-Verfügbarkeit
  - Kategorisierung: Marketcap → LARGE/MID/SMALL, Sektor → DEFI/AI/MEME/etc.
  - `WatchlistManager.add_coin()` für dynamisches Hinzufügen
  - Inaktive/illiquide Coins automatisch deaktivieren

- [ ] **E2**: Unrealized P&L im Report (Live-Bewertung der offenen Positionen)
- [ ] **E3**: Performance-Vergleich zwischen Cohorts (welche Strategie gewinnt?)

### Priorität B: Optimierungen

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

### Priorität C: Ungenutzte DB-Tabellen aktivieren

- [ ] **F1: portfolio_snapshots Writer** — Equity-Kurve + Performance-Tracking (HOCH)
  - Tabelle existiert in init.sql, MetricsCalculator.store_snapshot() existiert
  - Braucht: Scheduler-Task der regelmäßig Portfolio-Wert berechnet und speichert
  - Mehrwert: Langzeit-Performance-Messung, Drawdown-Erkennung

- [ ] **F2: technical_indicators Writer** — Historische Indikator-Daten (MITTEL)
  - Tabelle existiert (RSI, MACD, BB, SMA, ATR pro Symbol)
  - Braucht: Neuer Scheduler-Task + Writer-Code (TechnicalIndicators Klasse erweitern)
  - Mehrwert: Playbook-Lernen, Signal-Validierung, AI-Training, Dashboard-Kontext

- [ ] **F3: economic_events Writer** — Makro-Event-Awareness (NIEDRIG)
  - Tabelle existiert, task_macro_check scheduled aber schreibt nicht in DB
  - Braucht: Writer in task_macro_check, API-Quelle für Events (z.B. investing.com)
  - Mehrwert: Automatische Positionsreduktion vor wichtigen Events (Fed, CPI)

- [ ] **F4: ai_conversations Writer** — Telegram Chat-Log (MINIMAL)
  - Tabelle existiert für AI-Chat-History
  - Braucht: Integration in Telegram AI-Handler
  - Mehrwert: Minimal — nur Konversations-Logging, kein Trading-Mehrwert

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
| 8     | 8     | 8        | done   |
| 9     | 6     | 5        | active |

## Deployment-Strategie

1. Phase 0-3: Keine Änderung am laufenden System
2. Phase 4-5: main_hybrid.py als separater Entry Point (altes main.py bleibt)
3. Phase 6: Docker-Compose umstellen auf hybrid
4. Phase 7: Testnet mit mode_switching=false, dann true
5. Phase 8: Cohort-System mit 4 Strategien ($1000 je)
6. Phase 9: 6 Cohorts + Small-Cap/Meme Expansion
