"""
Zentrales Database Connection Management.

Stellt eine einzelne, wiederverwendbare Datenbankverbindung bereit.
Alle Module sollten diese Klasse nutzen statt eigene Connections zu erstellen.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from psycopg2.extensions import connection

load_dotenv()

logger = logging.getLogger("trading_bot")

# PostgreSQL
try:
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import ThreadedConnectionPool

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    ThreadedConnectionPool = None  # type: ignore
    RealDictCursor = None  # type: ignore
    logger.warning("psycopg2 nicht installiert - pip install psycopg2-binary")


class DatabaseManager:
    """
    Zentrales Database Connection Management mit Connection Pooling.

    Features:
    - Singleton Pattern
    - Connection Pooling (min 1, max 10 connections)
    - Context Manager für sichere Transaktionen
    - Automatisches Reconnect bei Verbindungsabbruch

    Usage:
        db = DatabaseManager.get_instance()

        # Option 1: Context Manager (empfohlen)
        with db.get_cursor() as cur:
            cur.execute("SELECT * FROM trades")
            rows = cur.fetchall()

        # Option 2: Direkte Connection (für komplexe Transaktionen)
        conn = db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
        finally:
            db.return_connection(conn)
    """

    _instance: DatabaseManager | None = None

    def __init__(self):
        self._pool: ThreadedConnectionPool | None = None
        self._db_url: str | None = None
        self._init_pool()

    @classmethod
    def get_instance(cls) -> DatabaseManager:
        """Singleton-Instanz."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset für Tests."""
        if cls._instance is not None:
            cls._instance.close_all()
            cls._instance = None

    def _init_pool(self) -> bool:
        """Initialisiert den Connection Pool."""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - DatabaseManager deaktiviert")
            return False

        try:
            # Hole Connection-Parameter
            self._db_url = os.getenv("DATABASE_URL")

            if self._db_url:
                # Nutze DATABASE_URL wenn vorhanden
                self._pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=self._db_url,
                )
            else:
                # Fallback auf einzelne Umgebungsvariablen
                self._pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    host=os.getenv("POSTGRES_HOST", "localhost"),
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    database=os.getenv("POSTGRES_DB", "trading_bot"),
                    user=os.getenv("POSTGRES_USER", "trading"),
                    password=os.getenv("POSTGRES_PASSWORD", ""),
                )

            logger.info("DatabaseManager: Connection Pool initialisiert (1-10 connections)")
            return True

        except Exception as e:
            logger.error(f"DatabaseManager: Pool-Initialisierung fehlgeschlagen: {e}")
            self._pool = None
            return False

    def get_connection(self) -> connection | None:
        """
        Holt eine Connection aus dem Pool.

        WICHTIG: Connection muss mit return_connection() zurückgegeben werden!
        Besser: Nutze get_cursor() Context Manager.
        """
        if not self._pool:
            return None

        conn = None
        try:
            conn = self._pool.getconn()
            # Teste ob Connection noch gültig
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception as e:
            logger.warning(f"DatabaseManager: Connection ungültig, reconnecting: {e}")
            if conn is not None:
                try:
                    self._pool.putconn(conn, close=True)
                except Exception:
                    pass
            try:
                return self._pool.getconn()
            except Exception:
                return None

    def return_connection(self, conn: connection) -> None:
        """Gibt eine Connection zurück an den Pool."""
        if self._pool and conn:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.warning(f"DatabaseManager: Connection return failed: {e}")

    @contextmanager
    def get_cursor(self, dict_cursor: bool = True):
        """
        Context Manager für sichere Cursor-Nutzung.

        Args:
            dict_cursor: True für RealDictCursor (Ergebnisse als Dict)

        Usage:
            with db.get_cursor() as cur:
                cur.execute("SELECT * FROM trades")
                rows = cur.fetchall()
        """
        conn = self.get_connection()
        if not conn:
            raise RuntimeError("Keine Datenbankverbindung verfügbar")

        try:
            cursor_factory = RealDictCursor if dict_cursor else None
            with conn.cursor(cursor_factory=cursor_factory) as cur:
                yield cur
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.return_connection(conn)

    @contextmanager
    def transaction(self):
        """
        Context Manager für explizite Transaktionen.

        Usage:
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(...)
                    cur.execute(...)
                # Auto-commit am Ende
        """
        conn = self.get_connection()
        if not conn:
            raise RuntimeError("Keine Datenbankverbindung verfügbar")

        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.return_connection(conn)

    def execute(
        self,
        query: str,
        params: tuple | dict | None = None,
        fetch: bool = False,
    ) -> list | None:
        """
        Führt ein einzelnes SQL-Statement aus.

        Args:
            query: SQL Query
            params: Query Parameter
            fetch: True um Ergebnisse zurückzugeben

        Returns:
            Liste von Rows (als Dict) wenn fetch=True, sonst None
        """
        with self.get_cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return None

    def execute_many(
        self,
        query: str,
        params_list: list[tuple | dict],
    ) -> int:
        """
        Führt ein Statement mehrfach aus (Batch Insert/Update).

        Args:
            query: SQL Query mit Platzhaltern
            params_list: Liste von Parameter-Tupeln

        Returns:
            Anzahl betroffener Rows
        """
        with self.get_cursor(dict_cursor=False) as cur:
            cur.executemany(query, params_list)
            return cur.rowcount

    def is_connected(self) -> bool:
        """Prüft ob eine Verbindung möglich ist."""
        if not self._pool:
            return False

        try:
            conn = self.get_connection()
            if conn:
                self.return_connection(conn)
                return True
        except Exception:
            pass
        return False

    def close_all(self) -> None:
        """Schließt alle Connections im Pool."""
        if self._pool:
            try:
                self._pool.closeall()
                logger.info("DatabaseManager: Alle Connections geschlossen")
            except Exception as e:
                logger.warning(f"DatabaseManager: Fehler beim Schließen: {e}")
            self._pool = None

    def get_pool_status(self) -> dict:
        """Gibt Status des Connection Pools zurück."""
        if not self._pool:
            return {"available": False, "connections": 0}

        return {
            "available": True,
            "min_connections": self._pool.minconn,
            "max_connections": self._pool.maxconn,
        }


# Convenience-Funktionen
def get_db() -> DatabaseManager:
    """Gibt die globale DatabaseManager-Instanz zurück."""
    return DatabaseManager.get_instance()


def get_db_cursor(dict_cursor: bool = True):
    """Shortcut für db.get_cursor()."""
    return get_db().get_cursor(dict_cursor)
