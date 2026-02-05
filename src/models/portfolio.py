"""
Portfolio Optimization Models
Basierend auf klassischer Portfolio-Theorie (Markowitz et al.)
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass
class Asset:
    symbol: str
    expected_return: float  # Annualisiert
    volatility: float  # Standardabweichung annualisiert
    weight: float = 0.0


class PortfolioOptimizer:
    """
    Markowitz Mean-Variance Optimization für Krypto-Portfolio.

    Unterschiede zu klassischen Assets:
    - Höhere Volatilität
    - Fat Tails (nicht normalverteilt)
    - Korrelationen ändern sich schnell
    - 24/7 Markt
    """

    def __init__(self, risk_free_rate: float = 0.05):
        self.risk_free_rate = risk_free_rate  # ~5% (Stablecoin Staking)
        self.returns_data: pd.DataFrame = None
        self.cov_matrix: np.ndarray = None
        self.mean_returns: np.ndarray = None
        self.assets: list[str] = []

    def load_returns(self, price_data: pd.DataFrame):
        """
        Lädt Preisdaten und berechnet Returns.
        price_data: DataFrame mit Spalten = Asset-Namen, Index = Datum
        """
        self.assets = list(price_data.columns)

        # Log-Returns (besser für Finanzanalyse)
        self.returns_data = np.log(price_data / price_data.shift(1)).dropna()

        # Annualisierte Metriken (365 Tage für Krypto)
        self.mean_returns = self.returns_data.mean() * 365
        self.cov_matrix = self.returns_data.cov() * 365

    def portfolio_return(self, weights: np.ndarray) -> float:
        """Erwartete Portfolio-Rendite"""
        return np.dot(weights, self.mean_returns)

    def portfolio_volatility(self, weights: np.ndarray) -> float:
        """Portfolio-Volatilität (Standardabweichung)"""
        return np.sqrt(np.dot(weights.T, np.dot(self.cov_matrix, weights)))

    def sharpe_ratio(self, weights: np.ndarray) -> float:
        """
        Sharpe Ratio = (Return - Risk-Free) / Volatility
        Misst risiko-adjustierte Performance
        """
        ret = self.portfolio_return(weights)
        vol = self.portfolio_volatility(weights)
        return (ret - self.risk_free_rate) / vol if vol > 0 else 0

    def negative_sharpe(self, weights: np.ndarray) -> float:
        """Für Minimierung (scipy minimiert)"""
        return -self.sharpe_ratio(weights)

    def optimize_sharpe(self) -> dict[str, float]:
        """
        Findet Portfolio mit maximaler Sharpe Ratio.
        Returns: Dict mit Asset -> Gewichtung
        """
        n_assets = len(self.assets)

        # Constraints: Gewichte summieren zu 1, alle >= 0
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
        bounds = tuple((0, 1) for _ in range(n_assets))

        # Startpunkt: Gleichgewichtung
        initial_weights = np.array([1 / n_assets] * n_assets)

        result = minimize(
            self.negative_sharpe,
            initial_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        optimal_weights = result.x
        return {asset: round(weight, 4) for asset, weight in zip(self.assets, optimal_weights)}

    def optimize_min_variance(self) -> dict[str, float]:
        """
        Minimum-Varianz Portfolio.
        Für risiko-averse Investoren.
        """
        n_assets = len(self.assets)

        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
        bounds = tuple((0, 1) for _ in range(n_assets))
        initial_weights = np.array([1 / n_assets] * n_assets)

        result = minimize(
            self.portfolio_volatility,
            initial_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        return {asset: round(weight, 4) for asset, weight in zip(self.assets, result.x)}

    def efficient_frontier(self, n_points: int = 50) -> list[tuple[float, float]]:
        """
        Berechnet die Effizienzgrenze.
        Returns: Liste von (Volatilität, Return) Tupeln
        """
        # Finde min und max mögliche Returns
        min_ret = self.mean_returns.min()
        max_ret = self.mean_returns.max()

        target_returns = np.linspace(min_ret, max_ret, n_points)
        frontier = []

        n_assets = len(self.assets)
        bounds = tuple((0, 1) for _ in range(n_assets))

        for target in target_returns:
            constraints = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1},
                {"type": "eq", "fun": lambda w, t=target: self.portfolio_return(w) - t},
            ]

            result = minimize(
                self.portfolio_volatility,
                np.array([1 / n_assets] * n_assets),
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
            )

            if result.success:
                vol = self.portfolio_volatility(result.x)
                frontier.append((vol, target))

        return frontier


class KellyCriterion:
    """
    Kelly Criterion für optimale Positionsgröße.

    f* = (p * b - q) / b

    Wobei:
    - p = Gewinnwahrscheinlichkeit
    - q = Verlustwahrscheinlichkeit (1-p)
    - b = Gewinn/Verlust Ratio

    Für Krypto: Oft "Fractional Kelly" (25-50%) wegen hoher Unsicherheit
    """

    @staticmethod
    def optimal_fraction(
        win_rate: float,
        win_loss_ratio: float,
        fraction: float = 0.25,  # 25% Kelly für Sicherheit
    ) -> float:
        """
        Berechnet optimale Positionsgröße.

        Args:
            win_rate: Historische Gewinnrate (0-1)
            win_loss_ratio: Durchschnittlicher Gewinn / Durchschnittlicher Verlust
            fraction: Anteil des Kelly-Wertes (0.25 = Quarter Kelly)

        Returns:
            Optimaler Anteil des Portfolios pro Trade
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0

        q = 1 - win_rate
        kelly = (win_rate * win_loss_ratio - q) / win_loss_ratio

        # Nie mehr als 100%, nie negativ
        kelly = max(0, min(kelly, 1))

        return kelly * fraction


