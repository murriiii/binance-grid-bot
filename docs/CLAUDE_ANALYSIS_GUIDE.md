# Claude Code Weekly Analysis Guide

This guide explains how to use Claude Code for weekly trading bot analysis and optimization.

## Overview

Every Saturday at 23:00, the bot automatically generates a comprehensive export containing:
- Trading performance metrics
- Error logs and patterns
- AI decision statistics
- Playbook effectiveness

This data is designed to be analyzed by Claude Code to continuously improve the bot.

## Weekly Analysis Workflow

### 1. Check Export Location

```bash
ls -la analysis_exports/
```

The most recent export will be in a folder like `week_20260205/`.

### 2. Start Claude Code Analysis

Run Claude Code with access to the export:

```bash
claude

# Then ask:
"Analyze the latest weekly export in analysis_exports/ and provide optimization recommendations"
```

### 3. Key Files to Review

| File | Purpose |
|------|---------|
| `analysis_export.json` | Structured data for programmatic analysis |
| `ANALYSIS_REPORT.md` | Human-readable summary |
| `logs/error.log` | Recent errors for debugging |
| `logs/decision.log` | AI decisions with reasoning |

### 4. Analysis Questions to Ask Claude Code

#### Performance Analysis
- "What patterns led to the most profitable trades this week?"
- "Which Fear & Greed ranges had the best outcomes?"
- "Are there any symbols that consistently underperform?"

#### Error Analysis
- "What are the most common errors and how can we fix them?"
- "Are there any API rate limit issues?"
- "What errors are causing trade failures?"

#### Decision Quality
- "How accurate were the AI predictions this week?"
- "What confidence levels led to the best outcomes?"
- "Are there any decisions that should have been different?"

#### Playbook Optimization
- "Based on the data, what new rules should be added to the playbook?"
- "Which existing playbook rules are not working?"
- "What anti-patterns should be documented?"

## Log Files Reference

### Error Log (`logs/error.log`)
```json
{
  "timestamp": "2026-02-05T14:30:00Z",
  "level": "ERROR",
  "category": "error",
  "message": "API call failed",
  "data": {
    "error_type": "ConnectionError",
    "context": {"endpoint": "/api/v3/order"}
  }
}
```

### Trade Log (`logs/trade.log`)
```json
{
  "timestamp": "2026-02-05T14:30:00Z",
  "level": "INFO",
  "category": "trade",
  "message": "Trade executed: BUY 0.001 BTCUSDT @ 97500",
  "data": {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": 0.001,
    "price": 97500,
    "order_id": "12345678"
  }
}
```

### Decision Log (`logs/decision.log`)
```json
{
  "timestamp": "2026-02-05T14:30:00Z",
  "level": "INFO",
  "category": "decision",
  "message": "AI Decision: BUY BTCUSDT (confidence: 0.75)",
  "data": {
    "symbol": "BTCUSDT",
    "direction": "BULLISH",
    "action": "BUY",
    "confidence": 0.75,
    "reasoning": "RSI oversold, F&G in fear zone",
    "market_data": {"fear_greed": 25, "rsi": 28}
  }
}
```

### Performance Log (`logs/performance.log`)
```json
{
  "timestamp": "2026-02-05T20:00:00Z",
  "level": "INFO",
  "category": "performance",
  "message": "Daily Performance: +1.25% ($12.50)",
  "data": {
    "portfolio_value": 1012.50,
    "daily_pnl": 12.50,
    "daily_pnl_pct": 1.25,
    "trades_count": 5,
    "win_rate": 0.8
  }
}
```

## Playbook Updates

After analysis, update the Trading Playbook:

```bash
# Edit the playbook
nano config/TRADING_PLAYBOOK.md

# Or let Claude Code suggest changes:
"Based on the analysis, update the TRADING_PLAYBOOK.md with new rules"
```

### Playbook Sections to Update

1. **Fear & Greed Rules** - Add/modify based on outcome data
2. **Anti-Patterns** - Document failing strategies
3. **Success Patterns** - Document winning strategies
4. **Parameter Adjustments** - Update position sizing, thresholds

## Code Improvements

After analysis, Claude Code may suggest code improvements:

```bash
# Review suggestions
"What code changes would improve the bot based on this week's data?"

# Apply changes
"Implement the suggested improvement for [specific area]"

# Test
pytest tests/ -v
```

## Automation

For fully automated weekly optimization, you can create a script:

```bash
#!/bin/bash
# weekly_optimize.sh

cd /home/murriiii/dev/private/trading/binance-grid-bot

# Run Claude Code analysis
claude --print "Analyze analysis_exports/$(ls -t analysis_exports | head -1) and suggest playbook updates"
```

## Best Practices

1. **Always backup before changes**
   ```bash
   cp config/TRADING_PLAYBOOK.md config/playbook_history/playbook_backup_$(date +%Y%m%d).md
   ```

2. **Test in testnet first**
   - Apply suggested changes
   - Run for 1 week on testnet
   - Verify improvement before mainnet

3. **Version control everything**
   ```bash
   git add .
   git commit -m "Weekly optimization based on analysis"
   ```

4. **Track improvements over time**
   - Keep metrics from each week
   - Compare win rates, P&L trends
   - Revert changes that don't improve performance

## Troubleshooting

### Export not generated
```bash
# Manually trigger export
python -c "from src.analysis.weekly_export import run_weekly_export; print(run_weekly_export())"
```

### Logs empty
```bash
# Check if logging is working
python -c "from src.core.logging_system import get_logger; l=get_logger(); l.error('Test')"
cat logs/error.log
```

### Database connection issues
```bash
# Check DB status
docker exec -it trading-postgres pg_isready
```

---

*Last updated: 2026-02-05*
*This guide is part of the Trading Bot documentation.*
