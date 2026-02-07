"""Data retention tasks — auto-cleanup of old records (D2)."""

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked

# Table → retention days mapping
RETENTION_CONFIG = {
    "market_snapshots": ("created_at", 90),
    "whale_alerts": ("created_at", 60),
    "social_sentiment": ("created_at", 90),
    "opportunities": ("created_at", 30),
    "technical_indicators": ("created_at", 60),
    "calculation_snapshots": ("created_at", 90),
    "ai_conversations": ("created_at", 30),
    "regime_history": ("created_at", 180),
}


@task_locked
def task_cleanup_old_data():
    """Delete old records based on retention policy. Runs daily at 03:00."""
    logger.info("Running data retention cleanup...")

    conn = get_db_connection()
    if not conn:
        return

    total_deleted = 0

    try:
        with conn.cursor() as cur:
            for table, (ts_column, days) in RETENTION_CONFIG.items():
                try:
                    cur.execute(
                        f"DELETE FROM {table} WHERE {ts_column} < NOW() - INTERVAL '%s days'",
                        (days,),
                    )
                    deleted = cur.rowcount
                    if deleted > 0:
                        logger.info(f"Retention: deleted {deleted} rows from {table} (>{days}d)")
                        total_deleted += deleted
                except Exception as e:
                    logger.warning(f"Retention cleanup failed for {table}: {e}")
                    conn.rollback()
                    continue

        conn.commit()
        logger.info(f"Data retention cleanup complete: {total_deleted} total rows deleted")

    except Exception as e:
        logger.error(f"Data Retention Error: {e}")
    finally:
        conn.close()
