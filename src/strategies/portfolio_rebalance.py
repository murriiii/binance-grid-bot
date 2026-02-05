"""
Portfolio Rebalancing Strategy
Kombiniert Markowitz-Optimierung mit dynamischer Risiko-Skalierung
"""

from datetime import datetime

import pandas as pd

from src.models.portfolio import PortfolioOptimizer, RiskScaler


class PortfolioRebalanceStrategy:
    """
    Intelligente Portfolio-Strategie die:
    1. Markowitz-Optimierung für Asset-Allokation nutzt
    2. Risiko basierend auf Portfolio-Größe skaliert
    3. Regelmäßig rebalanciert
    4. Jede Entscheidung begründet
    """

    # Coin-Kategorien
    LARGE_CAP = ["BTC", "ETH"]
    MID_CAP = ["SOL", "AVAX", "LINK", "DOT"]
    SMALL_CAP = ["MATIC", "ARB", "OP", "INJ"]  # Höheres Risiko

    def __init__(
        self,
        rebalance_threshold: float = 0.05,  # 5% Abweichung triggert Rebalance
        lookback_days: int = 30,  # Tage für Volatilitäts-Berechnung
        min_trade_value: float = 1.0,  # Mindest-Trade-Wert
    ):
        self.rebalance_threshold = rebalance_threshold
        self.lookback_days = lookback_days
        self.min_trade_value = min_trade_value

        self.risk_scaler = RiskScaler()
        self.last_rebalance: datetime = None
        self.target_weights: dict[str, float] = {}

    def calculate_target_weights(
        self, price_history: pd.DataFrame, portfolio_value: float, available_coins: list[str]
    ) -> tuple[dict[str, float], str]:
        """
        Berechnet Ziel-Gewichtung basierend auf:
        1. Portfolio-Größe (Risiko-Skalierung)
        2. Historischer Performance (Markowitz)

        Returns:
            (weights_dict, reasoning_string)
        """
        # 1. Risiko-Level basierend auf Portfolio-Größe
        altcoin_allocation = self.risk_scaler.get_altcoin_allocation(portfolio_value)
        risk_reasoning = self.risk_scaler.get_allocation_reasoning(portfolio_value)

        # 2. Kategorisiere verfügbare Coins
        large_caps = [c for c in available_coins if c in self.LARGE_CAP]
        altcoins = [c for c in available_coins if c not in self.LARGE_CAP]

        # 3. Markowitz-Optimierung für Altcoin-Teil
        weights = {}

        # Large-Cap Anteil (1 - altcoin_allocation)
        large_cap_total = 1 - altcoin_allocation
        if large_caps:
            # Einfache Gleichverteilung für Large-Caps
            for coin in large_caps:
                weights[coin] = large_cap_total / len(large_caps)

        # Altcoin-Anteil mit Optimierung
        if altcoins and len(price_history) >= self.lookback_days:
            altcoin_prices = price_history[altcoins].tail(self.lookback_days)

            optimizer = PortfolioOptimizer()
            optimizer.load_returns(altcoin_prices)

            # Optimiere Sharpe Ratio innerhalb der Altcoins
            optimal_altcoin_weights = optimizer.optimize_sharpe()

            # Skaliere auf Altcoin-Allokation
            for coin, w in optimal_altcoin_weights.items():
                weights[coin] = w * altcoin_allocation

            optimization_reasoning = (
                f"Markowitz-Optimierung (Sharpe): "
                f"Top-Picks: {', '.join([f'{k}:{v * 100:.1f}%' for k, v in sorted(optimal_altcoin_weights.items(), key=lambda x: -x[1])[:3]])}"
            )
        else:
            # Fallback: Gleichverteilung
            if altcoins:
                for coin in altcoins:
                    weights[coin] = altcoin_allocation / len(altcoins)
            optimization_reasoning = "Gleichverteilung (nicht genug Historie für Optimierung)"

        full_reasoning = f"{risk_reasoning} | {optimization_reasoning}"

        return weights, full_reasoning

    def get_rebalance_trades(
        self,
        current_positions: dict[str, float],
        target_weights: dict[str, float],
        prices: dict[str, float],
        portfolio_value: float,
    ) -> list[dict]:
        """
        Berechnet nötige Trades für Rebalancing.
        Minimiert Trades durch Threshold.
        """
        trades = []

        # Aktuelle Gewichtungen
        current_weights = {}
        for coin, qty in current_positions.items():
            if coin in prices:
                current_weights[coin] = (qty * prices[coin]) / portfolio_value

        # Alle relevanten Coins
        all_coins = set(current_weights.keys()) | set(target_weights.keys())

        for coin in all_coins:
            current_w = current_weights.get(coin, 0)
            target_w = target_weights.get(coin, 0)
            diff = target_w - current_w

            # Ignoriere kleine Abweichungen
            if abs(diff) < self.rebalance_threshold:
                continue

            trade_value = diff * portfolio_value

            if abs(trade_value) < self.min_trade_value:
                continue

            if trade_value > 0:
                trades.append(
                    {
                        "action": "BUY",
                        "symbol": coin,
                        "value": trade_value,
                        "reason": f"Untergewichtet ({current_w * 100:.1f}% → {target_w * 100:.1f}%)",
                    }
                )
            else:
                trades.append(
                    {
                        "action": "SELL",
                        "symbol": coin,
                        "value": abs(trade_value),
                        "reason": f"Übergewichtet ({current_w * 100:.1f}% → {target_w * 100:.1f}%)",
                    }
                )

        return trades


