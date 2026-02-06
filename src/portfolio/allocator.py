"""
Portfolio Allocator für Multi-Coin Trading.

Verteilt Kapital intelligent auf Coins basierend auf:
- Opportunity Scores
- Risk Constraints
- Kelly Criterion
- Korrelationen
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv

from src.portfolio.constraints import (
    AGGRESSIVE_CONSTRAINTS,
    BALANCED_CONSTRAINTS,
    CONSERVATIVE_CONSTRAINTS,
    AllocationConstraints,
)
from src.scanner.opportunity import Opportunity, OpportunityRisk

load_dotenv()

logger = logging.getLogger("trading_bot")

# PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


@dataclass
class AllocationResult:
    """Ergebnis einer Allocation-Berechnung."""

    allocations: dict[str, float] = field(default_factory=dict)  # {symbol: amount_usd}
    total_allocated: float = 0.0
    cash_remaining: float = 0.0
    rejected: dict[str, str] = field(default_factory=dict)  # {symbol: reason}
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "allocations": self.allocations,
            "total_allocated": self.total_allocated,
            "cash_remaining": self.cash_remaining,
            "rejected": self.rejected,
            "timestamp": self.timestamp.isoformat(),
        }


class PortfolioAllocator:
    """
    Verteilt Kapital intelligent auf Coins.

    Verwendet einen Score-basierten Ansatz mit Kelly-Anpassung:
    1. Normalisiere Opportunity Scores
    2. Wende Kelly Fraction für Position Sizing an
    3. Enforced Constraints (max per coin, category, etc.)
    4. Berücksichtige Korrelationen

    Usage:
        allocator = PortfolioAllocator.get_instance()
        result = allocator.calculate_allocation(
            opportunities=top_opportunities,
            available_capital=1000.0,
        )
    """

    _instance: PortfolioAllocator | None = None

    def __init__(
        self,
        constraints: AllocationConstraints | None = None,
    ):
        self.conn = None
        self.constraints = constraints or BALANCED_CONSTRAINTS
        self._current_portfolio: dict[str, dict] = {}
        self._correlations: dict[tuple[str, str], float] = {}
        self.connect()

    @classmethod
    def get_instance(cls) -> PortfolioAllocator:
        """Singleton-Instanz."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset für Tests."""
        if cls._instance is not None:
            if cls._instance.conn:
                cls._instance.conn.close()
            cls._instance = None

    def connect(self) -> bool:
        """Verbindet zur PostgreSQL Datenbank."""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - PortfolioAllocator eingeschränkt")
            return False

        try:
            self.conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", 5432),
                database=os.getenv("POSTGRES_DB", "trading_bot"),
                user=os.getenv("POSTGRES_USER", "trading"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
            )
            logger.info("PortfolioAllocator: PostgreSQL verbunden")
            return True
        except Exception as e:
            logger.error(f"PortfolioAllocator: PostgreSQL Fehler: {e}")
            self.conn = None
            return False

    def set_constraints(self, constraints: AllocationConstraints) -> None:
        """Setzt neue Allocation Constraints."""
        self.constraints = constraints

    def _get_regime_constraints(self, regime: str | None) -> AllocationConstraints:
        """Return constraints appropriate for the given market regime."""
        regime_constraints = {
            "BULL": AGGRESSIVE_CONSTRAINTS,
            "SIDEWAYS": BALANCED_CONSTRAINTS,
            "BEAR": CONSERVATIVE_CONSTRAINTS,
        }
        return (
            regime_constraints.get(regime, BALANCED_CONSTRAINTS) if regime else BALANCED_CONSTRAINTS
        )

    def calculate_allocation(
        self,
        opportunities: list[Opportunity],
        available_capital: float,
        current_portfolio: dict[str, dict] | None = None,
        cohort_id: str | None = None,
        regime: str | None = None,
    ) -> AllocationResult:
        """
        Berechnet die optimale Kapitalverteilung.

        Args:
            opportunities: Liste von Opportunities (sortiert nach Score)
            available_capital: Verfügbares Kapital in USD
            current_portfolio: {symbol: {amount, category, tier}}
            cohort_id: Optional Cohort für DB-Tracking
            regime: Market regime (BULL/BEAR/SIDEWAYS) for auto-constraints

        Returns:
            AllocationResult mit {symbol: amount_usd}
        """
        # Auto-select constraints based on regime if provided
        if regime:
            self.constraints = self._get_regime_constraints(regime)

        result = AllocationResult(cash_remaining=available_capital)

        if not opportunities:
            logger.debug("PortfolioAllocator: Keine Opportunities")
            return result

        if current_portfolio:
            self._current_portfolio = current_portfolio

        # Berechne verfügbares Kapital unter Berücksichtigung der Constraints
        total_capital = available_capital + sum(
            p.get("amount", 0) for p in self._current_portfolio.values()
        )
        actual_available = self.constraints.get_available_capital(
            total_capital,
            sum(p.get("amount", 0) for p in self._current_portfolio.values()),
        )

        if actual_available < self.constraints.min_position_usd:
            logger.debug("PortfolioAllocator: Nicht genug verfügbares Kapital")
            return result

        # Filtere bereits gehaltene Positionen und Low-Score Opportunities
        filtered_opps = [
            o
            for o in opportunities
            if o.symbol not in self._current_portfolio
            and o.total_score >= 0.4
            and o.confidence >= 0.3
        ]

        if not filtered_opps:
            logger.debug("PortfolioAllocator: Keine neuen Opportunities nach Filter")
            return result

        # Berechne Score-gewichtete Allocation
        allocations = self._calculate_score_weighted_allocation(
            filtered_opps,
            actual_available,
            total_capital,
        )

        # Wende Kelly Fraction an
        allocations = self._apply_kelly_adjustment(allocations, filtered_opps)

        # Validiere gegen Constraints
        valid, violations = self.constraints.validate_allocation(
            allocations,
            total_capital,
            self._current_portfolio,
        )

        if not valid:
            # Reduziere Allocations bis sie valide sind
            allocations = self._reduce_to_constraints(
                allocations,
                total_capital,
                violations,
            )

        # Filtere zu kleine Positionen
        final_allocations = {}
        for symbol, amount in allocations.items():
            if amount >= self.constraints.min_position_usd:
                final_allocations[symbol] = amount
            else:
                result.rejected[symbol] = f"Position too small (${amount:.2f})"

        result.allocations = final_allocations
        result.total_allocated = sum(final_allocations.values())
        result.cash_remaining = available_capital - result.total_allocated

        # In DB speichern
        if cohort_id:
            self._store_allocation(result, cohort_id)

        logger.info(
            f"PortfolioAllocator: {len(final_allocations)} Allocations, "
            f"${result.total_allocated:.2f} allocated"
        )

        return result

    def _calculate_score_weighted_allocation(
        self,
        opportunities: list[Opportunity],
        available_capital: float,
        total_capital: float,
    ) -> dict[str, float]:
        """
        Berechnet Score-gewichtete Allocation.

        Höhere Scores bekommen proportional mehr Kapital.
        """
        allocations = {}

        # Normalisiere Scores
        total_score = sum(o.total_score for o in opportunities)
        if total_score == 0:
            return {}

        for opp in opportunities:
            # Basis-Allocation proportional zum Score
            score_weight = opp.total_score / total_score
            base_allocation = available_capital * score_weight

            # Max per coin limit
            max_for_coin = (
                total_capital
                * self.constraints.get_max_for_coin(
                    opp.symbol,
                    opp.category,
                    1 if opp.category == "LARGE_CAP" else 2,
                )
            ) / 100

            # Risk-based adjustment
            risk_multiplier = self._get_risk_multiplier(opp.risk_level)

            allocation = min(base_allocation * risk_multiplier, max_for_coin)
            allocation = min(allocation, self.constraints.max_position_usd)

            if allocation >= self.constraints.min_position_usd:
                allocations[opp.symbol] = allocation

        return allocations

    def _get_risk_multiplier(self, risk_level: OpportunityRisk) -> float:
        """Gibt den Risiko-Multiplikator zurück."""
        multipliers = {
            OpportunityRisk.LOW: 1.2,  # Low Risk = mehr Allocation
            OpportunityRisk.MEDIUM: 1.0,
            OpportunityRisk.HIGH: 0.7,  # High Risk = weniger Allocation
        }
        return multipliers.get(risk_level, 1.0)

    def _apply_kelly_adjustment(
        self,
        allocations: dict[str, float],
        opportunities: list[Opportunity],
    ) -> dict[str, float]:
        """
        Wendet Kelly Criterion Adjustment an.

        Kelly Fraction = (bp - q) / b
        wobei:
        - b = odds (vereinfacht: expected return ratio)
        - p = win probability (approximiert durch confidence)
        - q = 1 - p

        Wir verwenden Half-Kelly für konservativere Sizing.
        """
        opp_by_symbol = {o.symbol: o for o in opportunities}

        for symbol, amount in allocations.items():
            opp = opp_by_symbol.get(symbol)
            if not opp:
                continue

            # Vereinfachte Kelly Berechnung
            p = opp.confidence  # Win probability
            q = 1 - p

            # Geschätzter Return basierend auf Score
            b = 1.0 + (opp.total_score * 0.5)  # 0-50% expected return

            kelly = (b * p - q) / b if b > 0 else 0
            half_kelly = max(0, kelly / 2)

            # Kelly-adjustierte Allocation
            allocations[symbol] = amount * (0.5 + half_kelly * 0.5)

        return allocations

    def _reduce_to_constraints(
        self,
        allocations: dict[str, float],
        total_capital: float,
        violations: list[str],
    ) -> dict[str, float]:
        """
        Reduziert Allocations um Constraints einzuhalten.

        Iterativ reduzieren bis alle Constraints erfüllt sind.
        """
        # Einfache Strategie: Proportional reduzieren
        iteration = 0
        max_iterations = 10

        while iteration < max_iterations:
            iteration += 1

            valid, _new_violations = self.constraints.validate_allocation(
                allocations,
                total_capital,
                self._current_portfolio,
            )

            if valid:
                break

            # Reduziere alle Allocations um 10%
            allocations = {s: a * 0.9 for s, a in allocations.items()}

        return allocations

    def _store_allocation(
        self,
        result: AllocationResult,
        cohort_id: str,
    ) -> None:
        """Speichert Allocation-Ergebnis in der Datenbank."""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                for symbol, amount in result.allocations.items():
                    cur.execute(
                        """
                        INSERT INTO cohort_allocations (
                            cohort_id, symbol, target_allocation_pct, position_usd
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (cohort_id, symbol, cycle_id)
                        DO UPDATE SET
                            target_allocation_pct = EXCLUDED.target_allocation_pct,
                            position_usd = EXCLUDED.position_usd,
                            updated_at = NOW()
                        """,
                        (cohort_id, symbol, amount / result.total_allocated * 100, amount),
                    )
                self.conn.commit()
        except Exception as e:
            logger.error(f"PortfolioAllocator: DB store error: {e}")
            self.conn.rollback()

    def get_current_positions(
        self,
        cohort_id: str | None = None,
    ) -> dict[str, dict]:
        """
        Holt aktuelle Positionen aus der Datenbank.

        Returns:
            {symbol: {amount, category, tier, entry_price}}
        """
        if not self.conn:
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT
                        ca.symbol,
                        ca.position_usd as amount,
                        ca.avg_entry_price as entry_price,
                        w.category,
                        w.tier
                    FROM cohort_allocations ca
                    JOIN watchlist w ON ca.symbol = w.symbol
                    WHERE ca.status = 'active'
                """
                if cohort_id:
                    query += " AND ca.cohort_id = %s"
                    cur.execute(query, (cohort_id,))
                else:
                    cur.execute(query)

                positions = {}
                for row in cur.fetchall():
                    positions[row["symbol"]] = {
                        "amount": float(row["amount"]) if row["amount"] else 0,
                        "entry_price": float(row["entry_price"]) if row["entry_price"] else 0,
                        "category": row["category"],
                        "tier": row["tier"],
                    }

                return positions

        except Exception as e:
            logger.error(f"PortfolioAllocator: Get positions error: {e}")
            return {}

    def calculate_rebalance(
        self,
        target_allocations: dict[str, float],
        current_positions: dict[str, dict],
        available_cash: float,
    ) -> dict[str, dict]:
        """
        Berechnet notwendige Trades für Rebalancing.

        Returns:
            {symbol: {action: BUY/SELL, amount: float}}
        """
        trades = {}

        # Neue Positionen
        for symbol, target in target_allocations.items():
            current = current_positions.get(symbol, {}).get("amount", 0)
            diff = target - current

            if abs(diff) < self.constraints.min_position_usd:
                continue

            if diff > 0:
                trades[symbol] = {"action": "BUY", "amount": diff}
            else:
                trades[symbol] = {"action": "SELL", "amount": abs(diff)}

        # Positionen die nicht mehr im Target sind -> SELL
        for symbol, pos in current_positions.items():
            if symbol not in target_allocations and pos.get("amount", 0) > 0:
                trades[symbol] = {"action": "SELL", "amount": pos["amount"]}

        return trades

    def get_portfolio_stats(
        self,
        cohort_id: str | None = None,
    ) -> dict:
        """Gibt Portfolio-Statistiken zurück."""
        positions = self.get_current_positions(cohort_id)

        if not positions:
            return {
                "total_value": 0,
                "position_count": 0,
                "by_category": {},
            }

        total_value = sum(p.get("amount", 0) for p in positions.values())

        by_category: dict[str, float] = {}
        for symbol, pos in positions.items():
            cat = pos.get("category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + pos.get("amount", 0)

        return {
            "total_value": total_value,
            "position_count": len(positions),
            "by_category": by_category,
            "positions": positions,
        }


# Convenience-Funktion
def get_portfolio_allocator() -> PortfolioAllocator:
    """Gibt die globale PortfolioAllocator-Instanz zurück."""
    return PortfolioAllocator.get_instance()
