-- ═══════════════════════════════════════════════════════════════
-- TRADING BOT DATABASE SCHEMA
-- Vollständiges Schema für AI-Enhanced Trading mit Memory
-- ═══════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ═══════════════════════════════════════════════════════════════
-- TRADES - Alle ausgeführten Trades
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Trade Details
    action VARCHAR(10) NOT NULL,  -- BUY, SELL, HOLD
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    value_usd DECIMAL(20, 2) NOT NULL,
    fee_usd DECIMAL(10, 4) DEFAULT 0,

    -- Market Context at Trade Time
    fear_greed INTEGER,
    btc_price DECIMAL(20, 2),
    eth_price DECIMAL(20, 2),
    symbol_24h_change DECIMAL(10, 4),
    symbol_7d_change DECIMAL(10, 4),
    market_trend VARCHAR(20),  -- BULL, BEAR, SIDEWAYS
    volatility_regime VARCHAR(20),  -- LOW, MEDIUM, HIGH, EXTREME

    -- Decision Context
    math_signal JSONB,  -- Markowitz output
    ai_signal JSONB,    -- DeepSeek output
    sentiment_data JSONB,
    macro_context JSONB,
    reasoning TEXT,
    confidence DECIMAL(3, 2),

    -- Outcome (updated later)
    outcome_1h DECIMAL(10, 4),
    outcome_4h DECIMAL(10, 4),
    outcome_24h DECIMAL(10, 4),
    outcome_7d DECIMAL(10, 4),
    was_good_decision BOOLEAN,
    outcome_notes TEXT,

    -- Metadata
    trade_source VARCHAR(50) DEFAULT 'bot',  -- bot, manual, backtest
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_action ON trades(action);
CREATE INDEX idx_trades_fear_greed ON trades(fear_greed);
CREATE INDEX idx_trades_outcome ON trades(was_good_decision) WHERE was_good_decision IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- MARKET_SNAPSHOTS - Stündliche Marktdaten
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Global Market
    fear_greed INTEGER,
    btc_price DECIMAL(20, 2),
    btc_24h_change DECIMAL(10, 4),
    eth_price DECIMAL(20, 2),
    total_market_cap DECIMAL(30, 2),
    btc_dominance DECIMAL(5, 2),
    volume_24h DECIMAL(30, 2),

    -- Top Movers
    top_gainers JSONB,  -- [{symbol, change_pct}, ...]
    top_losers JSONB,

    -- Sentiment
    trending_coins JSONB,
    social_volume JSONB,

    -- Macro
    etf_flows JSONB,  -- {btc_flow, eth_flow}
    upcoming_events JSONB,

    -- Technical
    btc_rsi DECIMAL(5, 2),
    btc_macd JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_snapshots_timestamp ON market_snapshots(timestamp DESC);
CREATE INDEX idx_snapshots_fear_greed ON market_snapshots(fear_greed);

-- ═══════════════════════════════════════════════════════════════
-- WHALE_ALERTS - Große Transaktionen
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS whale_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL,

    symbol VARCHAR(20) NOT NULL,
    amount DECIMAL(30, 8) NOT NULL,
    amount_usd DECIMAL(20, 2) NOT NULL,
    transaction_type VARCHAR(50),  -- transfer, exchange_deposit, exchange_withdrawal
    from_address VARCHAR(100),
    to_address VARCHAR(100),
    from_owner VARCHAR(100),  -- exchange name or "unknown"
    to_owner VARCHAR(100),

    -- Analysis
    is_significant BOOLEAN DEFAULT false,
    potential_impact VARCHAR(20),  -- BULLISH, BEARISH, NEUTRAL
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_whale_timestamp ON whale_alerts(timestamp DESC);
CREATE INDEX idx_whale_symbol ON whale_alerts(symbol);
CREATE INDEX idx_whale_significant ON whale_alerts(is_significant) WHERE is_significant = true;

