"""Shared infrastructure for scheduler tasks."""

import logging

logger = logging.getLogger("trading_bot")


def get_db_connection():
    """Erstellt Datenbankverbindung aus dem DatabaseManager Pool."""
    try:
        from src.data.database import DatabaseManager

        db = DatabaseManager.get_instance()
        return db.get_connection()
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        return None