class RiskScaler:
    """
    Dynamische Risiko-Allokation basierend auf Portfolio-Größe.

    Philosophie: Mit kleinem Kapital kann man mehr riskieren,
    da der absolute Verlust verkraftbar ist. Bei größerem
    Vermögen wird Kapitalerhalt wichtiger.
    """

    def __init__(self, thresholds: list[tuple[float, float]] = None):
        """
        Args:
            thresholds: Liste von (Portfolio-Größe, Altcoin-Anteil)
                        Sortiert nach Größe aufsteigend
        """
        self.thresholds = thresholds or [
            (0, 0.80),  # <100€: 80% Altcoins
            (100, 0.60),  # 100-500€: 60% Altcoins
            (500, 0.40),  # 500-1000€: 40% Altcoins
            (1000, 0.25),  # 1000-5000€: 25% Altcoins
            (5000, 0.15),  # >5000€: 15% Altcoins
        ]

    def get_altcoin_allocation(self, portfolio_value: float) -> float:
        """
        Gibt empfohlenen Altcoin-Anteil basierend auf Portfolio-Größe.
        """
        allocation = self.thresholds[0][1]  # Default

        for threshold, alloc in self.thresholds:
            if portfolio_value >= threshold:
                allocation = alloc

        return allocation

    def get_allocation_reasoning(self, portfolio_value: float) -> str:
        """
        Gibt Begründung für die Allokation.
        Für Lernzwecke / Transparenz.
        """
        altcoin_pct = self.get_altcoin_allocation(portfolio_value) * 100
        stable_pct = 100 - altcoin_pct

        if portfolio_value < 100:
            risk_level = "AGGRESSIV"
            reasoning = (
                f"Bei {portfolio_value:.2f}€ ist der absolute Verlust begrenzt. "
                f"Maximale Wachstumschance durch {altcoin_pct:.0f}% Altcoins."
            )
        elif portfolio_value < 1000:
            risk_level = "MODERAT"
            reasoning = (
                f"Portfolio wächst. Balance zwischen Wachstum ({altcoin_pct:.0f}% Altcoins) "
                f"und Sicherheit ({stable_pct:.0f}% Large-Caps)."
            )
        else:
            risk_level = "KONSERVATIV"
            reasoning = (
                f"Kapitalerhalt priorisiert. Nur {altcoin_pct:.0f}% in riskanteren Altcoins, "
                f"{stable_pct:.0f}% in etablierten Coins."
            )

        return f"[{risk_level}] {reasoning}"