-- ═══════════════════════════════════════════════════════════════
-- ECONOMIC_EVENTS - Makroökonomische Events
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS economic_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_date TIMESTAMPTZ NOT NULL,

    name VARCHAR(200) NOT NULL,
    country VARCHAR(50),
    impact VARCHAR(20),  -- HIGH, MEDIUM, LOW
    category VARCHAR(50),  -- FOMC, CPI, NFP, CRYPTO, etc.

    previous_value VARCHAR(50),
    forecast_value VARCHAR(50),
    actual_value VARCHAR(50),

    -- Market Reaction (filled after event)
    btc_reaction_1h DECIMAL(10, 4),
    btc_reaction_24h DECIMAL(10, 4),
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_date ON economic_events(event_date);
CREATE INDEX idx_events_impact ON economic_events(impact);

-- ═══════════════════════════════════════════════════════════════
-- LEARNED_PATTERNS - Was funktioniert hat
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS learned_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_name VARCHAR(100) NOT NULL UNIQUE,

    description TEXT,
    conditions JSONB NOT NULL,  -- {"fear_greed_min": 20, "fear_greed_max": 30, ...}

    -- Statistics
    sample_size INTEGER DEFAULT 0,
    success_rate DECIMAL(5, 2),
    avg_return_1h DECIMAL(10, 4),
    avg_return_24h DECIMAL(10, 4),
    avg_return_7d DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),

    -- Metadata
    is_active BOOLEAN DEFAULT true,
    last_triggered TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- PORTFOLIO_SNAPSHOTS - Portfolio Zustand über Zeit
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    total_value_usd DECIMAL(20, 2) NOT NULL,
    cash_usd DECIMAL(20, 2),
    positions JSONB,  -- {"BTC": {"qty": 0.001, "value": 50}, ...}

    -- Performance
    daily_pnl DECIMAL(10, 4),
    daily_pnl_pct DECIMAL(10, 4),
    total_pnl DECIMAL(10, 4),
    total_pnl_pct DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),

    -- Risk Metrics
    portfolio_volatility DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    var_95 DECIMAL(20, 2),  -- Value at Risk 95%

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_portfolio_timestamp ON portfolio_snapshots(timestamp DESC);

-- ═══════════════════════════════════════════════════════════════
-- STOP_LOSS_ORDERS - Automatische Stop-Loss Tracking
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stop_loss_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    symbol VARCHAR(20) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    stop_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    stop_type VARCHAR(20) DEFAULT 'fixed',  -- fixed, trailing, atr

    -- Status
    is_active BOOLEAN DEFAULT true,
    triggered_at TIMESTAMPTZ,
    triggered_price DECIMAL(20, 8),
    result_pnl DECIMAL(10, 4),

    notes TEXT
);

CREATE INDEX idx_stoploss_active ON stop_loss_orders(is_active) WHERE is_active = true;
CREATE INDEX idx_stoploss_symbol ON stop_loss_orders(symbol);

-- ═══════════════════════════════════════════════════════════════
-- AI_CONVERSATIONS - Telegram AI Chat History
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    tokens_used INTEGER,
    response_time_ms INTEGER,

    -- Context
    had_trade_context BOOLEAN DEFAULT false,
    had_market_context BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_conv_timestamp ON ai_conversations(timestamp DESC);

