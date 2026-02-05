"""
Strategie-Konfiguration
Zentrale Einstellungen für den Trading Bot

Lernphase: 3-4 Monate für robuste Daten
"""

STRATEGY_CONFIG = {
    # ═══════════════════════════════════════════════════════════════
    # LERNPHASE KONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    "learning_phase": {
        "duration_months": 4,  # 3-4 Monate für genug Datenpunkte
        "min_trades_for_patterns": 50,  # Mindestens 50 Trades pro Pattern
        "min_confidence_threshold": 0.6,  # AI-Confidence unter 0.6 = HOLD
        # In der Lernphase konservativer
        "learning_mode_settings": {
            "max_position_size_pct": 20,  # Max 20% pro Position
            "prefer_hold_on_uncertainty": True,
            "log_all_decisions": True,  # Auch Nicht-Trades loggen
        },
    },
    # ═══════════════════════════════════════════════════════════════
    # MAKROÖKONOMISCHE REGELN
    # ═══════════════════════════════════════════════════════════════
    "macro_rules": {
        # Bei diesen Events: NICHT traden
        "no_trade_events": [
            "FOMC",
            "Fed Interest Rate Decision",
            "CPI Release",
            "Core CPI",
            "ECB Interest Rate Decision",
        ],
        # Stunden vor/nach Event nicht traden
        "event_blackout_hours_before": 4,
        "event_blackout_hours_after": 2,
        # ETF Flow Regeln
        "etf_flow_thresholds": {
            "strong_inflow_mio": 500,  # >500M = sehr bullish
            "strong_outflow_mio": -300,  # <-300M = bearish Signal
        },
    },
    # ═══════════════════════════════════════════════════════════════
    # DATENSAMMLUNG
    # ═══════════════════════════════════════════════════════════════
    "data_collection": {
        # Was wird geloggt?
        "log_trades": True,
        "log_non_trades": True,  # "Bot hat NICHT gehandelt weil..."
        "log_market_snapshots": True,
        "log_ai_reasoning": True,
        # Wie oft?
        "market_snapshot_interval_minutes": 60,  # Stündlich
        "portfolio_snapshot_interval_hours": 4,  # Alle 4h
        # Outcome Tracking
        "track_outcome_after_hours": [1, 4, 24, 168],  # 1h, 4h, 24h, 7d
    },
    # ═══════════════════════════════════════════════════════════════
    # RISIKO MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    "risk_management": {
        # Portfolio Limits
        "max_single_position_pct": 30,  # Max 30% in einem Coin
        "max_altcoin_exposure_pct": 80,  # Max 80% in Altcoins
        # Drawdown Protection
        "max_daily_drawdown_pct": 10,  # Stop bei -10% am Tag
        "max_total_drawdown_pct": 25,  # Stop bei -25% gesamt
        # Bei extremen Bedingungen
        "extreme_fear_action": "ACCUMULATE",  # Fear < 20: Akkumulieren
        "extreme_greed_action": "REDUCE",  # Greed > 80: Positionen reduzieren
    },
    # ═══════════════════════════════════════════════════════════════
    # AI INTEGRATION
    # ═══════════════════════════════════════════════════════════════
    "ai_settings": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        # Wann AI nutzen?
        "use_ai_for_trade_reasoning": True,
        "use_ai_for_macro_analysis": True,
        "use_ai_for_anomaly_detection": True,
        # AI kann Mathe überstimmen wenn:
        "ai_can_override_math": True,
        "ai_override_conditions": [
            "high_impact_news",
            "extreme_sentiment",
            "detected_anomaly",
        ],
        # Kosten-Limit (DeepSeek ist günstig, aber trotzdem)
        "max_daily_api_calls": 100,
        "max_monthly_cost_usd": 5.0,
    },
    # ═══════════════════════════════════════════════════════════════
    # REBALANCING
    # ═══════════════════════════════════════════════════════════════
    "rebalancing": {
        "interval_days": 7,  # Wöchentlich
        "threshold_pct": 5,  # Nur wenn Position >5% abweicht
        # Nicht rebalancen wenn:
        "skip_rebalance_conditions": [
            "high_impact_event_today",
            "extreme_volatility",
            "ai_confidence_low",
        ],
    },
    # ═══════════════════════════════════════════════════════════════
    # BENACHRICHTIGUNGEN
    # ═══════════════════════════════════════════════════════════════
    "notifications": {
        "mode": "normal",  # minimal, normal, verbose
        # Normal Mode:
        "daily_summary_time": "20:00",
        "alert_on_trade": True,
        "alert_on_extreme_sentiment": True,
        "alert_on_macro_event": True,
        "include_ai_reasoning": True,
    },
}

# ═══════════════════════════════════════════════════════════════════
# PHASE TIMELINE (3-4 Monate)
# ═══════════════════════════════════════════════════════════════════
"""
MONAT 1: Setup & Datensammlung
├── Woche 1-2: Bot läuft, sammelt Daten, wenige echte Trades
├── Woche 3-4: Erste Patterns erkennbar, AI bekommt Kontext
└── Ziel: ~30-50 Datenpunkte, System stabil

MONAT 2: Aktives Lernen
├── Mehr Trades, AI-Reasoning verbessert sich
├── Erste Pattern-Analyse möglich
├── Makro-Events werden getrackt
└── Ziel: ~100 Datenpunkte, erste Insights

MONAT 3: Verfeinerung
├── Patterns werden statistisch signifikant
├── AI gibt bessere Empfehlungen (mehr Kontext)
├── Strategie-Adjustments basierend auf Daten
└── Ziel: ~150+ Datenpunkte, robuste Patterns

MONAT 4: Optimierung
├── Volle AI-Integration mit reichem Kontext
├── Alle Patterns haben genug Samples
├── Bot "kennt" verschiedene Marktphasen
└── Ziel: Profitables, datengetriebenes System
"""
