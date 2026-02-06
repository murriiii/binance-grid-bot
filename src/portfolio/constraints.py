"""
Allocation Constraints für Portfolio Management.

Definiert Regeln und Limits für die Kapitalverteilung.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AllocationConstraints:
    """
    Constraints für die Portfolio-Allokation.

    Diese Regeln stellen sicher, dass das Portfolio:
    - Diversifiziert ist (max % pro Coin/Kategorie)
    - Risiko-kontrolliert ist (Cash Reserve)
    - Liquidität hat (min Position Size)
    """

    # Pro Coin Limits
    max_per_coin_pct: float = 10.0  # Max 10% des Portfolios pro Coin
    min_position_usd: float = 10.0  # Mindestposition (Binance Minimum)
    max_position_usd: float = 500.0  # Max Position pro Coin

    # Pro Kategorie Limits
    max_per_category_pct: float = 30.0  # Max 30% in einer Kategorie
    category_limits: dict[str, float] = field(
        default_factory=lambda: {
            "LARGE_CAP": 40.0,  # BTC, ETH können mehr bekommen
            "MID_CAP": 30.0,
            "L2": 20.0,
            "DEFI": 20.0,
            "AI": 15.0,
            "GAMING": 10.0,
        }
    )

    # Portfolio Limits
    min_cash_reserve_pct: float = 20.0  # Mindestens 20% Cash behalten
    max_open_positions: int = 10  # Max gleichzeitige Positionen
    max_total_exposure_pct: float = 80.0  # Max 80% investiert

    # Risk Limits
    max_correlated_positions: int = 3  # Max 3 Coins mit >0.7 Korrelation
    max_high_risk_allocation_pct: float = 15.0  # Max 15% in High-Risk
    correlation_threshold: float = 0.7  # Ab wann gelten Coins als korreliert

    # Rebalancing
    rebalance_threshold_pct: float = 5.0  # Rebalance wenn >5% Abweichung
    min_rebalance_interval_hours: int = 24  # Mindestens 24h zwischen Rebalances

    # Tier-basierte Limits
    tier_limits: dict[int, float] = field(
        default_factory=lambda: {
            1: 15.0,  # Primary Coins (BTC, ETH, SOL)
            2: 10.0,  # Secondary Coins
            3: 5.0,  # Experimental Coins
        }
    )

    def get_max_for_coin(
        self,
        symbol: str,
        category: str,
        tier: int,
    ) -> float:
        """
        Berechnet das maximale Allocation-Limit für einen Coin.

        Nimmt das Minimum aus allen anwendbaren Limits.
        """
        limits = [
            self.max_per_coin_pct,
            self.category_limits.get(category, self.max_per_category_pct),
            self.tier_limits.get(tier, self.max_per_coin_pct),
        ]

        # LARGE_CAP Coins bekommen etwas mehr Spielraum
        if category == "LARGE_CAP":
            limits.append(self.tier_limits.get(1, 15.0))

        return min(limits)

    def get_available_capital(
        self,
        total_capital: float,
        current_invested: float,
    ) -> float:
        """
        Berechnet das verfügbare Kapital für neue Investments.

        Berücksichtigt:
        - Cash Reserve Requirement
        - Max Total Exposure
        """
        min_cash = total_capital * (self.min_cash_reserve_pct / 100)
        max_invested = total_capital * (self.max_total_exposure_pct / 100)

        available = min(
            total_capital - current_invested - min_cash,
            max_invested - current_invested,
        )

        return max(0, available)

    def validate_allocation(
        self,
        proposed: dict[str, float],
        total_capital: float,
        current_portfolio: dict[str, dict],
    ) -> tuple[bool, list[str]]:
        """
        Validiert eine vorgeschlagene Allocation.

        Args:
            proposed: {symbol: amount_usd}
            total_capital: Gesamtkapital
            current_portfolio: {symbol: {category, tier, amount}}

        Returns:
            (is_valid, list_of_violations)
        """
        violations = []

        # Check Cash Reserve
        total_proposed = sum(proposed.values())
        current_invested = sum(p.get("amount", 0) for p in current_portfolio.values())
        new_total = current_invested + total_proposed

        if new_total > total_capital * (self.max_total_exposure_pct / 100):
            violations.append(
                f"Total exposure {new_total / total_capital * 100:.1f}% "
                f"exceeds max {self.max_total_exposure_pct}%"
            )

        # Check per-coin limits
        for symbol, amount in proposed.items():
            pct = (amount / total_capital) * 100
            coin_info = current_portfolio.get(symbol, {})
            max_allowed = self.get_max_for_coin(
                symbol,
                coin_info.get("category", "MID_CAP"),
                coin_info.get("tier", 2),
            )

            if pct > max_allowed:
                violations.append(f"{symbol}: {pct:.1f}% exceeds max {max_allowed:.1f}%")

        # Check position count
        new_positions = set(proposed.keys()) - set(current_portfolio.keys())
        total_positions = len(current_portfolio) + len(new_positions)

        if total_positions > self.max_open_positions:
            violations.append(
                f"Position count {total_positions} exceeds max {self.max_open_positions}"
            )

        # Check category limits
        category_totals: dict[str, float] = {}
        for symbol, amount in proposed.items():
            category = current_portfolio.get(symbol, {}).get("category", "MID_CAP")
            category_totals[category] = category_totals.get(category, 0) + amount

        for category, amount in category_totals.items():
            pct = (amount / total_capital) * 100
            max_cat = self.category_limits.get(category, self.max_per_category_pct)

            if pct > max_cat:
                violations.append(f"Category {category}: {pct:.1f}% exceeds max {max_cat:.1f}%")

        return len(violations) == 0, violations

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary für Speicherung."""
        return {
            "max_per_coin_pct": self.max_per_coin_pct,
            "min_position_usd": self.min_position_usd,
            "max_position_usd": self.max_position_usd,
            "max_per_category_pct": self.max_per_category_pct,
            "category_limits": self.category_limits,
            "min_cash_reserve_pct": self.min_cash_reserve_pct,
            "max_open_positions": self.max_open_positions,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "max_correlated_positions": self.max_correlated_positions,
            "max_high_risk_allocation_pct": self.max_high_risk_allocation_pct,
            "tier_limits": self.tier_limits,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AllocationConstraints:
        """Erstellt Constraints aus Dictionary."""
        return cls(
            max_per_coin_pct=data.get("max_per_coin_pct", 10.0),
            min_position_usd=data.get("min_position_usd", 10.0),
            max_position_usd=data.get("max_position_usd", 500.0),
            max_per_category_pct=data.get("max_per_category_pct", 30.0),
            category_limits=data.get("category_limits", {}),
            min_cash_reserve_pct=data.get("min_cash_reserve_pct", 20.0),
            max_open_positions=data.get("max_open_positions", 10),
            max_total_exposure_pct=data.get("max_total_exposure_pct", 80.0),
            max_correlated_positions=data.get("max_correlated_positions", 3),
            max_high_risk_allocation_pct=data.get("max_high_risk_allocation_pct", 15.0),
            tier_limits=data.get("tier_limits", {}),
        )


# Preset Constraints für verschiedene Strategien
CONSERVATIVE_CONSTRAINTS = AllocationConstraints(
    max_per_coin_pct=8.0,
    max_per_category_pct=25.0,
    min_cash_reserve_pct=30.0,
    max_open_positions=6,
    max_total_exposure_pct=70.0,
    max_high_risk_allocation_pct=10.0,
)

BALANCED_CONSTRAINTS = AllocationConstraints(
    max_per_coin_pct=10.0,
    max_per_category_pct=30.0,
    min_cash_reserve_pct=20.0,
    max_open_positions=10,
    max_total_exposure_pct=80.0,
    max_high_risk_allocation_pct=15.0,
)

AGGRESSIVE_CONSTRAINTS = AllocationConstraints(
    max_per_coin_pct=15.0,
    max_per_category_pct=40.0,
    min_cash_reserve_pct=10.0,
    max_open_positions=15,
    max_total_exposure_pct=90.0,
    max_high_risk_allocation_pct=25.0,
)

SMALL_PORTFOLIO_CONSTRAINTS = AllocationConstraints(
    max_per_coin_pct=40.0,
    min_position_usd=10.0,
    max_position_usd=80.0,
    max_per_category_pct=50.0,
    min_cash_reserve_pct=15.0,
    max_open_positions=8,
    max_total_exposure_pct=85.0,
    max_high_risk_allocation_pct=30.0,
    tier_limits={1: 50.0, 2: 40.0, 3: 30.0},
)