-- ═══════════════════════════════════════════════════════════════
-- TECHNICAL_INDICATORS - Berechnete Indikatoren
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS technical_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,

    -- Price
    price DECIMAL(20, 8),
    volume_24h DECIMAL(30, 2),

    -- Moving Averages
    sma_20 DECIMAL(20, 8),
    sma_50 DECIMAL(20, 8),
    sma_200 DECIMAL(20, 8),
    ema_12 DECIMAL(20, 8),
    ema_26 DECIMAL(20, 8),

    -- Momentum
    rsi_14 DECIMAL(5, 2),
    macd_line DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    macd_histogram DECIMAL(20, 8),

    -- Volatility
    bollinger_upper DECIMAL(20, 8),
    bollinger_middle DECIMAL(20, 8),
    bollinger_lower DECIMAL(20, 8),
    atr_14 DECIMAL(20, 8),

    -- Signals
    trend VARCHAR(20),  -- STRONG_UP, UP, NEUTRAL, DOWN, STRONG_DOWN
    momentum VARCHAR(20),  -- OVERBOUGHT, NEUTRAL, OVERSOLD
    volatility VARCHAR(20),  -- LOW, MEDIUM, HIGH

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(timestamp, symbol)
);

CREATE INDEX idx_tech_timestamp ON technical_indicators(timestamp DESC);
CREATE INDEX idx_tech_symbol ON technical_indicators(symbol);

-- ═══════════════════════════════════════════════════════════════
-- FUNCTIONS
-- ═══════════════════════════════════════════════════════════════

-- Funktion: Update timestamp on row update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger für trades
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ═══════════════════════════════════════════════════════════════
-- VIEWS
-- ═══════════════════════════════════════════════════════════════

-- View: Recent Performance
CREATE OR REPLACE VIEW v_recent_performance AS
SELECT
    DATE_TRUNC('day', timestamp) as date,
    COUNT(*) as trades,
    SUM(CASE WHEN was_good_decision THEN 1 ELSE 0 END) as winning_trades,
    AVG(outcome_24h) as avg_return_24h,
    SUM(value_usd) as volume
FROM trades
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY date DESC;

-- View: Pattern Performance
CREATE OR REPLACE VIEW v_pattern_performance AS
SELECT
    pattern_name,
    success_rate,
    sample_size,
    avg_return_24h,
    sharpe_ratio,
    last_triggered
FROM learned_patterns
WHERE is_active = true AND sample_size >= 10
ORDER BY success_rate DESC;

-- ═══════════════════════════════════════════════════════════════
-- INITIAL DATA
-- ═══════════════════════════════════════════════════════════════

-- Initiale Patterns zum Tracken
INSERT INTO learned_patterns (pattern_name, description, conditions) VALUES
    ('buy_extreme_fear', 'Kaufen bei extremer Angst (F&G < 25)', '{"action": "BUY", "fear_greed_max": 25}'),
    ('buy_fear', 'Kaufen bei Angst (F&G 25-40)', '{"action": "BUY", "fear_greed_min": 25, "fear_greed_max": 40}'),
    ('buy_neutral', 'Kaufen bei neutralem Markt (F&G 40-60)', '{"action": "BUY", "fear_greed_min": 40, "fear_greed_max": 60}'),
    ('buy_greed', 'Kaufen bei Gier (F&G 60-75)', '{"action": "BUY", "fear_greed_min": 60, "fear_greed_max": 75}'),
    ('buy_extreme_greed', 'Kaufen bei extremer Gier (F&G > 75)', '{"action": "BUY", "fear_greed_min": 75}'),
    ('sell_extreme_fear', 'Verkaufen bei extremer Angst', '{"action": "SELL", "fear_greed_max": 25}'),
    ('sell_extreme_greed', 'Verkaufen bei extremer Gier', '{"action": "SELL", "fear_greed_min": 75}'),
    ('buy_rsi_oversold', 'Kaufen bei RSI < 30', '{"action": "BUY", "rsi_max": 30}'),
    ('sell_rsi_overbought', 'Verkaufen bei RSI > 70', '{"action": "SELL", "rsi_min": 70}'),
    ('buy_whale_accumulation', 'Kaufen nach großem Whale-Kauf', '{"action": "BUY", "whale_signal": "accumulation"}')
