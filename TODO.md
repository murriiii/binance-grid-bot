# Trading Bot - Pre-Testing Fix Plan

## Status: In Progress
## Ziel: Phase A+B vor Testnet-Start abschließen

### Aktueller Fokus: Phase B - Vor Testnet-Start

---

## Phase A: KRITISCH - Ohne diese Fixes kein Live-Testing

- [x] **A5**: Float → Decimal für Crypto-Quantities (`grid_strategy.py`, `binance_client.py`)
- [x] **A6**: Binance Rate-Limit Error-Codes fixen (`binance_client.py`)
- [x] **A7**: Fee-Berechnung einbauen (`bot.py`, `grid_strategy.py`)
- [x] **A1**: Risk Enforcement in Order-Pipeline (`bot.py`)
- [x] **A2**: Partial-Fill-Handling (`bot.py`)
- [x] **A3**: Downtime-Fill-Recovery (`bot.py`)
- [x] **A4**: Stop-Loss in DB persistieren (`bot.py`, `stop_loss.py`)

## Phase B: HOCH - Vor Testnet-Start

- [ ] **B1**: Price-Matching prozentual statt 0.01 (`grid_strategy.py`)
- [ ] **B2**: Cycle-Duration .days Bug (`cycle_manager.py`)
- [ ] **B3**: Scheduler Task-Locking (`docker/scheduler.py`)
- [ ] **B4**: Telegram Message-Length Validation (`telegram_service.py`)
- [ ] **B5**: Connection Leaks fixen (diverse Singletons)
- [ ] **B6**: DynamicGrid Cache Memory-Leak (`dynamic_grid.py`)
- [ ] **B7**: Kelly Confidence Double-Counting (`cvar_sizing.py`)

## Phase C: MITTEL - Erste Testwochen

- [ ] **C1**: RAG-Similarity verbessern (`memory.py`)
- [ ] **C2**: DB Retention + Indexes + Constraints (`init.sql`)
- [ ] **C3**: AI-Output validieren (`ai_enhanced.py`)
- [ ] **C4**: Sentiment Single-Source Dampening (`social_sentiment.py`)
- [ ] **C5**: Regime-Detection None-Handling (`scheduler.py`)
- [ ] **C6**: Scanner Division-by-Zero (`coin_scanner.py`)

## Phase D: NEUE FEATURES - Während Testmonate

- [ ] **D1**: Fee-Aware Grid Calculation
- [ ] **D2**: Data Retention Auto-Cleanup
- [ ] **D3**: Dynamic Grid Count basierend auf ATR
- [ ] **D4**: Slippage Tracking
- [ ] **D5**: Funding Rate Signal
- [ ] **D6**: Echte Korrelations-Matrix

## Constraints für $400 Portfolio

- [ ] `SMALL_PORTFOLIO_CONSTRAINTS` Preset hinzufügen

---

## Fortschritt

| Phase | Items | Erledigt | Status |
|-------|-------|----------|--------|
| A     | 7     | 7        | 🟢     |
| B     | 7     | 0        | 🔴     |
| C     | 6     | 0        | 🔴     |
| D     | 6     | 0        | 🔴     |

## Verifikation vor Live-Testing
- [ ] `pytest tests/ -v` alle grün
- [ ] `ruff check src/ tests/ docker/` keine Fehler
- [ ] `mypy src/` keine Fehler
- [ ] 2 Wochen Binance Testnet mit LEARNING_MODE=true
