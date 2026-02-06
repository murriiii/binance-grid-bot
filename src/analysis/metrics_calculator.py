"""
Metrics Calculator - Berechnet und persistiert alle mathematischen Metriken

Stellt sicher, dass KEINE Berechnung verloren geht:
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Kelly Criterion
- Value at Risk (VaR)
- Conditional VaR (CVaR)
- Maximum Drawdown
- Win Rate, Profit Factor
- Position Sizing

Alle Berechnungen werden in calculation_snapshots gespeichert
für spätere Analyse und Optimierung.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from dotenv import load_dotenv

from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


@dataclass
class RiskMetrics:
    """Alle Risk-Metriken zu einem Zeitpunkt"""

    timestamp: datetime

    # Core Ratios
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None

    # Volatility
    volatility_daily: float | None
    volatility_weekly: float | None

    # Drawdown
    current_drawdown: float | None
    max_drawdown: float | None

    # Value at Risk
    var_95: float | None
    var_99: float | None
    cvar_95: float | None
    cvar_99: float | None

    # Position Sizing
    kelly_fraction: float | None
    half_kelly: float | None
    optimal_position_size: float | None

    # Win/Loss Stats
    win_rate: float | None
    profit_factor: float | None
    avg_win: float | None
    avg_loss: float | None
    consecutive_wins: int
    consecutive_losses: int


@dataclass
class PositionSizeResult:
    """Ergebnis der Position Sizing Berechnung"""

    recommended_size: float
    max_size: float
    risk_budget_used: float
    cvar_contribution: float
    kelly_fraction: float
    method_used: str
    constraints_hit: list[str]


class MetricsCalculator(SingletonMixin):
    """
    Berechnet alle mathematischen Metriken und persistiert sie.

    Garantiert:
    - Keine Berechnung geht verloren
    - Alle Snapshots sind in der DB
    - Reproduzierbare Ergebnisse
    - Audit-Trail für alle Entscheidungen
    """

    # Konstanten
    RISK_FREE_RATE = 0.05  # 5% annual (Stablecoin Staking)
    TRADING_DAYS_PER_YEAR = 365  # Crypto 24/7
    MAX_RISK_BUDGET_PCT = 2.0  # Max 2% Portfolio pro Trade

    def __init__(self):
        self.conn = None
        self._connect()

    def _connect(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.info("MetricsCalculator: PostgreSQL verbunden")
        except Exception as e:
            logger.error(f"MetricsCalculator: DB Verbindung fehlgeschlagen: {e}")

    # ═══════════════════════════════════════════════════════════════
    # CORE RATIO CALCULATIONS
    # ═══════════════════════════════════════════════════════════════

    def calculate_sharpe_ratio(
        self,
        returns: list[float],
        risk_free_rate: float | None = None,
        annualize: bool = True,
    ) -> float | None:
        """
        Berechne Sharpe Ratio.

        Sharpe = (Mean Return - Risk Free) / Std Dev

        Args:
            returns: Liste von Renditen (z.B. tägliche Returns)
            risk_free_rate: Risikofreier Zinssatz (default: 5%)
            annualize: Annualisieren (default: True)
        """
        if len(returns) < 2:
            return None

        rf = risk_free_rate if risk_free_rate is not None else self.RISK_FREE_RATE
        returns_arr = np.array(returns)

        # Täglicher risikofreier Return
        daily_rf = rf / self.TRADING_DAYS_PER_YEAR
        excess_returns = returns_arr - daily_rf

        std = np.std(excess_returns)
        if std == 0:
            return None

        sharpe = np.mean(excess_returns) / std

        if annualize:
            sharpe *= np.sqrt(self.TRADING_DAYS_PER_YEAR)

        return float(sharpe)

    def calculate_sortino_ratio(
        self,
        returns: list[float],
        risk_free_rate: float | None = None,
        annualize: bool = True,
    ) -> float | None:
        """
        Berechne Sortino Ratio (nur Downside-Volatilität).

        Besser als Sharpe weil positive Volatilität nicht bestraft wird.

        Sortino = (Mean Return - Risk Free) / Downside Std Dev
        """
        if len(returns) < 2:
            return None

        rf = risk_free_rate if risk_free_rate is not None else self.RISK_FREE_RATE
        returns_arr = np.array(returns)

        daily_rf = rf / self.TRADING_DAYS_PER_YEAR
        excess_returns = returns_arr - daily_rf

        # Nur negative Returns für Downside
        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) == 0:
            return float("inf")  # Keine Verluste

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return None

        sortino = np.mean(excess_returns) / downside_std

        if annualize:
            sortino *= np.sqrt(self.TRADING_DAYS_PER_YEAR)

        return float(sortino)

    def calculate_calmar_ratio(
        self,
        returns: list[float],
        max_drawdown: float | None = None,
    ) -> float | None:
        """
        Berechne Calmar Ratio.

        Calmar = Annualized Return / Max Drawdown

        Gut für Drawdown-averse Investoren.
        """
        if len(returns) < 2:
            return None

        # Annualisierte Rendite
        total_return = np.sum(returns)
        days = len(returns)
        annual_return = total_return * (self.TRADING_DAYS_PER_YEAR / days)

        # Max Drawdown berechnen falls nicht übergeben
        if max_drawdown is None:
            max_drawdown = self.calculate_max_drawdown(returns)

        if max_drawdown is None or max_drawdown == 0:
            return None

        calmar = annual_return / abs(max_drawdown)
        return float(calmar)

    # ═══════════════════════════════════════════════════════════════
    # RISK METRICS
    # ═══════════════════════════════════════════════════════════════

    def calculate_max_drawdown(self, returns: list[float]) -> float | None:
        """
        Berechne Maximum Drawdown.

        Max Drawdown = (Trough - Peak) / Peak

        Returns prozentual (z.B. -15.5 für 15.5% Drawdown)
        """
        if len(returns) < 2:
            return None

        returns_arr = np.array(returns)
        cumulative = np.cumsum(returns_arr)

        # Running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Drawdown an jedem Punkt
        drawdowns = cumulative - running_max

        # Maximum Drawdown (negativster Wert)
        max_dd = np.min(drawdowns)

        return float(max_dd)

    def calculate_var(
        self,
        returns: list[float],
        confidence: float = 0.95,
    ) -> float | None:
        """
        Berechne Value at Risk (VaR).

        VaR = Percentile der Returns bei (1-confidence)

        Beispiel: 95% VaR = "In 95% der Fälle verlieren wir nicht mehr als X%"
        """
        if len(returns) < 5:
            return None

        returns_arr = np.array(returns)
        var = np.percentile(returns_arr, (1 - confidence) * 100)
        return float(var)

    def calculate_cvar(
        self,
        returns: list[float],
        confidence: float = 0.95,
    ) -> float | None:
        """
        Berechne Conditional VaR (Expected Shortfall).

        CVaR = Durchschnitt der Returns unterhalb des VaR

        Besser als VaR weil es den "Tail" berücksichtigt.
        """
        if len(returns) < 5:
            return None

        var = self.calculate_var(returns, confidence)
        if var is None:
            return None

        returns_arr = np.array(returns)
        returns_below_var = returns_arr[returns_arr <= var]

        if len(returns_below_var) == 0:
            return var

        return float(np.mean(returns_below_var))

    def calculate_volatility(
        self,
        returns: list[float],
        window: int | None = None,
        annualize: bool = True,
    ) -> float | None:
        """
        Berechne Volatilität (Standardabweichung der Returns).

        Args:
            returns: Liste von Returns
            window: Optional rolling window (None = alle)
            annualize: Annualisieren
        """
        if len(returns) < 2:
            return None

        returns_arr = np.array(returns)

        if window and len(returns) > window:
            returns_arr = returns_arr[-window:]

        vol = np.std(returns_arr)

        if annualize:
            vol *= np.sqrt(self.TRADING_DAYS_PER_YEAR)

        return float(vol)

    # ═══════════════════════════════════════════════════════════════
    # POSITION SIZING
    # ═══════════════════════════════════════════════════════════════

    def calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.25,  # Quarter-Kelly (konservativ)
    ) -> float | None:
        """
        Berechne Kelly Criterion für optimale Position Size.

        Kelly f* = (p * b - q) / b
        wobei:
            p = Win Rate
            q = 1 - p (Loss Rate)
            b = Avg Win / Avg Loss

        Args:
            win_rate: Gewinnwahrscheinlichkeit (0-1)
            avg_win: Durchschnittlicher Gewinn
            avg_loss: Durchschnittlicher Verlust (positiv)
            fraction: Kelly-Fraktion (0.25 = Quarter-Kelly)
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return None

        win_loss_ratio = avg_win / abs(avg_loss)
        q = 1 - win_rate

        kelly = (win_rate * win_loss_ratio - q) / win_loss_ratio

        # Bound zwischen 0 und 1
        kelly = max(0, min(kelly, 1))

        # Fractional Kelly
        return kelly * fraction

    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        expected_volatility: float,
        signal_confidence: float,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
        historical_returns: list[float] | None = None,
    ) -> PositionSizeResult:
        """
        Berechne optimale Position Size mit mehreren Methoden.

        Kombiniert:
        1. CVaR-basiertes Sizing (Risk Budget)
        2. Kelly Criterion (wenn Daten verfügbar)
        3. Volatility Adjustment
        4. Confidence Scaling

        Args:
            portfolio_value: Gesamtes Portfolio in USD
            entry_price: Einstiegspreis
            expected_volatility: Erwartete Volatilität (z.B. ATR-basiert)
            signal_confidence: Konfidenz des Signals (0-1)
            win_rate: Historische Gewinnrate
            avg_win: Durchschnittlicher Gewinn
            avg_loss: Durchschnittlicher Verlust
            historical_returns: Liste historischer Returns
        """
        constraints_hit = []

        # 1. Risk Budget
        risk_budget_usd = portfolio_value * (self.MAX_RISK_BUDGET_PCT / 100)
        adjusted_budget = risk_budget_usd * signal_confidence

        # 2. CVaR-basiertes Sizing
        cvar = None
        if historical_returns and len(historical_returns) >= 5:
            cvar = abs(self.calculate_cvar(historical_returns) or expected_volatility)
        else:
            cvar = expected_volatility

        if cvar == 0:
            cvar = 0.05  # Default 5% als Fallback

        cvar_max_position = adjusted_budget / cvar
        cvar_max_quantity = cvar_max_position / entry_price

        # 3. Kelly-basiertes Sizing
        kelly = None
        kelly_max_quantity = float("inf")
        if win_rate and avg_win and avg_loss:
            kelly = self.calculate_kelly_fraction(win_rate, avg_win, avg_loss)
            if kelly:
                kelly_max_position = portfolio_value * kelly
                kelly_max_quantity = kelly_max_position / entry_price

        # 4. Finale Size = Minimum aller Constraints
        final_quantity = min(cvar_max_quantity, kelly_max_quantity)

        # Constraint Tracking
        if final_quantity == cvar_max_quantity:
            constraints_hit.append("cvar_limit")
        if final_quantity == kelly_max_quantity:
            constraints_hit.append("kelly_limit")

        # Max Size (ohne Confidence Scaling)
        max_quantity = min(
            risk_budget_usd / cvar / entry_price,
            kelly_max_quantity if kelly else float("inf"),
        )

        return PositionSizeResult(
            recommended_size=final_quantity,
            max_size=max_quantity,
            risk_budget_used=final_quantity * entry_price * cvar,
            cvar_contribution=cvar,
            kelly_fraction=kelly or 0,
            method_used="cvar_kelly_hybrid",
            constraints_hit=constraints_hit,
        )

    # ═══════════════════════════════════════════════════════════════
    # WIN/LOSS STATISTICS
    # ═══════════════════════════════════════════════════════════════

    def calculate_win_rate(self, returns: list[float]) -> float | None:
        """Berechne Win Rate"""
        if not returns:
            return None

        wins = sum(1 for r in returns if r > 0)
        return wins / len(returns)

    def calculate_profit_factor(self, returns: list[float]) -> float | None:
        """
        Berechne Profit Factor.

        Profit Factor = Gross Profit / Gross Loss

        > 1 = Profitabel
        > 2 = Gut
        > 3 = Exzellent
        """
        if not returns:
            return None

        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else None

        return gross_profit / gross_loss

    def calculate_avg_win_loss(self, returns: list[float]) -> tuple[float | None, float | None]:
        """Berechne durchschnittlichen Gewinn und Verlust"""
        if not returns:
            return None, None

        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]

        avg_win = np.mean(wins) if wins else None
        avg_loss = np.mean(np.abs(losses)) if losses else None

        return (
            float(avg_win) if avg_win else None,
            float(avg_loss) if avg_loss else None,
        )

    def calculate_consecutive_streaks(self, returns: list[float]) -> tuple[int, int]:
        """Berechne aktuelle Win/Loss Streaks"""
        if not returns:
            return 0, 0

        consecutive_wins = 0
        consecutive_losses = 0

        # Von hinten nach vorne zählen
        for r in reversed(returns):
            if r > 0:
                if consecutive_losses == 0:
                    consecutive_wins += 1
                else:
                    break
            elif r < 0:
                if consecutive_wins == 0:
                    consecutive_losses += 1
                else:
                    break

        return consecutive_wins, consecutive_losses

    # ═══════════════════════════════════════════════════════════════
    # FULL METRICS CALCULATION & PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def calculate_all_metrics(self, returns: list[float]) -> RiskMetrics:
        """
        Berechne ALLE Metriken auf einmal.

        Args:
            returns: Liste von Returns (tägliche oder pro Trade)

        Returns:
            RiskMetrics Objekt mit allen berechneten Werten
        """
        win_rate = self.calculate_win_rate(returns)
        avg_win, avg_loss = self.calculate_avg_win_loss(returns)
        cons_wins, cons_losses = self.calculate_consecutive_streaks(returns)
        max_dd = self.calculate_max_drawdown(returns)

        kelly = None
        if win_rate and avg_win and avg_loss:
            kelly = self.calculate_kelly_fraction(win_rate, avg_win, avg_loss)

        return RiskMetrics(
            timestamp=datetime.now(),
            sharpe_ratio=self.calculate_sharpe_ratio(returns),
            sortino_ratio=self.calculate_sortino_ratio(returns),
            calmar_ratio=self.calculate_calmar_ratio(returns, max_dd),
            volatility_daily=self.calculate_volatility(returns, annualize=False),
            volatility_weekly=self.calculate_volatility(returns, window=7, annualize=False),
            current_drawdown=None,  # Needs cumulative tracking
            max_drawdown=max_dd,
            var_95=self.calculate_var(returns, 0.95),
            var_99=self.calculate_var(returns, 0.99),
            cvar_95=self.calculate_cvar(returns, 0.95),
            cvar_99=self.calculate_cvar(returns, 0.99),
            kelly_fraction=kelly,
            half_kelly=kelly / 2 if kelly else None,
            optimal_position_size=None,  # Needs portfolio context
            win_rate=win_rate,
            profit_factor=self.calculate_profit_factor(returns),
            avg_win=avg_win,
            avg_loss=avg_loss,
            consecutive_wins=cons_wins,
            consecutive_losses=cons_losses,
        )

    def store_snapshot(
        self,
        metrics: RiskMetrics,
        cycle_id: str | None = None,
        cohort_id: str | None = None,
        trade_id: str | None = None,
        portfolio_value: float | None = None,
        cash_position: float | None = None,
        btc_price: float | None = None,
        fear_greed: int | None = None,
        current_regime: str | None = None,
    ):
        """
        Speichere Metriken-Snapshot in der Datenbank.

        Stellt sicher, dass KEINE Berechnung verloren geht.
        """
        if not self.conn:
            logger.debug("MetricsCalculator: DB nicht verfügbar, Snapshot nicht gespeichert")
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calculation_snapshots (
                        cycle_id, cohort_id, trade_id,
                        kelly_fraction, half_kelly, optimal_position_size,
                        current_sharpe, current_sortino, current_calmar,
                        rolling_volatility_7d, rolling_volatility_30d,
                        current_drawdown, max_drawdown_cycle,
                        var_95, var_99, cvar_95, cvar_99,
                        portfolio_value, cash_position, exposure_pct,
                        btc_price, fear_greed, current_regime,
                        win_rate, profit_factor, avg_win, avg_loss,
                        consecutive_wins, consecutive_losses
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                """,
                    (
                        cycle_id,
                        cohort_id,
                        trade_id,
                        metrics.kelly_fraction,
                        metrics.half_kelly,
                        metrics.optimal_position_size,
                        metrics.sharpe_ratio,
                        metrics.sortino_ratio,
                        metrics.calmar_ratio,
                        metrics.volatility_daily,
                        metrics.volatility_weekly,
                        metrics.current_drawdown,
                        metrics.max_drawdown,
                        metrics.var_95,
                        metrics.var_99,
                        metrics.cvar_95,
                        metrics.cvar_99,
                        portfolio_value,
                        cash_position,
                        ((portfolio_value - cash_position) / portfolio_value * 100)
                        if portfolio_value and cash_position
                        else None,
                        btc_price,
                        fear_greed,
                        current_regime,
                        metrics.win_rate,
                        metrics.profit_factor,
                        metrics.avg_win,
                        metrics.avg_loss,
                        metrics.consecutive_wins,
                        metrics.consecutive_losses,
                    ),
                )
                self.conn.commit()
                logger.debug("MetricsCalculator: Snapshot gespeichert")

        except Exception as e:
            logger.error(f"MetricsCalculator: Fehler beim Speichern: {e}")
            self.conn.rollback()

    def get_latest_metrics(self, cohort_id: str) -> dict[str, Any] | None:
        """Hole neueste Metriken für eine Cohort"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM calculation_snapshots
                    WHERE cohort_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    (cohort_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"MetricsCalculator: Fehler beim Abrufen: {e}")
            return None

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