ON CONFLICT (pattern_name) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════
-- COHORTS - Parallele Strategie-Varianten
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS cohorts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL UNIQUE,  -- 'conservative', 'balanced', 'aggressive', 'baseline'
    description TEXT,
    config JSONB NOT NULL,  -- Strategie-Parameter
    starting_capital DECIMAL(20, 2) DEFAULT 1000.00,
    current_capital DECIMAL(20, 2) DEFAULT 1000.00,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cohorts_active ON cohorts(is_active) WHERE is_active = true;

-- ═══════════════════════════════════════════════════════════════
-- TRADING_CYCLES - Wöchentliche Zyklen pro Cohort
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trading_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cohort_id UUID REFERENCES cohorts(id) ON DELETE CASCADE,
    cycle_number INTEGER NOT NULL,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, cancelled

    -- Cycle Capital
    starting_capital DECIMAL(20, 2) NOT NULL DEFAULT 1000.00,
    ending_capital DECIMAL(20, 2),
    trades_count INTEGER DEFAULT 0,

    -- Performance Metrics
    total_pnl DECIMAL(20, 4),
    total_pnl_pct DECIMAL(10, 4),
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    max_drawdown DECIMAL(10, 4),
    max_drawdown_date TIMESTAMPTZ,

    -- Risk Metrics
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    calmar_ratio DECIMAL(10, 4),
    volatility DECIMAL(10, 4),
    kelly_fraction DECIMAL(10, 4),
    var_95 DECIMAL(10, 4),
    cvar_95 DECIMAL(10, 4),

    -- Market Context Summary
    avg_fear_greed DECIMAL(5, 2),
    min_fear_greed INTEGER,
    max_fear_greed INTEGER,
    dominant_regime VARCHAR(20),  -- BULL, BEAR, SIDEWAYS
    btc_performance_pct DECIMAL(10, 4),

    -- Signal Performance (which signals worked)
    signal_performance JSONB,  -- {"rsi": {"accuracy": 0.65, "pnl": 2.3}, ...}

    -- Learnings
    best_patterns JSONB,
    worst_patterns JSONB,
    recommendations TEXT,

    -- Playbook
    playbook_version_at_start INTEGER,
    playbook_version_at_end INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,

    UNIQUE(cohort_id, cycle_number)
);

CREATE INDEX idx_cycles_cohort ON trading_cycles(cohort_id);
CREATE INDEX idx_cycles_number ON trading_cycles(cycle_number DESC);
CREATE INDEX idx_cycles_status ON trading_cycles(status);
CREATE INDEX idx_cycles_dates ON trading_cycles(start_date, end_date);

