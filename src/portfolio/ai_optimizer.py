"""AI Portfolio Optimizer - DeepSeek recommends monthly tier allocations.

Uses market regime, signal accuracy, and tier performance to suggest
optimal portfolio allocation. Guard rails prevent extreme allocations.

Learning mode: Months 1-3 log only (paper validation).
After month 4: auto-apply if confidence > 0.8.
"""

import json
import logging
import os

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection

logger = logging.getLogger("trading_bot")

# Guard rails — AI cannot allocate outside these bounds
ALLOCATION_BOUNDS = {
    "cash_reserve": (5.0, 20.0),
    "index_holdings": (40.0, 80.0),
    "trading": (10.0, 40.0),
}

# Max percentage point shift per recommendation
MAX_SHIFT_PP = 5.0


class AIPortfolioOptimizer:
    """Monthly AI-driven portfolio allocation optimizer.

    Gathers context (regime, performance, signal accuracy), sends to
    DeepSeek, and stores recommendations. Guard rails ensure safe bounds.
    """

    def __init__(self, portfolio_manager=None):
        self.pm = portfolio_manager

    def gather_context(self) -> dict:
        """Gather all context needed for the AI recommendation."""
        conn = get_db_connection()
        if not conn:
            return {}

        context = {}
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Current regime
                cur.execute("""
                    SELECT regime, probability, detected_at
                    FROM regime_history
                    ORDER BY detected_at DESC LIMIT 1
                """)
                regime_row = cur.fetchone()
                context["current_regime"] = {
                    "regime": regime_row["regime"] if regime_row else "UNKNOWN",
                    "probability": float(regime_row["probability"]) if regime_row else 0,
                }

                # 2. Regime history (last 90 days)
                cur.execute("""
                    SELECT regime, COUNT(*) as count
                    FROM regime_history
                    WHERE detected_at > NOW() - INTERVAL '90 days'
                    GROUP BY regime ORDER BY count DESC
                """)
                context["regime_distribution"] = {
                    row["regime"]: row["count"] for row in cur.fetchall()
                }

                # 3. Per-tier performance (last 30 days from portfolio_snapshots)
                cur.execute("""
                    SELECT total_value_usd, daily_pnl_pct, timestamp
                    FROM portfolio_snapshots
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                    ORDER BY timestamp
                """)
                snapshots = cur.fetchall()
                if snapshots:
                    values = [float(s["total_value_usd"]) for s in snapshots]
                    returns = [float(s["daily_pnl_pct"] or 0) for s in snapshots]
                    context["portfolio_30d"] = {
                        "start_value": values[0],
                        "end_value": values[-1],
                        "total_return_pct": (values[-1] - values[0]) / values[0] * 100
                        if values[0] > 0
                        else 0,
                        "avg_daily_return": sum(returns) / len(returns) if returns else 0,
                        "max_drawdown_pct": _calculate_max_drawdown(values),
                        "data_points": len(snapshots),
                    }

                # 4. Trading tier realized P&L
                cur.execute("""
                    SELECT
                        COALESCE(SUM(net_pnl), 0) as total_pnl,
                        COUNT(*) as trade_count,
                        SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins
                    FROM trade_pairs
                    WHERE status = 'closed'
                    AND closed_at > NOW() - INTERVAL '30 days'
                """)
                tp = cur.fetchone()
                trades = tp["trade_count"] or 0
                wins = tp["wins"] or 0
                context["trading_30d"] = {
                    "total_pnl": float(tp["total_pnl"]),
                    "trade_count": trades,
                    "win_rate": wins / trades * 100 if trades > 0 else 0,
                }

                # 5. Signal accuracy (top signals)
                cur.execute("""
                    SELECT signal_name,
                        COUNT(*) as total,
                        SUM(CASE WHEN was_correct THEN 1 ELSE 0 END) as correct
                    FROM signal_components
                    WHERE was_correct IS NOT NULL
                    AND created_at > NOW() - INTERVAL '30 days'
                    GROUP BY signal_name
                    HAVING COUNT(*) >= 10
                    ORDER BY SUM(CASE WHEN was_correct THEN 1 ELSE 0 END)::float / COUNT(*) DESC
                    LIMIT 5
                """)
                context["signal_accuracy"] = [
                    {
                        "signal": row["signal_name"],
                        "accuracy": float(row["correct"]) / float(row["total"]) * 100,
                        "samples": row["total"],
                    }
                    for row in cur.fetchall()
                ]

                # 6. Current tier allocations
                cur.execute("""
                    SELECT tier_name, target_pct, current_pct, current_value_usd
                    FROM portfolio_tiers WHERE is_active = TRUE
                """)
                context["current_tiers"] = {
                    row["tier_name"]: {
                        "target_pct": float(row["target_pct"]),
                        "current_pct": float(row["current_pct"] or 0),
                        "value_usd": float(row["current_value_usd"] or 0),
                    }
                    for row in cur.fetchall()
                }

                # 7. Previous AI recommendations
                cur.execute("""
                    SELECT recommended_allocations, confidence,
                           market_regime, was_applied, timestamp
                    FROM ai_portfolio_recommendations
                    ORDER BY timestamp DESC LIMIT 3
                """)
                context["previous_recommendations"] = [
                    {
                        "allocations": row["recommended_allocations"],
                        "confidence": float(row["confidence"]) if row["confidence"] else 0,
                        "regime": row["market_regime"],
                        "applied": row["was_applied"],
                        "date": row["timestamp"].isoformat() if row["timestamp"] else None,
                    }
                    for row in cur.fetchall()
                ]

        except Exception as e:
            logger.error(f"AI Optimizer context gathering failed: {e}")
        finally:
            conn.close()

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        """Build system and user prompts for DeepSeek."""
        system_prompt = """Du bist ein quantitativer Portfolio-Optimizer für ein Krypto-Trading-System.

Das System hat 3 Tiers:
- cash_reserve: USDT-Sicherheitspuffer (erlaubt: 5-20%)
- index_holdings: Top-20-Krypto Buy-and-Hold, ETF-artig (erlaubt: 40-80%)
- trading: Aktives Grid/Hold Trading mit 6 Kohorten (erlaubt: 10-40%)

Deine Aufgabe: Basierend auf Marktregime, Performance und Signal-Qualität
die optimale Tier-Verteilung empfehlen.

Regeln:
- Summe MUSS exakt 100% ergeben
- Max 5 Prozentpunkte Shift pro Empfehlung vs. aktuelle Ziele
- BEAR → mehr Cash, weniger Trading
- BULL → weniger Cash, mehr Trading
- SIDEWAYS → ausgewogener, mehr Index
- Niedrige Signal-Accuracy → weniger Trading-Gewicht
- Hoher Drawdown → mehr Cash

Antworte AUSSCHLIESSLICH als JSON:
{
    "cash_reserve": <float>,
    "index_holdings": <float>,
    "trading": <float>,
    "confidence": <float 0-1>,
    "reasoning": "<kurze Begründung auf Deutsch>"
}"""

        user_parts = ["Analysiere folgende Portfolio-Daten und empfehle optimale Verteilung:\n"]

        regime = context.get("current_regime", {})
        user_parts.append(
            f"MARKT-REGIME: {regime.get('regime', 'UNKNOWN')} "
            f"(Wahrscheinlichkeit: {regime.get('probability', 0):.0%})"
        )

        dist = context.get("regime_distribution", {})
        if dist:
            user_parts.append(f"Regime-Verteilung (90d): {dist}")

        p30 = context.get("portfolio_30d", {})
        if p30:
            user_parts.append(
                f"\nPORTFOLIO (30d): Return {p30.get('total_return_pct', 0):+.1f}%, "
                f"Max-Drawdown {p30.get('max_drawdown_pct', 0):.1f}%, "
                f"Avg Daily {p30.get('avg_daily_return', 0):+.3f}%"
            )

        t30 = context.get("trading_30d", {})
        if t30:
            user_parts.append(
                f"TRADING (30d): P&L ${t30.get('total_pnl', 0):+.2f}, "
                f"{t30.get('trade_count', 0)} Trades, "
                f"Win-Rate {t30.get('win_rate', 0):.1f}%"
            )

        signals = context.get("signal_accuracy", [])
        if signals:
            signal_str = ", ".join(f"{s['signal']} {s['accuracy']:.0f}%" for s in signals[:3])
            user_parts.append(f"SIGNAL ACCURACY (Top 3): {signal_str}")

        tiers = context.get("current_tiers", {})
        if tiers:
            tier_str = ", ".join(
                f"{name}: {info['target_pct']:.0f}% (aktuell {info['current_pct']:.1f}%)"
                for name, info in tiers.items()
            )
            user_parts.append(f"\nAKTUELLE ZIELE: {tier_str}")

        prev = context.get("previous_recommendations", [])
        if prev:
            last = prev[0]
            user_parts.append(
                f"LETZTE EMPFEHLUNG: {last.get('allocations', {})} "
                f"(Confidence: {last.get('confidence', 0):.0%}, "
                f"Regime: {last.get('regime', '?')}, "
                f"Angewendet: {'Ja' if last.get('applied') else 'Nein'})"
            )

        return system_prompt, "\n".join(user_parts)

    def get_recommendation(self) -> dict:
        """Get AI recommendation for tier allocations.

        Returns:
            Dict with recommended allocations, confidence, reasoning.
            Empty dict on failure.
        """
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.warning("AI Optimizer: no DEEPSEEK_API_KEY configured")
            return {}

        context = self.gather_context()
        if not context:
            logger.warning("AI Optimizer: could not gather context")
            return {}

        system_prompt, user_prompt = self.build_prompt(context)

        try:
            from src.api.http_client import get_http_client

            http = get_http_client()
            response = http.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
                api_type="deepseek",
            )

            content = response["choices"][0]["message"]["content"]
            recommendation = self._parse_recommendation(content, context)

            if recommendation:
                self._store_recommendation(recommendation, context)

            return recommendation

        except Exception as e:
            logger.error(f"AI Optimizer API call failed: {e}")
            return {}

    def _parse_recommendation(self, response_text: str, context: dict) -> dict:
        """Parse and validate AI response."""
        try:
            # Extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start < 0 or end <= start:
                logger.error("AI Optimizer: no JSON in response")
                return {}

            data = json.loads(response_text[start:end])

            allocations = {
                "cash_reserve": float(data.get("cash_reserve", 10)),
                "index_holdings": float(data.get("index_holdings", 65)),
                "trading": float(data.get("trading", 25)),
            }
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "")

            # Validate: sum must be ~100
            allocations = _normalize(allocations, threshold=1.0)

            # Validate: within bounds
            for tier, (min_pct, max_pct) in ALLOCATION_BOUNDS.items():
                allocations[tier] = max(min_pct, min(max_pct, allocations[tier]))

            # Re-normalize after clamping
            allocations = _normalize(allocations)

            # Validate: max shift from current targets
            current_targets = {
                t: info["target_pct"] for t, info in context.get("current_tiers", {}).items()
            }
            if current_targets:
                for tier, val in allocations.items():
                    current = current_targets.get(tier, val)
                    shift = val - current
                    if abs(shift) > MAX_SHIFT_PP:
                        allocations[tier] = current + MAX_SHIFT_PP * (1 if shift > 0 else -1)

                # Final normalization
                allocations = _normalize(allocations)

            # Round to 1 decimal
            allocations = {k: round(v, 1) for k, v in allocations.items()}

            return {
                "allocations": allocations,
                "confidence": round(min(1.0, max(0.0, confidence)), 2),
                "reasoning": reasoning,
            }

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"AI Optimizer parse error: {e}")
            return {}

    def _store_recommendation(self, recommendation: dict, context: dict):
        """Store recommendation in ai_portfolio_recommendations table."""
        conn = get_db_connection()
        if not conn:
            return

        try:
            regime = context.get("current_regime", {}).get("regime", "UNKNOWN")
            current_allocs = {
                t: info.get("target_pct", 0) for t, info in context.get("current_tiers", {}).items()
            }

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_portfolio_recommendations
                        (recommended_allocations, current_allocations,
                         reasoning, confidence, market_regime)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        json.dumps(recommendation["allocations"]),
                        json.dumps(current_allocs),
                        recommendation.get("reasoning", ""),
                        recommendation["confidence"],
                        regime,
                    ),
                )
                conn.commit()

            logger.info(
                f"AI recommendation stored: {recommendation['allocations']} "
                f"(confidence: {recommendation['confidence']})"
            )

        except Exception as e:
            logger.error(f"Failed to store AI recommendation: {e}")
        finally:
            conn.close()

    def should_auto_apply(self, recommendation: dict) -> bool:
        """Check if recommendation should be auto-applied.

        Auto-apply conditions:
        - At least 3 previous recommendations exist (learning period)
        - Confidence > 0.8
        """
        if recommendation.get("confidence", 0) < 0.8:
            return False

        conn = get_db_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ai_portfolio_recommendations")
                count = cur.fetchone()[0]
                return count >= 3
        except Exception:
            return False
        finally:
            conn.close()

    def apply_recommendation(self, recommendation: dict) -> bool:
        """Apply recommendation by updating portfolio_tiers targets."""
        allocations = recommendation.get("allocations", {})
        if not allocations:
            return False

        conn = get_db_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                for tier_name, new_pct in allocations.items():
                    # Log history
                    cur.execute(
                        """
                        INSERT INTO tier_allocation_history
                            (tier_name, old_target_pct, new_target_pct,
                             reason, source, market_regime)
                        SELECT tier_name, target_pct, %s,
                               %s, 'ai_recommendation',
                               (SELECT regime FROM regime_history
                                ORDER BY detected_at DESC LIMIT 1)
                        FROM portfolio_tiers WHERE tier_name = %s
                        """,
                        (new_pct, recommendation.get("reasoning", ""), tier_name),
                    )

                    # Update target
                    cur.execute(
                        "UPDATE portfolio_tiers SET target_pct = %s, updated_at = NOW() "
                        "WHERE tier_name = %s",
                        (new_pct, tier_name),
                    )

                # Mark recommendation as applied
                cur.execute(
                    """
                    UPDATE ai_portfolio_recommendations
                    SET was_applied = TRUE
                    WHERE id = (
                        SELECT id FROM ai_portfolio_recommendations
                        ORDER BY timestamp DESC LIMIT 1
                    )
                    """
                )

                conn.commit()

            logger.info(f"AI recommendation applied: {allocations}")

            # Update in-memory targets
            if self.pm:
                self.pm._targets.update(allocations)

            return True

        except Exception as e:
            logger.error(f"Failed to apply AI recommendation: {e}")
            return False
        finally:
            conn.close()


def _normalize(allocations: dict, threshold: float = 0.1) -> dict:
    """Normalize allocation percentages to sum to 100."""
    total = sum(allocations.values())
    if abs(total - 100.0) > threshold and total > 0:
        return {k: v / total * 100 for k, v in allocations.items()}
    return allocations


def _calculate_max_drawdown(values: list[float]) -> float:
    """Calculate maximum drawdown percentage from a value series."""
    if len(values) < 2:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for v in values[1:]:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return max_dd
