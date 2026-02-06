"""Trade pair tracking — links BUY fills to SELL fills for realized P&L."""

import logging
from datetime import datetime

logger = logging.getLogger("trading_bot")


class TradePairTracker:
    """Tracks BUY→SELL trade pairs in the ``trade_pairs`` table.

    Each BUY fill opens a pair; each SELL fill closes the oldest open pair
    for the same symbol (FIFO).  Stop-loss / cash exits close all open pairs.
    """

    def __init__(self, cohort_id: str | None = None):
        self.cohort_id = cohort_id
        self.db = self._get_db()

    @staticmethod
    def _get_db():
        try:
            from src.data.database import DatabaseManager

            db = DatabaseManager.get_instance()
            if db and db._pool:
                return db
        except Exception as e:
            logger.warning(f"TradePairTracker: DB not available: {e}")
        return None

    # ------------------------------------------------------------------
    # Open a pair (on BUY fill)
    # ------------------------------------------------------------------

    def open_pair(
        self,
        symbol: str,
        entry_trade_id: str | int | None,
        entry_price: float,
        entry_qty: float,
        entry_fee: float,
    ) -> str | None:
        """Create an open trade pair.  Returns the pair UUID or *None*."""
        if not self.db:
            return None

        try:
            entry_value = entry_price * entry_qty
            with self.db.get_cursor(dict_cursor=False) as cur:
                cur.execute(
                    """
                    INSERT INTO trade_pairs (
                        cohort_id, symbol,
                        entry_trade_id, entry_timestamp, entry_price,
                        entry_quantity, entry_value_usd, entry_fee_usd,
                        remaining_quantity, status, position_type
                    ) VALUES (
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, 'open', 'LONG'
                    ) RETURNING id
                    """,
                    (
                        self.cohort_id,
                        symbol,
                        str(entry_trade_id) if entry_trade_id else None,
                        datetime.now(),
                        entry_price,
                        entry_qty,
                        entry_value,
                        entry_fee,
                        entry_qty,
                    ),
                )
                row = cur.fetchone()
                pair_id = str(row[0]) if row else None
                logger.info(
                    f"Trade pair opened: {symbol} @ {entry_price:.4f} x {entry_qty} "
                    f"(pair {pair_id})"
                )
                return pair_id
        except Exception as e:
            logger.warning(f"TradePairTracker.open_pair failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Close the oldest open pair for a symbol (on SELL fill)
    # ------------------------------------------------------------------

    def close_pair(
        self,
        symbol: str,
        exit_trade_id: str | int | None,
        exit_price: float,
        exit_qty: float,
        exit_fee: float,
        exit_reason: str = "grid_fill",
    ) -> bool:
        """Close the oldest open pair for *symbol* (FIFO).  Returns success."""
        if not self.db:
            return False

        try:
            with self.db.get_cursor(dict_cursor=False) as cur:
                # Find oldest open pair for this symbol + cohort
                cur.execute(
                    """
                    SELECT id, entry_price, entry_quantity, entry_value_usd,
                           entry_fee_usd, entry_timestamp
                    FROM trade_pairs
                    WHERE symbol = %s AND status = 'open'
                      AND (cohort_id = %s OR (cohort_id IS NULL AND %s IS NULL))
                    ORDER BY entry_timestamp ASC
                    LIMIT 1
                    """,
                    (symbol, self.cohort_id, self.cohort_id),
                )
                row = cur.fetchone()
                if not row:
                    logger.debug(f"No open pair to close for {symbol}")
                    return False

                pair_id = row[0]
                entry_price_db = float(row[1])
                entry_qty_db = float(row[2])
                entry_value = float(row[3])
                entry_fee = float(row[4])
                entry_ts = row[5]

                now = datetime.now()
                exit_value = exit_price * exit_qty
                gross_pnl = exit_value - entry_value
                net_pnl = gross_pnl - entry_fee - exit_fee
                pnl_pct = (net_pnl / entry_value * 100) if entry_value > 0 else 0.0
                hold_hours = (now - entry_ts).total_seconds() / 3600 if entry_ts else 0.0

                cur.execute(
                    """
                    UPDATE trade_pairs SET
                        exit_trade_id = %s,
                        exit_timestamp = %s,
                        exit_price = %s,
                        exit_quantity = %s,
                        exit_value_usd = %s,
                        exit_fee_usd = %s,
                        gross_pnl = %s,
                        net_pnl = %s,
                        pnl_pct = %s,
                        hold_duration_hours = %s,
                        exit_reason = %s,
                        status = 'closed',
                        remaining_quantity = 0,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        str(exit_trade_id) if exit_trade_id else None,
                        now,
                        exit_price,
                        exit_qty,
                        exit_value,
                        exit_fee,
                        gross_pnl,
                        net_pnl,
                        pnl_pct,
                        hold_hours,
                        exit_reason,
                        now,
                        pair_id,
                    ),
                )
                logger.info(
                    f"Trade pair closed: {symbol} entry@{entry_price_db:.4f} "
                    f"exit@{exit_price:.4f} P&L={net_pnl:+.4f}$ ({pnl_pct:+.2f}%) "
                    f"held {hold_hours:.1f}h (pair {pair_id})"
                )
                return True
        except Exception as e:
            logger.warning(f"TradePairTracker.close_pair failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Close ALL open pairs for a symbol (stop-loss / cash exit)
    # ------------------------------------------------------------------

    def close_pairs_by_symbol(
        self,
        symbol: str,
        exit_price: float,
        exit_qty: float,
        exit_reason: str = "stop_loss",
    ) -> int:
        """Close all open pairs for *symbol*.  Returns number of pairs closed."""
        if not self.db:
            return 0

        try:
            now = datetime.now()
            with self.db.get_cursor(dict_cursor=False) as cur:
                cur.execute(
                    """
                    SELECT id, entry_price, entry_quantity, entry_value_usd,
                           entry_fee_usd, entry_timestamp
                    FROM trade_pairs
                    WHERE symbol = %s AND status = 'open'
                      AND (cohort_id = %s OR (cohort_id IS NULL AND %s IS NULL))
                    ORDER BY entry_timestamp ASC
                    """,
                    (symbol, self.cohort_id, self.cohort_id),
                )
                open_pairs = cur.fetchall()
                if not open_pairs:
                    return 0

                closed = 0
                for row in open_pairs:
                    pair_id = row[0]
                    entry_value = float(row[3])
                    entry_fee = float(row[4])
                    entry_ts = row[5]
                    entry_qty_db = float(row[2])

                    pair_exit_value = exit_price * entry_qty_db
                    gross_pnl = pair_exit_value - entry_value
                    net_pnl = gross_pnl - entry_fee
                    pnl_pct = (net_pnl / entry_value * 100) if entry_value > 0 else 0.0
                    hold_hours = (now - entry_ts).total_seconds() / 3600 if entry_ts else 0.0

                    cur.execute(
                        """
                        UPDATE trade_pairs SET
                            exit_timestamp = %s,
                            exit_price = %s,
                            exit_quantity = %s,
                            exit_value_usd = %s,
                            gross_pnl = %s,
                            net_pnl = %s,
                            pnl_pct = %s,
                            hold_duration_hours = %s,
                            exit_reason = %s,
                            status = 'closed',
                            remaining_quantity = 0,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            now,
                            exit_price,
                            entry_qty_db,
                            pair_exit_value,
                            gross_pnl,
                            net_pnl,
                            pnl_pct,
                            hold_hours,
                            exit_reason,
                            now,
                            pair_id,
                        ),
                    )
                    closed += 1

                logger.info(
                    f"Closed {closed} trade pairs for {symbol} "
                    f"(reason={exit_reason}, price={exit_price:.4f})"
                )
                return closed
        except Exception as e:
            logger.warning(f"TradePairTracker.close_pairs_by_symbol failed: {e}")
            return 0