-- ═══════════════════════════════════════════════════════════════
-- SIGNAL_COMPONENTS - Signal-Breakdown pro Trade
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS signal_components (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trade_id UUID REFERENCES trades(id) ON DELETE CASCADE,
    cycle_id UUID REFERENCES trading_cycles(id),
    cohort_id UUID REFERENCES cohorts(id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Individual Signal Scores (-1 to +1)
    fear_greed_signal DECIMAL(5, 4),  -- Contrarian interpretation
    rsi_signal DECIMAL(5, 4),
    macd_signal DECIMAL(5, 4),
    trend_signal DECIMAL(5, 4),  -- SMA alignment
    volume_signal DECIMAL(5, 4),
    whale_signal DECIMAL(5, 4),
    sentiment_signal DECIMAL(5, 4),
    macro_signal DECIMAL(5, 4),

    -- AI Signals
    ai_direction_signal DECIMAL(5, 4),
    ai_confidence DECIMAL(5, 4),
    ai_risk_level VARCHAR(20),  -- LOW, MEDIUM, HIGH
    playbook_alignment_score DECIMAL(5, 4),

    -- Weights Used
    weights_applied JSONB,  -- {"fear_greed": 0.15, "rsi": 0.20, ...}

    -- Combined Scores
    math_composite_score DECIMAL(5, 4),
    ai_composite_score DECIMAL(5, 4),
    final_score DECIMAL(5, 4),

    -- Divergence Detection
    has_divergence BOOLEAN DEFAULT FALSE,
    divergence_type VARCHAR(50),  -- bullish_regular, bearish_hidden, etc.
    divergence_strength DECIMAL(5, 4),

    -- Outcome (updated later)
    was_correct BOOLEAN,
    outcome_contribution DECIMAL(10, 4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_signals_trade ON signal_components(trade_id);
CREATE INDEX idx_signals_cycle ON signal_components(cycle_id);
CREATE INDEX idx_signals_cohort ON signal_components(cohort_id);
CREATE INDEX idx_signals_timestamp ON signal_components(timestamp DESC);
CREATE INDEX idx_signals_divergence ON signal_components(has_divergence) WHERE has_divergence = true;

-- ═══════════════════════════════════════════════════════════════
-- CALCULATION_SNAPSHOTS - Alle Math-Berechnungen persistieren
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS calculation_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cycle_id UUID REFERENCES trading_cycles(id),
    cohort_id UUID REFERENCES cohorts(id),
    trade_id UUID REFERENCES trades(id),  -- Optional: linked to specific trade

    -- Position Sizing Calculations
    kelly_fraction DECIMAL(10, 6),
    half_kelly DECIMAL(10, 6),
    optimal_position_size DECIMAL(20, 8),
    max_position_size DECIMAL(20, 8),
    position_size_used DECIMAL(20, 8),

    -- Risk Metrics at This Point
    current_sharpe DECIMAL(10, 4),
    current_sortino DECIMAL(10, 4),
    current_calmar DECIMAL(10, 4),
    rolling_volatility_7d DECIMAL(10, 4),
    rolling_volatility_30d DECIMAL(10, 4),
    current_drawdown DECIMAL(10, 4),
    max_drawdown_cycle DECIMAL(10, 4),

    -- Value at Risk
    var_95 DECIMAL(20, 4),
    var_99 DECIMAL(20, 4),
    cvar_95 DECIMAL(20, 4),
    cvar_99 DECIMAL(20, 4),

    -- Portfolio State
    portfolio_value DECIMAL(20, 4),
    cash_position DECIMAL(20, 4),
    invested_position DECIMAL(20, 4),
    exposure_pct DECIMAL(10, 4),
    leverage DECIMAL(5, 2) DEFAULT 1.00,

    -- Market State
    btc_price DECIMAL(20, 2),
    fear_greed INTEGER,
    current_regime VARCHAR(20),

    -- Correlation Matrix (for multi-asset)
    correlation_matrix JSONB,

    -- Win/Loss Stats
    win_rate DECIMAL(5, 4),
    profit_factor DECIMAL(10, 4),
    avg_win DECIMAL(10, 4),
    avg_loss DECIMAL(10, 4),
    consecutive_wins INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_calc_timestamp ON calculation_snapshots(timestamp DESC);
CREATE INDEX idx_calc_cycle ON calculation_snapshots(cycle_id);
CREATE INDEX idx_calc_cohort ON calculation_snapshots(cohort_id);
CREATE INDEX idx_calc_trade ON calculation_snapshots(trade_id);

-- ═══════════════════════════════════════════════════════════════
-- TRADE_PAIRS - BUY/SELL Paare für echtes P&L
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trade_pairs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES trading_cycles(id),
    cohort_id UUID REFERENCES cohorts(id),
    symbol VARCHAR(20) NOT NULL,

    -- Entry Trade
    entry_trade_id UUID REFERENCES trades(id),
    entry_timestamp TIMESTAMPTZ NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    entry_quantity DECIMAL(20, 8) NOT NULL,
    entry_value_usd DECIMAL(20, 4) NOT NULL,
    entry_fee_usd DECIMAL(10, 4) DEFAULT 0,

    -- Exit Trade (null if position still open)
    exit_trade_id UUID REFERENCES trades(id),
    exit_timestamp TIMESTAMPTZ,
    exit_price DECIMAL(20, 8),
    exit_quantity DECIMAL(20, 8),
    exit_value_usd DECIMAL(20, 4),
    exit_fee_usd DECIMAL(10, 4),

    -- Position Details
    position_type VARCHAR(10) DEFAULT 'LONG',  -- LONG, SHORT
    status VARCHAR(20) DEFAULT 'open',  -- open, closed, partial
    remaining_quantity DECIMAL(20, 8),

    -- Calculated P&L
    gross_pnl DECIMAL(20, 4),
    net_pnl DECIMAL(20, 4),  -- After fees
    pnl_pct DECIMAL(10, 4),
    hold_duration_hours DECIMAL(10, 2),

    -- Peak/Trough during hold
    max_price_during_hold DECIMAL(20, 8),
    min_price_during_hold DECIMAL(20, 8),
    max_unrealized_pnl_pct DECIMAL(10, 4),
    max_unrealized_loss_pct DECIMAL(10, 4),

    -- Exit Reason
    exit_reason VARCHAR(50),  -- target_hit, stop_loss, manual, cycle_end, trailing_stop

    -- Market Context Comparison
    entry_fear_greed INTEGER,
    exit_fear_greed INTEGER,
    entry_btc_price DECIMAL(20, 2),
    exit_btc_price DECIMAL(20, 2),
    entry_regime VARCHAR(20),
    exit_regime VARCHAR(20),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pairs_cycle ON trade_pairs(cycle_id);
CREATE INDEX idx_pairs_cohort ON trade_pairs(cohort_id);
CREATE INDEX idx_pairs_symbol ON trade_pairs(symbol);
CREATE INDEX idx_pairs_status ON trade_pairs(status);
CREATE INDEX idx_pairs_entry ON trade_pairs(entry_timestamp DESC);

-- ═══════════════════════════════════════════════════════════════
-- REGIME_HISTORY - Markt-Regime Tracking
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS regime_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    regime VARCHAR(20) NOT NULL,  -- BULL, BEAR, SIDEWAYS
    regime_probability DECIMAL(5, 4),
    transition_probability DECIMAL(5, 4),

    -- Features used for detection
    return_7d DECIMAL(10, 4),
    volatility_7d DECIMAL(10, 4),
    volume_trend DECIMAL(10, 4),
    fear_greed_avg DECIMAL(5, 2),

    -- Model Confidence
    model_confidence DECIMAL(5, 4),
    previous_regime VARCHAR(20),
    regime_duration_hours INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_regime_timestamp ON regime_history(timestamp DESC);
CREATE INDEX idx_regime_type ON regime_history(regime);

-- ═══════════════════════════════════════════════════════════════
-- SIGNAL_WEIGHTS - Bayesian Gewichtung über Zeit
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS signal_weights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cohort_id UUID REFERENCES cohorts(id),

    -- Current Weights
    fear_greed_weight DECIMAL(5, 4),
    rsi_weight DECIMAL(5, 4),
    macd_weight DECIMAL(5, 4),
    trend_weight DECIMAL(5, 4),
    volume_weight DECIMAL(5, 4),
    whale_weight DECIMAL(5, 4),
    sentiment_weight DECIMAL(5, 4),
    macro_weight DECIMAL(5, 4),
    ai_weight DECIMAL(5, 4),

    -- Weight Uncertainties (Bayesian)
    weight_uncertainties JSONB,

    -- Performance that led to this update
    signal_accuracies JSONB,
    learning_rate DECIMAL(5, 4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_weights_timestamp ON signal_weights(timestamp DESC);
CREATE INDEX idx_weights_cohort ON signal_weights(cohort_id);

-- ═══════════════════════════════════════════════════════════════
-- ALTER EXISTING TABLES
-- ═══════════════════════════════════════════════════════════════

-- Add cohort_id and cycle_id to trades table
ALTER TABLE trades ADD COLUMN IF NOT EXISTS cohort_id UUID REFERENCES cohorts(id);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES trading_cycles(id);

CREATE INDEX IF NOT EXISTS idx_trades_cohort ON trades(cohort_id);
CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id);

-- ═══════════════════════════════════════════════════════════════
-- VIEWS FOR ANALYSIS
-- ═══════════════════════════════════════════════════════════════

-- View: Cohort Comparison
CREATE OR REPLACE VIEW v_cohort_comparison AS
SELECT
    c.name as cohort_name,
    tc.cycle_number,
    tc.starting_capital,
    tc.ending_capital,
    tc.total_pnl_pct,
    tc.sharpe_ratio,
    tc.max_drawdown,
    tc.trades_count,
    tc.winning_trades,
    CASE WHEN tc.trades_count > 0
        THEN ROUND(tc.winning_trades::DECIMAL / tc.trades_count * 100, 2)
        ELSE 0 END as win_rate_pct,
    tc.dominant_regime,
    tc.avg_fear_greed
FROM trading_cycles tc
JOIN cohorts c ON tc.cohort_id = c.id
WHERE tc.status = 'completed'
ORDER BY tc.cycle_number DESC, c.name;

-- View: Signal Effectiveness
CREATE OR REPLACE VIEW v_signal_effectiveness AS
SELECT
    c.name as cohort_name,
    tc.cycle_number,
    COUNT(sc.id) as total_signals,
    AVG(CASE WHEN sc.was_correct THEN 1 ELSE 0 END) as overall_accuracy,
    AVG(CASE WHEN sc.fear_greed_signal > 0.3 AND sc.was_correct THEN 1
             WHEN sc.fear_greed_signal > 0.3 THEN 0 END) as fear_greed_accuracy,
    AVG(CASE WHEN sc.rsi_signal > 0.3 AND sc.was_correct THEN 1
             WHEN sc.rsi_signal > 0.3 THEN 0 END) as rsi_accuracy,
    AVG(CASE WHEN sc.ai_direction_signal > 0.3 AND sc.was_correct THEN 1
             WHEN sc.ai_direction_signal > 0.3 THEN 0 END) as ai_accuracy
FROM signal_components sc
JOIN trading_cycles tc ON sc.cycle_id = tc.id
JOIN cohorts c ON sc.cohort_id = c.id
WHERE sc.was_correct IS NOT NULL
GROUP BY c.name, tc.cycle_number
ORDER BY tc.cycle_number DESC, c.name;

-- ═══════════════════════════════════════════════════════════════
-- INITIAL COHORTS
-- ═══════════════════════════════════════════════════════════════
INSERT INTO cohorts (name, description, config, starting_capital) VALUES
    ('conservative', 'Konservative Strategie: Enge Grids, hohe Confidence',
     '{"grid_range_pct": 2.0, "min_confidence": 0.7, "max_fear_greed": 40, "risk_tolerance": "low"}',
     1000.00),
    ('balanced', 'Ausgewogene Strategie: Standard Grids, Playbook-gesteuert',
     '{"grid_range_pct": 5.0, "min_confidence": 0.5, "use_playbook": true, "risk_tolerance": "medium"}',
     1000.00),
    ('aggressive', 'Aggressive Strategie: Weite Grids, höheres Risiko',
     '{"grid_range_pct": 8.0, "min_confidence": 0.3, "min_fear_greed": 0, "risk_tolerance": "high"}',
     1000.00),
    ('baseline', 'Baseline: Keine Änderungen, Woche 1 Strategie als Kontrolle',
     '{"grid_range_pct": 5.0, "min_confidence": 0.5, "frozen": true, "risk_tolerance": "medium"}',
     1000.00)
ON CONFLICT (name) DO NOTHING;

-- Fertig!
SELECT 'Trading Bot Database initialized successfully with Cohort System!' as status;
