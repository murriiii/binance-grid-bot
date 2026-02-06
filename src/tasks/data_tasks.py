"""External data fetching tasks."""

from src.tasks.base import logger


def task_fetch_etf_flows():
    """Holt tägliche ETF-Flow Daten. Läuft täglich um 10:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Fetching ETF flow data...")

    try:
        from src.data.etf_flows import ETFFlowTracker

        tracker = ETFFlowTracker.get_instance()
        flows = tracker.fetch_and_store_daily()

        if flows:
            signal, reasoning = tracker.get_institutional_signal()
            logger.info(f"ETF Flows: Signal={signal:.2f}, {reasoning}")

            if abs(signal) > 0.5:
                direction = "📈 BULLISH" if signal > 0 else "📉 BEARISH"
                telegram = get_telegram()
                telegram.send(f"""
🏦 <b>ETF FLOW ALERT</b>

{direction} Institutional Signal: {signal:.2f}

{reasoning}
""")

    except Exception as e:
        logger.error(f"ETF Flow Fetch Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("ETF flow fetch failed", e, {"task": "fetch_etf_flows"})


def task_fetch_social_sentiment():
    """Holt Social Media Sentiment Daten. Läuft alle 4 Stunden."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Fetching social sentiment...")

    try:
        from src.data.social_sentiment import SocialSentimentProvider

        provider = SocialSentimentProvider.get_instance()

        symbols = ["BTC", "ETH", "SOL"]

        for symbol in symbols:
            metrics = provider.get_aggregated_sentiment(symbol)

            if metrics:
                logger.info(
                    f"Social Sentiment {symbol}: "
                    f"Score={metrics.composite_sentiment:.2f}, "
                    f"Volume={metrics.social_volume}"
                )

                if metrics.composite_sentiment and abs(metrics.composite_sentiment) > 0.7:
                    direction = "🚀 EUPHORIE" if metrics.composite_sentiment > 0 else "😰 PANIK"
                    telegram = get_telegram()
                    telegram.send(f"""
📱 <b>SOCIAL SENTIMENT ALERT</b>

{symbol}: {direction}
Composite Score: {metrics.composite_sentiment:.2f}
Social Volume: {metrics.social_volume:,}
""")

    except Exception as e:
        logger.error(f"Social Sentiment Fetch Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Social sentiment fetch failed", e, {"task": "fetch_social_sentiment"})


def task_fetch_token_unlocks():
    """Holt anstehende Token Unlock Events. Läuft täglich um 08:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Fetching token unlocks...")

    try:
        from src.data.token_unlocks import TokenUnlockTracker

        tracker = TokenUnlockTracker.get_instance()
        unlocks = tracker.fetch_and_store_upcoming(days=14)

        significant = tracker.get_significant_unlocks(days=7, min_pct=2.0)

        if significant:
            message = "🔓 <b>SIGNIFIKANTE TOKEN UNLOCKS</b>\n\n"

            for unlock in significant[:5]:
                impact_emoji = "🔴" if unlock.expected_impact == "HIGH" else "🟡"
                message += f"""
{impact_emoji} <b>{unlock.symbol}</b>
📅 {unlock.unlock_date.strftime("%d.%m.%Y")}
📊 {unlock.unlock_pct_of_supply:.1f}% Supply
💰 ${unlock.unlock_value_usd / 1_000_000:.1f}M
"""

            telegram = get_telegram()
            telegram.send(message)

        logger.info(f"Token Unlocks: {len(unlocks)} total, {len(significant)} significant")

    except Exception as e:
        logger.error(f"Token Unlock Fetch Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Token unlock fetch failed", e, {"task": "fetch_token_unlocks"})


def task_whale_check():
    """Prüft Whale-Aktivität."""
    from src.core.config import get_config
    from src.notifications.telegram_service import get_telegram

    logger.info("Checking whale activity...")

    try:
        from src.data.whale_alert import WhaleAlertTracker

        tracker = WhaleAlertTracker()
        whales = tracker.fetch_recent_whales(hours=1)

        if whales:
            config = get_config()
            big_whales = [w for w in whales if w.amount_usd >= config.whale.alert_threshold]

            telegram = get_telegram()
            for whale in big_whales[:3]:
                telegram.send_whale_alert(
                    symbol=whale.symbol,
                    amount=whale.amount,
                    amount_usd=whale.amount_usd,
                    direction=whale.potential_impact,
                    from_owner=whale.from_owner,
                    to_owner=whale.to_owner,
                )

    except Exception as e:
        logger.error(f"Whale Check Error: {e}")
