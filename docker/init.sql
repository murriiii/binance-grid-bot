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

-- Fertig!
SELECT 'Trading Bot Database initialized successfully!' as status;
