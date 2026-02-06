"""Shared infrastructure for scheduler tasks."""

import logging

import psycopg2

logger = logging.getLogger("trading_bot")


def get_db_connection():
    """Erstellt Datenbankverbindung."""
    from src.core.config import get_config

    config = get_config()
    db_url = config.database.url
    if not db_url:
        return None
    try:
        return psycopg2.connect(db_url)
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        return None
