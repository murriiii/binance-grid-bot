"""Market data collection tasks."""

from datetime import datetime

from src.tasks.base import get_db_connection, logger


def task_market_snapshot():
    """Stündlicher Market Snapshot."""
    from src.data.market_data import get_market_data

    logger.info("Running market snapshot...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        market_data = get_market_data()
        fear_greed = market_data.get_fear_greed()
        btc_price = market_data.get_price("BTCUSDT")
        btc_dominance = market_data.get_btc_dominance()

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_snapshots
                (timestamp, fear_greed, btc_price, btc_dominance)
                VALUES (%s, %s, %s, %s)
            """,
                (datetime.now(), fear_greed.value, btc_price, btc_dominance),
            )
            conn.commit()

        logger.info(
            f"Market Snapshot saved: F&G={fear_greed.value}, BTC=${btc_price:,.0f}, Dom={btc_dominance:.1f}%"
        )

    except Exception as e:
        logger.error(f"Market Snapshot Error: {e}")
    finally:
        conn.close()


def task_sentiment_check():
    """Prüft Sentiment und warnt bei Extremen."""
    from src.data.market_data import get_market_data
    from src.notifications.telegram_service import get_telegram

    logger.info("Checking sentiment...")

    market_data = get_market_data()
    fear_greed = market_data.get_fear_greed()

    telegram = get_telegram()
    telegram.send_sentiment_alert(fear_greed.value, fear_greed.classification)
