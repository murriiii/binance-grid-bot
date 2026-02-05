"""
Notification Konfiguration
Modus: NORMAL (2-5 Nachrichten/Tag)
"""

NOTIFICATION_CONFIG = {
    # Modus: "minimal", "normal", "verbose"
    "mode": "normal",

    # Tägliche Summary
    "daily_summary": {
        "enabled": True,
        "time": "20:00",  # Uhrzeit für täglichen Report
        "include_chart": True,
    },

    # Trade Alerts
    "trade_alerts": {
        "enabled": True,
        "min_value": 5.0,  # Nur Trades > 5€ melden
        "include_reasoning": True,  # Begründung mitschicken
    },

    # Sentiment Alerts
    "sentiment_alerts": {
        "enabled": True,
        "fear_threshold": 25,   # Alert wenn Fear & Greed < 25
        "greed_threshold": 75,  # Alert wenn Fear & Greed > 75
        "cooldown_hours": 12,   # Nicht öfter als alle 12h
    },

    # Error Alerts (immer an)
    "error_alerts": {
        "enabled": True,
    },

    # Stille Zeiten (keine Benachrichtigungen)
    "quiet_hours": {
        "enabled": False,
        "start": "23:00",
        "end": "07:00",
    },
}

"""
Erwartete Nachrichten pro Tag (Normal-Modus):

1. Tägliche Summary um 20:00           → 1 Nachricht
2. Rebalancing-Trades (ca. 1x/Woche)   → ~0.14/Tag
3. Sentiment bei Extremen              → ~0.5/Tag (wenn volatil)
4. Errors (hoffentlich nie)            → 0/Tag

= ca. 1-3 Nachrichten/Tag normal
= bis zu 5 bei hoher Volatilität
"""
