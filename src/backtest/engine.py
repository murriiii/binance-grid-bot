"""
Backtesting Engine
Simuliert Trading-Strategien auf historischen Daten
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from datetime import datetime
from enum import Enum


class TradeType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    REBALANCE = "REBALANCE"


@dataclass
class Trade:
    """Einzelner Trade mit Begründung"""
    timestamp: datetime
    symbol: str
    trade_type: TradeType
    quantity: float
    price: float
    value: float  # quantity * price
    fee: float
    reasoning: str  # WICHTIG: Warum dieser Trade?

    # Nach dem Trade
    portfolio_value: float = 0.0
    pnl: float = 0.0  # Profit/Loss dieses Trades


@dataclass
class BacktestResult:
    """Ergebnis eines Backtests"""
    # Performance
    initial_value: float
    final_value: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float

    # Trades
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float

    # Daten für Analyse
    trades: List[Trade]
    portfolio_history: pd.DataFrame


class BacktestEngine:
    """
    Event-driven Backtesting Engine.

    Features:
    - Realistische Fee-Berechnung (Binance: 0.1%)
    - Slippage-Simulation
    - Trade-Begründungen für Lernzwecke
    - Detaillierte Performance-Metriken
    """

    def __init__(
        self,
        initial_capital: float = 10.0,
        fee_rate: float = 0.001,  # 0.1% Binance
        slippage: float = 0.0005  # 0.05% Slippage
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage

        # State
        self.cash = initial_capital
        self.positions: Dict[str, float] = {}  # symbol -> quantity
        self.trades: List[Trade] = []
        self.portfolio_history: List[Dict] = []

    def reset(self):
        """Reset für neuen Backtest"""
        self.cash = self.initial_capital
        self.positions = {}
        self.trades = []
        self.portfolio_history = []

    def get_portfolio_value(self, prices: Dict[str, float]) -> float:
        """Aktueller Portfolio-Wert"""
        positions_value = sum(
            qty * prices.get(symbol, 0)
            for symbol, qty in self.positions.items()
        )
        return self.cash + positions_value

    def execute_buy(
        self,
        timestamp: datetime,
        symbol: str,
        amount_usd: float,
        price: float,
        reasoning: str
    ) -> Optional[Trade]:
        """
        Führt einen Buy aus.

        Args:
            timestamp: Zeitpunkt
            symbol: z.B. "BTC"
            amount_usd: Wie viel USD ausgeben
            price: Aktueller Preis
            reasoning: WARUM kaufen wir?
        """
        # Slippage (kaufen teurer)
        exec_price = price * (1 + self.slippage)

        # Fee
        fee = amount_usd * self.fee_rate
        net_amount = amount_usd - fee

        # Können wir uns das leisten?
        if net_amount > self.cash:
            return None

        quantity = net_amount / exec_price

        # Ausführen
        self.cash -= amount_usd
        self.positions[symbol] = self.positions.get(symbol, 0) + quantity

        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            trade_type=TradeType.BUY,
            quantity=quantity,
            price=exec_price,
            value=amount_usd,
            fee=fee,
            reasoning=reasoning
        )

        self.trades.append(trade)
        return trade

    def execute_sell(
        self,
        timestamp: datetime,
        symbol: str,
        quantity: float,
        price: float,
        reasoning: str
    ) -> Optional[Trade]:
        """
        Führt einen Sell aus.
        """
        # Haben wir genug?
        if self.positions.get(symbol, 0) < quantity:
            quantity = self.positions.get(symbol, 0)

        if quantity <= 0:
            return None

        # Slippage (verkaufen billiger)
        exec_price = price * (1 - self.slippage)

        gross_value = quantity * exec_price
        fee = gross_value * self.fee_rate
        net_value = gross_value - fee

        # Ausführen
        self.positions[symbol] -= quantity
        if self.positions[symbol] <= 0:
            del self.positions[symbol]
        self.cash += net_value

        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            trade_type=TradeType.SELL,
            quantity=quantity,
            price=exec_price,
            value=gross_value,
            fee=fee,
            reasoning=reasoning
        )

        self.trades.append(trade)
        return trade

    def run(
        self,
        price_data: pd.DataFrame,
        strategy: Callable,
        **strategy_params
    ) -> BacktestResult:
        """
        Führt Backtest durch.

        Args:
            price_data: DataFrame mit Close-Preisen (Spalten = Symbole)
            strategy: Funktion(engine, timestamp, prices, **params) -> None
            **strategy_params: Parameter für die Strategie
        """
        self.reset()

        for timestamp, row in price_data.iterrows():
            prices = row.to_dict()

            # Strategie ausführen
            strategy(self, timestamp, prices, **strategy_params)

            # Portfolio-State speichern
            portfolio_value = self.get_portfolio_value(prices)
            self.portfolio_history.append({
                'timestamp': timestamp,
                'cash': self.cash,
                'positions_value': portfolio_value - self.cash,
                'total_value': portfolio_value,
                **{f"pos_{k}": v for k, v in self.positions.items()}
            })

        return self._calculate_results()

    def _calculate_results(self) -> BacktestResult:
        """Berechnet Performance-Metriken"""
        history_df = pd.DataFrame(self.portfolio_history)
        history_df.set_index('timestamp', inplace=True)

        final_value = history_df['total_value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital

        # Annualisierte Rendite
        days = (history_df.index[-1] - history_df.index[0]).days
        annualized_return = (1 + total_return) ** (365 / max(days, 1)) - 1

        # Sharpe Ratio (vereinfacht, tägliche Returns)
        daily_returns = history_df['total_value'].pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 1 else 0

        # Max Drawdown
        cummax = history_df['total_value'].cummax()
        drawdown = (history_df['total_value'] - cummax) / cummax
        max_drawdown = drawdown.min()

        # Trade-Statistiken
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]

        return BacktestResult(
            initial_value=self.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            total_trades=len(self.trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / max(len(self.trades), 1),
            avg_win=np.mean([t.pnl for t in winning]) if winning else 0,
            avg_loss=np.mean([t.pnl for t in losing]) if losing else 0,
            trades=self.trades,
            portfolio_history=history_df
        )


def print_backtest_report(result: BacktestResult):
    """Druckt einen schönen Backtest-Report"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTEST REPORT                           ║
