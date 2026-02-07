"""AI-Enhanced Coin Auto-Discovery with Learning Feedback Loop.

Discovers new USDT trading pairs on Binance, evaluates them via DeepSeek AI
with playbook context and past discovery history, and adds approved coins
to the watchlist. Each AI decision is logged for later performance evaluation,
creating a feedback loop that improves future discoveries.
"""

import json
import logging
import os
from datetime import datetime, timedelta

from src.utils.singleton import SingletonMixin

logger = logging.getLogger("trading_bot")

# Public Binance API (no key needed)
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
BINANCE_TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"

MAX_COINS_PER_RUN = 5
MIN_VOLUME_24H_USD = 1_000_000
STALE_DAYS_THRESHOLD = 7
DISCOVERY_HISTORY_LIMIT = 50
CANDIDATE_LIMIT = 20
EVALUATION_AFTER_DAYS = 7


class CoinDiscovery(SingletonMixin):
    """Discovers and evaluates new coins using AI with a learning feedback loop."""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")

    def run_discovery(self) -> dict:
        """Run the full discovery pipeline.

        Returns summary dict with counts and actions taken.
        """
        from src.tasks.base import get_db_connection

        summary = {"candidates": 0, "evaluated": 0, "approved": 0, "added": 0, "errors": []}

        if not self.api_key:
            summary["errors"].append("DEEPSEEK_API_KEY not set")
            return summary

        conn = get_db_connection()
        if not conn:
            summary["errors"].append("No DB connection")
            return summary

        try:
            # 1. Fetch all USDT pairs from Binance
            all_pairs = self._fetch_all_usdt_pairs()
            if not all_pairs:
                summary["errors"].append("Failed to fetch exchange info")
                return summary

            # 2. Filter out already known symbols
            known = self._get_known_symbols(conn)
            new_pairs = [p for p in all_pairs if p["symbol"] not in known]

            # 3. Filter by minimum volume
            candidates = self._filter_by_volume(new_pairs)
            summary["candidates"] = len(candidates)

            if not candidates:
                logger.info("CoinDiscovery: No new candidates found")
                return summary

            # 4. Load past discovery history for AI context
            history = self._load_discovery_history(conn)

            # 5. Evaluate past discoveries (update was_good_discovery)
            self._evaluate_past_discoveries(conn)

            # 6. AI evaluation with feedback loop
            evaluated = self._ai_evaluate(candidates[:CANDIDATE_LIMIT], history)
            summary["evaluated"] = len(evaluated)

            # 7. Log all AI decisions to DB
            self._log_decisions(conn, evaluated)

            # 8. Add approved coins to watchlist
            approved = [e for e in evaluated if e.get("approved")]
            summary["approved"] = len(approved)
            added = self._auto_add(approved[:MAX_COINS_PER_RUN])
            summary["added"] = added

            # 9. Deactivate stale coins
            self._deactivate_stale(conn)

            conn.commit()
            logger.info(
                f"CoinDiscovery: {summary['candidates']} candidates, "
                f"{summary['approved']} approved, {summary['added']} added"
            )

        except Exception as e:
            logger.error(f"CoinDiscovery pipeline error: {e}")
            summary["errors"].append(str(e))
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

        return summary

    def _fetch_all_usdt_pairs(self) -> list[dict]:
        """Fetch all USDT trading pairs from Binance public API."""
        from src.api.http_client import get_http_client

        try:
            http = get_http_client()
            data = http.get(BINANCE_EXCHANGE_INFO_URL, api_type="binance")

            pairs = []
            for s in data.get("symbols", []):
                if (
                    s.get("quoteAsset") == "USDT"
                    and s.get("status") == "TRADING"
                    and s.get("isSpotTradingAllowed", False)
                ):
                    pairs.append(
                        {
                            "symbol": s["symbol"],
                            "base_asset": s["baseAsset"],
                        }
                    )
            return pairs

        except Exception as e:
            logger.error(f"CoinDiscovery: Failed to fetch exchange info: {e}")
            return []

    def _get_known_symbols(self, conn) -> set[str]:
        """Get all symbols already in the watchlist."""
        from psycopg2.extras import RealDictCursor

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT symbol FROM watchlist")
                return {row["symbol"] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"CoinDiscovery: Failed to get known symbols: {e}")
            return set()

    def _filter_by_volume(self, pairs: list[dict]) -> list[dict]:
        """Filter pairs by 24h volume >= MIN_VOLUME_24H_USD."""
        from src.api.http_client import get_http_client

        try:
            http = get_http_client()
            tickers = http.get(BINANCE_TICKER_24H_URL, api_type="binance")
            volume_map = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in tickers}
        except Exception as e:
            logger.error(f"CoinDiscovery: Failed to fetch tickers: {e}")
            return []

        result = []
        for p in pairs:
            vol = volume_map.get(p["symbol"], 0)
            if vol >= MIN_VOLUME_24H_USD:
                p["volume_24h"] = vol
                result.append(p)

        # Sort by volume descending
        result.sort(key=lambda x: x["volume_24h"], reverse=True)
        return result

    def _load_discovery_history(self, conn) -> list[dict]:
        """Load past AI discovery decisions with their outcomes."""
        from psycopg2.extras import RealDictCursor

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT symbol, ai_approved, ai_category, ai_tier, ai_reason, "
                    "was_added, was_deactivated, deactivated_reason, "
                    "trades_after_30d, win_rate_after_30d, avg_return_after_30d, "
                    "was_good_discovery, discovered_at "
                    "FROM coin_discoveries "
                    "ORDER BY discovered_at DESC LIMIT %s",
                    (DISCOVERY_HISTORY_LIMIT,),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.debug(f"CoinDiscovery: No discovery history yet: {e}")
            return []

    def _evaluate_past_discoveries(self, conn) -> None:
        """Evaluate discoveries older than 30 days: update was_good_discovery."""
        from psycopg2.extras import RealDictCursor

        try:
            cutoff = datetime.utcnow() - timedelta(days=EVALUATION_AFTER_DAYS)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Find discoveries that were added but not yet evaluated
                cur.execute(
                    "SELECT d.id, d.symbol "
                    "FROM coin_discoveries d "
                    "WHERE d.was_added = true AND d.was_good_discovery IS NULL "
                    "AND d.discovered_at < %s",
                    (cutoff,),
                )
                pending = cur.fetchall()

                for row in pending:
                    # Get performance from watchlist table
                    cur.execute(
                        "SELECT total_trades, win_rate, avg_return_pct "
                        "FROM watchlist WHERE symbol = %s",
                        (row["symbol"],),
                    )
                    wl = cur.fetchone()
                    if not wl:
                        continue

                    trades = wl["total_trades"] or 0
                    win_rate = float(wl["win_rate"] or 0)
                    avg_return = float(wl["avg_return_pct"] or 0)

                    # Good discovery: >=2 trades AND (win_rate >= 50% OR avg_return > 0)
                    is_good = trades >= 2 and (win_rate >= 50 or avg_return > 0)

                    cur.execute(
                        "UPDATE coin_discoveries SET "
                        "trades_after_30d = %s, win_rate_after_30d = %s, "
                        "avg_return_after_30d = %s, was_good_discovery = %s "
                        "WHERE id = %s",
                        (trades, win_rate, avg_return, is_good, row["id"]),
                    )

        except Exception as e:
            logger.debug(f"CoinDiscovery: Past evaluation failed: {e}")

    def _format_discovery_history(self, history: list[dict]) -> str:
        """Format discovery history for the AI prompt."""
        if not history:
            return "Keine bisherigen Entscheidungen (erster Durchlauf)."

        lines = []
        for h in history:
            sym = h["symbol"]
            approved = h["ai_approved"]
            cat = h.get("ai_category", "?")
            tier = h.get("ai_tier", "?")

            if not approved:
                lines.append(f"  SKIP {sym} ({cat}, Tier {tier}): abgelehnt")
                continue

            if h.get("was_good_discovery") is True:
                trades = h.get("trades_after_30d", 0)
                wr = h.get("win_rate_after_30d", 0)
                avg = h.get("avg_return_after_30d", 0)
                lines.append(
                    f"  OK {sym} ({cat}, Tier {tier}): "
                    f"{trades} Trades, {wr:.0f}% Win Rate, {avg:+.2f}% avg"
                )
            elif h.get("was_good_discovery") is False:
                trades = h.get("trades_after_30d", 0)
                wr = h.get("win_rate_after_30d", 0)
                avg = h.get("avg_return_after_30d", 0)
                reason = ""
                if h.get("was_deactivated"):
                    reason = f" (deaktiviert: {h.get('deactivated_reason', '?')})"
                lines.append(
                    f"  FAIL {sym} ({cat}, Tier {tier}): "
                    f"{trades} Trades, {wr:.0f}% Win Rate, {avg:+.2f}% avg{reason}"
                )
            elif h.get("was_added"):
                lines.append(f"  PENDING {sym} ({cat}, Tier {tier}): noch in Bewertungsphase")
            else:
                lines.append(
                    f"  APPROVED {sym} ({cat}, Tier {tier}): genehmigt, nicht hinzugefuegt"
                )

        return "\n".join(lines) if lines else "Keine Entscheidungen mit Ergebnis."

    def _ai_evaluate(self, candidates: list[dict], history: list[dict]) -> list[dict]:
        """Evaluate candidates via DeepSeek AI with discovery history context."""
        from src.api.http_client import get_http_client
        from src.data.playbook import TradingPlaybook

        # Build playbook context
        playbook_context = ""
        try:
            from src.tasks.base import get_db_connection

            pb_conn = get_db_connection()
            if pb_conn:
                try:
                    pb = TradingPlaybook(db_connection=pb_conn)
                    playbook_context = pb.get_playbook_for_prompt()
                finally:
                    pb_conn.close()
        except Exception:
            pass

        history_context = self._format_discovery_history(history)

        candidate_list = "\n".join(
            f"  - {c['symbol']} (Base: {c['base_asset']}, 24h Vol: ${c['volume_24h']:,.0f})"
            for c in candidates
        )

        prompt = f"""Du bist ein Crypto-Analyst fuer einen Grid-Trading-Bot.

Dein Playbook (gelerntes Wissen):
{playbook_context or "Noch kein Playbook vorhanden."}

Deine bisherigen Discovery-Entscheidungen und Ergebnisse:
{history_context}

Bewerte diese neuen Kandidaten fuer Grid Trading:
{candidate_list}

Beachte:
- Grid Trading profitiert von hoher Volatilitaet und Liquiditaet
- Minimum 24h Volume: $1M
- Lerne aus deinen bisherigen Entscheidungen — vermeide Muster die zu schlechter Performance gefuehrt haben
- Sei konservativ: lieber wenige gute Coins als viele schlechte
- Maximal {MAX_COINS_PER_RUN} Coins genehmigen pro Durchlauf

Return AUSSCHLIESSLICH ein JSON Array (kein Markdown, kein Text drumherum):
[{{"symbol": "XXXUSDT", "category": "LARGE_CAP|MID_CAP|DEFI|AI|MEME|L2|GAMING", "tier": 1|2|3, "risk": "low|medium|high", "approved": true|false, "reason": "kurze Begruendung"}}]"""

        try:
            http = get_http_client()
            data = http.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Du bist ein Crypto-Analyst."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.3,
                },
                api_type="deepseek",
            )
            answer = data["choices"][0]["message"]["content"]

            # Parse JSON from response (handle markdown code blocks)
            answer = answer.strip()
            if answer.startswith("```"):
                answer = answer.split("\n", 1)[1] if "\n" in answer else answer[3:]
                answer = answer.rsplit("```", 1)[0]

            evaluated = json.loads(answer)

            # Merge volume data
            vol_map = {c["symbol"]: c["volume_24h"] for c in candidates}
            for e in evaluated:
                e["volume_24h"] = vol_map.get(e["symbol"], 0)

            return evaluated

        except json.JSONDecodeError as e:
            logger.error(f"CoinDiscovery: AI response not valid JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"CoinDiscovery: AI evaluation failed: {e}")
            return []

    def _log_decisions(self, conn, evaluated: list[dict]) -> None:
        """Log all AI decisions to coin_discoveries table."""
        try:
            with conn.cursor() as cur:
                for e in evaluated:
                    cur.execute(
                        "INSERT INTO coin_discoveries "
                        "(symbol, ai_approved, ai_category, ai_tier, ai_risk, "
                        "ai_reason, volume_24h_at_discovery) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            e["symbol"],
                            e.get("approved", False),
                            e.get("category"),
                            e.get("tier"),
                            e.get("risk"),
                            e.get("reason"),
                            e.get("volume_24h"),
                        ),
                    )
        except Exception as e:
            logger.error(f"CoinDiscovery: Failed to log decisions: {e}")

    def _auto_add(self, approved: list[dict]) -> int:
        """Add approved coins to watchlist. Returns count of successfully added."""
        from src.data.watchlist import WatchlistManager

        added = 0
        try:
            wm = WatchlistManager.get_instance()
        except Exception as e:
            logger.error(f"CoinDiscovery: WatchlistManager unavailable: {e}")
            return 0

        for coin in approved:
            try:
                symbol = coin["symbol"]
                base_asset = symbol.replace("USDT", "")
                category = coin.get("category", "MID_CAP")
                tier = coin.get("tier", 2)

                success = wm.add_coin(
                    symbol=symbol,
                    base_asset=base_asset,
                    category=category,
                    tier=tier,
                )
                if success:
                    added += 1
                    logger.info(f"CoinDiscovery: Added {symbol} ({category}, Tier {tier})")

                    # Mark as added in last discovery record
                    from src.tasks.base import get_db_connection

                    mark_conn = get_db_connection()
                    if mark_conn:
                        try:
                            with mark_conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE coin_discoveries SET was_added = true "
                                    "WHERE symbol = %s "
                                    "ORDER BY discovered_at DESC LIMIT 1",
                                    (symbol,),
                                )
                            mark_conn.commit()
                        finally:
                            mark_conn.close()

            except Exception as e:
                logger.error(f"CoinDiscovery: Failed to add {coin.get('symbol')}: {e}")

        return added

    def _deactivate_stale(self, conn) -> None:
        """Deactivate Tier-3 coins with no volume for STALE_DAYS_THRESHOLD days."""
        from psycopg2.extras import RealDictCursor

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Find Tier-3 coins added via discovery with no recent trades
                cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS_THRESHOLD)
                cur.execute(
                    "SELECT d.symbol FROM coin_discoveries d "
                    "JOIN watchlist w ON d.symbol = w.symbol "
                    "WHERE d.was_added = true AND d.was_deactivated = false "
                    "AND d.ai_tier = 3 AND d.discovered_at < %s "
                    "AND (w.total_trades IS NULL OR w.total_trades = 0)",
                    (cutoff,),
                )
                stale = cur.fetchall()

                for row in stale:
                    sym = row["symbol"]
                    cur.execute(
                        "UPDATE watchlist SET is_active = false WHERE symbol = %s",
                        (sym,),
                    )
                    cur.execute(
                        "UPDATE coin_discoveries SET "
                        "was_deactivated = true, deactivated_at = NOW(), "
                        "deactivated_reason = 'No trades after 7 days (Tier 3)' "
                        "WHERE symbol = %s AND was_added = true "
                        "AND was_deactivated = false",
                        (sym,),
                    )
                    logger.info(f"CoinDiscovery: Deactivated stale Tier-3 coin {sym}")

        except Exception as e:
            logger.debug(f"CoinDiscovery: Stale deactivation failed: {e}")

    def close(self):
        """Cleanup (required by SingletonMixin)."""
        pass