def portfolio_rebalance_strategy(
    engine,
    timestamp: datetime,
    prices: dict[str, float],
    price_history: pd.DataFrame,
    rebalance_interval_days: int = 7,
    **kwargs,
):
    """
    Strategy-Funktion für den Backtester.

    Rebalanciert das Portfolio basierend auf Markowitz-Optimierung
    und dynamischer Risiko-Skalierung.
    """
    strategy = kwargs.get("_strategy_instance")
    if strategy is None:
        strategy = PortfolioRebalanceStrategy()
        kwargs["_strategy_instance"] = strategy

    # Initial: Alles in Cash, noch keine Positionen
    if not engine.positions and engine.cash > 0:
        # Erstes Investment
        portfolio_value = engine.cash
        available_coins = [c for c in prices if c in price_history.columns]

        # Hole historische Daten bis zu diesem Zeitpunkt
        historical = price_history[price_history.index <= timestamp]

        weights, reasoning = strategy.calculate_target_weights(
            historical, portfolio_value, available_coins
        )

        # Kaufe initiale Positionen
        for coin, weight in weights.items():
            if weight > 0 and coin in prices:
                amount = portfolio_value * weight
                if amount >= 1.0:  # Min Trade
                    engine.execute_buy(
                        timestamp,
                        coin,
                        amount,
                        prices[coin],
                        f"Initial Allocation: {weight * 100:.1f}% | {reasoning}",
                    )
        return

    # Prüfe ob Rebalancing nötig
    if strategy.last_rebalance:
        days_since = (timestamp - strategy.last_rebalance).days
        if days_since < rebalance_interval_days:
            return

    # Berechne aktuelle Portfolio-Wert
    portfolio_value = engine.get_portfolio_value(prices)

    # Hole historische Daten
    historical = price_history[price_history.index <= timestamp]
    available_coins = [c for c in prices if c in historical.columns]

    # Berechne neue Ziel-Gewichtungen
    target_weights, reasoning = strategy.calculate_target_weights(
        historical, portfolio_value, available_coins
    )

    # Berechne nötige Trades
    trades = strategy.get_rebalance_trades(
        engine.positions, target_weights, prices, portfolio_value
    )

    # Führe Trades aus (Sells zuerst für Liquidität)
    sells = [t for t in trades if t["action"] == "SELL"]
    buys = [t for t in trades if t["action"] == "BUY"]

    for trade in sells:
        qty = trade["value"] / prices[trade["symbol"]]
        engine.execute_sell(
            timestamp,
            trade["symbol"],
            qty,
            prices[trade["symbol"]],
            f"Rebalance: {trade['reason']} | {reasoning}",
        )

    for trade in buys:
        engine.execute_buy(
            timestamp,
            trade["symbol"],
            trade["value"],
            prices[trade["symbol"]],
            f"Rebalance: {trade['reason']} | {reasoning}",
        )

    strategy.last_rebalance = timestamp