╠══════════════════════════════════════════════════════════════╣
║  PERFORMANCE                                                 ║
║  ─────────────────────────────────────────────────────────── ║
║  Initial Capital:     ${result.initial_value:>10.2f}                       ║
║  Final Value:         ${result.final_value:>10.2f}                       ║
║  Total Return:        {result.total_return*100:>10.2f}%                      ║
║  Annualized Return:   {result.annualized_return*100:>10.2f}%                      ║
║  Sharpe Ratio:        {result.sharpe_ratio:>10.2f}                        ║
║  Max Drawdown:        {result.max_drawdown*100:>10.2f}%                      ║
╠══════════════════════════════════════════════════════════════╣
║  TRADES                                                      ║
║  ─────────────────────────────────────────────────────────── ║
║  Total Trades:        {result.total_trades:>10}                        ║
║  Win Rate:            {result.win_rate*100:>10.1f}%                      ║
║  Avg Win:             ${result.avg_win:>10.2f}                       ║
║  Avg Loss:            ${result.avg_loss:>10.2f}                       ║
╚══════════════════════════════════════════════════════════════╝
""")

    if result.trades:
        print("\nLETZTE 10 TRADES MIT BEGRÜNDUNG:")
        print("─" * 70)
        for trade in result.trades[-10:]:
            print(f"  {trade.timestamp.strftime('%Y-%m-%d')} | "
                  f"{trade.trade_type.value:4} | "
                  f"{trade.symbol:6} | "
                  f"${trade.value:>8.2f}")
            print(f"    → {trade.reasoning}")
        print("─" * 70)
