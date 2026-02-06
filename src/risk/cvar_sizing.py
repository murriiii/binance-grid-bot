"""
CVaR-basiertes Position Sizing

Conditional Value at Risk (CVaR, auch Expected Shortfall):
- Misst den erwarteten Verlust in den schlimmsten X% der Fälle
- Besser als VaR, da es den "Tail Risk" berücksichtigt
- Kohärentes Risikomaß (subadditiv, monoton, homogen)

Formel: CVaR_alpha = E[X | X <= VaR_alpha]
- Bei alpha = 0.95: Durchschnittlicher Verlust in den schlechtesten 5%

Position Sizing basiert auf:
1. Maximum Verlust pro Trade = Risk Budget * Portfolio Value
2. Position Size = Max Loss / CVaR
3. Anpassung nach Signal-Confidence
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from dotenv import load_dotenv

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
    """Berechnete Risiko-Metriken"""

    var_95: float  # Value at Risk (95%)
    var_99: float  # Value at Risk (99%)
    cvar_95: float  # Conditional VaR (95%)
    cvar_99: float  # Conditional VaR (99%)
    max_loss_observed: float
    volatility: float  # Annualisierte Volatilität
    downside_volatility: float  # Nur negative Returns


@dataclass
class PositionSizeResult:
    """Ergebnis der Position Sizing Berechnung"""

    recommended_size: float  # In Basiswährung (USDT)
    max_position: float  # Absolute Obergrenze
    risk_adjusted_size: float  # Nach Confidence angepasst
    kelly_size: float  # Kelly Criterion Empfehlung

    # Begründung
    sizing_method: str
    risk_budget_used: float
    confidence_multiplier: float

    # Limits
    hit_max_position: bool
    hit_min_position: bool

    # Metriken
    expected_max_loss: float
    cvar_used: float


# Konfiguration
DEFAULT_RISK_BUDGET = 0.02  # 2% des Portfolios pro Trade
MAX_POSITION_PCT = 0.25  # Max 25% des Portfolios in einer Position
MIN_POSITION_PCT = 0.01  # Min 1% für sinnvolle Trades
CONFIDENCE_LEVEL = 0.95  # 95% CVaR
LOOKBACK_DAYS = 30  # Tage für historische Berechnung


class CVaRPositionSizer:
    """
    Position Sizing basierend auf Conditional Value at Risk.

    Features:
    1. CVaR-basierte Positionsgrößen
    2. Risk Budget Management
    3. Confidence-adjusted Sizing
    4. Kelly Criterion Integration
    5. Regime-aware Adjustments
    """

    _instance = None

    def __init__(self):
        self.conn = None
        self._connect_db()

        # Cache für historische Daten
        self._returns_cache: dict[str, tuple[datetime, np.ndarray]] = {}

    @classmethod
    def get_instance(cls) -> "CVaRPositionSizer":
        """Singleton Pattern"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset für Tests"""
        cls._instance = None

    def _connect_db(self):
        """Verbinde mit PostgreSQL"""
        if not POSTGRES_AVAILABLE:
            return

        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.conn = psycopg2.connect(database_url)
                logger.debug("CVaRPositionSizer: DB verbunden")
        except Exception as e:
            logger.error(f"CVaRPositionSizer: DB Fehler: {e}")

    # ═══════════════════════════════════════════════════════════════
    # RISK METRICS CALCULATION
    # ═══════════════════════════════════════════════════════════════

    def calculate_risk_metrics(
        self,
        returns: np.ndarray,
        confidence_level: float = CONFIDENCE_LEVEL,
    ) -> RiskMetrics:
        """
        Berechne alle Risiko-Metriken.

        Args:
            returns: Array von Returns (nicht Preisen!)
            confidence_level: Konfidenz-Level (default 0.95)

        Returns:
            RiskMetrics Objekt
        """
        if len(returns) < 10:
            # Fallback bei zu wenig Daten
            return RiskMetrics(
                var_95=0.05,
                var_99=0.10,
                cvar_95=0.07,
                cvar_99=0.12,
                max_loss_observed=0.10,
                volatility=0.30,
                downside_volatility=0.20,
            )

        # VaR: Percentile der Verluste
        var_95 = -np.percentile(returns, 5)  # Negativ da wir Verlust wollen
        var_99 = -np.percentile(returns, 1)

        # CVaR: Durchschnitt der Verluste jenseits VaR
        cvar_95 = -np.mean(returns[returns <= np.percentile(returns, 5)])
        cvar_99 = -np.mean(returns[returns <= np.percentile(returns, 1)])

        # Maximum beobachteter Verlust
        max_loss = -np.min(returns)

        # Volatilität (annualisiert für Crypto - 365 Tage)
        volatility = np.std(returns) * np.sqrt(365)

        # Downside Volatility (nur negative Returns)
        negative_returns = returns[returns < 0]
        downside_volatility = (
            np.std(negative_returns) * np.sqrt(365) if len(negative_returns) > 0 else volatility
        )

        return RiskMetrics(
            var_95=max(0.001, var_95),  # Minimum 0.1%
            var_99=max(0.001, var_99),
            cvar_95=max(0.001, cvar_95),
            cvar_99=max(0.001, cvar_99),
            max_loss_observed=max(0.001, max_loss),
            volatility=volatility,
            downside_volatility=downside_volatility,
        )

    def calculate_var(self, returns: np.ndarray, confidence: float = 0.95) -> float:
        """Berechne Value at Risk"""
        percentile = (1 - confidence) * 100
        return -np.percentile(returns, percentile)

    def calculate_cvar(self, returns: np.ndarray, confidence: float = 0.95) -> float:
        """
        Berechne Conditional Value at Risk (Expected Shortfall).

        CVaR = E[Loss | Loss > VaR]
        """
        var = self.calculate_var(returns, confidence)
        tail_losses = returns[returns <= -var]

        if len(tail_losses) == 0:
            return var

        return -np.mean(tail_losses)

    # ═══════════════════════════════════════════════════════════════
    # POSITION SIZING
    # ═══════════════════════════════════════════════════════════════

    def calculate_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        signal_confidence: float = 0.5,
        risk_budget: float = DEFAULT_RISK_BUDGET,
        regime: str | None = None,
        use_kelly: bool = True,
    ) -> PositionSizeResult:
        """
        Berechne optimale Positionsgröße.

        Args:
            symbol: Trading-Paar
            portfolio_value: Aktueller Portfolio-Wert in USDT
            signal_confidence: Konfidenz des Trading-Signals (0-1)
            risk_budget: Max % des Portfolios zu riskieren
            regime: Optionales Markt-Regime
            use_kelly: Kelly Criterion einbeziehen

        Returns:
            PositionSizeResult mit empfohlener Größe
        """
        # 1. Hole historische Returns
        returns = self._get_historical_returns(symbol)

        # 2. Berechne Risiko-Metriken
        metrics = self.calculate_risk_metrics(returns)

        # 3. Regime-Anpassung
        adjusted_cvar = self._adjust_cvar_for_regime(metrics.cvar_95, regime)

        # 4. Basis Position Sizing: Risk Budget / CVaR
        max_loss_allowed = portfolio_value * risk_budget
        base_position = max_loss_allowed / adjusted_cvar if adjusted_cvar > 0 else 0

        # 5. Kelly Criterion (optional)
        kelly_size = 0.0
        if use_kelly:
            kelly_size = self._calculate_kelly_position(returns, portfolio_value, signal_confidence)

        # 6. Confidence Adjustment
        # Höhere Confidence = größere Position
        confidence_multiplier = 0.5 + signal_confidence * 0.5  # 0.5 bis 1.0
        confidence_adjusted = base_position * confidence_multiplier

        # 7. Kombiniere mit Kelly (wenn aktiviert)
        if use_kelly and kelly_size > 0:
            # Nehme das Minimum von CVaR und Kelly (konservativ)
            recommended = min(confidence_adjusted, kelly_size)
        else:
            recommended = confidence_adjusted

        # 8. Apply Limits
        max_position = portfolio_value * MAX_POSITION_PCT
        min_position = portfolio_value * MIN_POSITION_PCT

        hit_max = recommended > max_position
        hit_min = recommended < min_position

        final_size = max(min_position, min(max_position, recommended))

        # 9. Erwarteter maximaler Verlust
        expected_max_loss = final_size * adjusted_cvar

        return PositionSizeResult(
            recommended_size=final_size,
            max_position=max_position,
            risk_adjusted_size=confidence_adjusted,
            kelly_size=kelly_size,
            sizing_method="CVaR-based with Kelly",
            risk_budget_used=risk_budget,
            confidence_multiplier=confidence_multiplier,
            hit_max_position=hit_max,
            hit_min_position=hit_min,
            expected_max_loss=expected_max_loss,
            cvar_used=adjusted_cvar,
        )

    def _adjust_cvar_for_regime(self, cvar: float, regime: str | None) -> float:
        """Passe CVaR basierend auf Markt-Regime an"""
        if regime is None:
            return cvar

        # In bearischen Regimes: Erhöhe CVaR (konservativer)
        # In bullischen Regimes: Leicht reduzieren
        regime_multipliers = {
            "BULL": 0.9,  # Etwas weniger konservativ
            "BEAR": 1.5,  # Deutlich konservativer
            "SIDEWAYS": 1.1,  # Leicht konservativer
            "TRANSITION": 1.3,  # Mehr Unsicherheit
        }

        multiplier = regime_multipliers.get(regime.upper(), 1.0)
        return cvar * multiplier

    def _calculate_kelly_position(
        self,
        returns: np.ndarray,
        portfolio_value: float,
        signal_confidence: float,
    ) -> float:
        """
        Berechne Kelly Criterion Position.

        Kelly Fraction: f* = (p * b - q) / b
        - p = Win-Wahrscheinlichkeit
        - q = Loss-Wahrscheinlichkeit (1 - p)
        - b = Win/Loss Ratio
        """
        if len(returns) < 20:
            return 0.0

        # Win Rate
        wins = returns[returns > 0]
        losses = returns[returns < 0]

        if len(wins) == 0 or len(losses) == 0:
            return 0.0

        # Use base win rate directly - confidence adjustment happens in calculate_position_size()
        base_win_rate = len(wins) / len(returns)
        adjusted_win_rate = base_win_rate

        p = adjusted_win_rate
        q = 1 - p

        # Win/Loss Ratio
        avg_win = np.mean(wins)
        avg_loss = abs(np.mean(losses))

        if avg_loss == 0:
            return 0.0

        b = avg_win / avg_loss

        # Kelly Fraction
        kelly_fraction = (p * b - q) / b

        # Half-Kelly (konservativer)
        half_kelly = kelly_fraction / 2

        # Limit auf sinnvollen Bereich
        half_kelly = max(0, min(0.25, half_kelly))

        return portfolio_value * half_kelly

    # ═══════════════════════════════════════════════════════════════
    # HISTORICAL DATA
    # ═══════════════════════════════════════════════════════════════

    def _get_historical_returns(
        self, symbol: str, lookback_days: int = LOOKBACK_DAYS
    ) -> np.ndarray:
        """Hole historische Returns für ein Symbol"""

        # Check Cache
        if symbol in self._returns_cache:
            cache_time, cached_returns = self._returns_cache[symbol]
            if datetime.now() - cache_time < timedelta(hours=1):
                return cached_returns

        # Versuche aus DB
        returns = self._fetch_returns_from_db(symbol, lookback_days)

        if len(returns) < 10:
            # Fallback: Fetch von API
            returns = self._fetch_returns_from_api(symbol, lookback_days)

        if len(returns) < 10:
            # Fallback: Generiere synthetische Daten basierend auf typischer Volatilität
            returns = self._generate_fallback_returns(symbol)

        # Cache
        self._returns_cache[symbol] = (datetime.now(), returns)

        return returns

    def _fetch_returns_from_db(self, symbol: str, lookback_days: int) -> np.ndarray:
        """Hole Returns aus historischen Trades"""
        if not self.conn:
            return np.array([])

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT pnl_pct FROM trade_pairs
                    WHERE symbol = %s
                    AND status = 'closed'
                    AND created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at
                """,
                    (symbol, lookback_days),
                )

                rows = cur.fetchall()
                if rows:
                    return np.array([float(row["pnl_pct"]) / 100 for row in rows])

        except Exception as e:
            logger.debug(f"Returns fetch error: {e}")

        return np.array([])

    def _fetch_returns_from_api(self, symbol: str, lookback_days: int) -> np.ndarray:
        """Hole Returns von Binance API"""
        try:
            from src.api.http_client import get_http_client

            http = get_http_client()
            if not http:
                return np.array([])

            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": "1d",
                "limit": lookback_days,
            }

            response = http.get(url, params=params, timeout=10)

            if response:
                closes = np.array([float(candle[4]) for candle in response])
                returns = np.diff(closes) / closes[:-1]
                return returns

        except Exception as e:
            logger.debug(f"API Returns fetch error: {e}")

        return np.array([])

    def _generate_fallback_returns(self, symbol: str) -> np.ndarray:
        """Generiere Fallback-Returns basierend auf typischer Crypto-Volatilität"""
        # Typische tägliche Volatilität für verschiedene Assets
        volatility_map = {
            "BTC": 0.03,  # 3% täglich
            "ETH": 0.04,
            "SOL": 0.06,
            "DEFAULT": 0.05,
        }

        # Finde passende Volatilität
        vol = volatility_map.get("DEFAULT", 0.05)
        for key, v in volatility_map.items():
            if key in symbol.upper():
                vol = v
                break

        # Generiere 30 Tage synthetische Returns
        np.random.seed(42)  # Reproduzierbar
        returns = np.random.normal(0.001, vol, 30)  # Leicht positiver Drift

        return returns

    # ═══════════════════════════════════════════════════════════════
    # RISK BUDGET MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def get_available_risk_budget(
        self,
        portfolio_value: float,
        open_positions: list[dict[str, Any]],
        max_total_risk: float = 0.10,  # Max 10% Gesamt-Risiko
    ) -> float:
        """
        Berechne verfügbares Risk Budget.

        Berücksichtigt bereits offene Positionen.
        """
        # Aktuell genutztes Risiko
        current_risk = 0.0

        for pos in open_positions:
            position_value = pos.get("value", 0)
            position_cvar = pos.get("cvar", 0.05)  # Default 5%
            current_risk += (position_value / portfolio_value) * position_cvar

        # Verfügbares Budget
        available = max(0, max_total_risk - current_risk)

        return available

    def adjust_for_correlation(
        self,
        position_size: float,
        new_symbol: str,
        existing_positions: list[dict[str, Any]],
        correlation_threshold: float = 0.7,
    ) -> float:
        """
        Passe Position für Korrelation mit bestehenden Positionen an.

        Hochkorrelierte Assets erhöhen das Risiko.
        """
        if not existing_positions:
            return position_size

        # Vereinfachte Korrelationsmatrix
        # In Produktion: Echte Korrelationsberechnung
        high_correlation_pairs = {
            ("BTC", "ETH"): 0.85,
            ("SOL", "ETH"): 0.75,
            ("ARB", "OP"): 0.80,
            ("AVAX", "SOL"): 0.70,
        }

        # Prüfe Korrelationen
        total_correlation_adjustment = 1.0

        for pos in existing_positions:
            existing_symbol = pos.get("symbol", "")

            # Suche Korrelation
            pair1 = (new_symbol.replace("USDT", ""), existing_symbol.replace("USDT", ""))
            pair2 = (existing_symbol.replace("USDT", ""), new_symbol.replace("USDT", ""))

            correlation = high_correlation_pairs.get(pair1, high_correlation_pairs.get(pair2, 0.3))

            if correlation > correlation_threshold:
                # Reduziere Position proportional zur Korrelation
                reduction = 1 - (correlation - correlation_threshold) / (1 - correlation_threshold)
                total_correlation_adjustment *= reduction

        return position_size * max(0.3, total_correlation_adjustment)

    # ═══════════════════════════════════════════════════════════════
    # POSITION ADJUSTMENT
    # ═══════════════════════════════════════════════════════════════

    def should_reduce_position(
        self,
        current_pnl_pct: float,
        holding_hours: float,
        signal_confidence: float,
    ) -> tuple[bool, float]:
        """
        Prüfe ob Position reduziert werden sollte.

        Returns: (should_reduce, reduction_pct)
        """
        # Trailing Stop Logic
        if current_pnl_pct > 0.05 and current_pnl_pct < 0.03:  # >5% Gewinn aber schrumpft
            return True, 0.5  # 50% verkaufen

        # Time Decay
        if holding_hours > 168 and current_pnl_pct < 0.01:  # >1 Woche, kaum Bewegung
            return True, 1.0  # Alles verkaufen

        # Confidence Drop
        if signal_confidence < 0.3:
            return True, 0.5  # 50% verkaufen

        return False, 0.0

    def calculate_stop_loss_distance(
        self,
        symbol: str,
        risk_metrics: RiskMetrics | None = None,
        multiplier: float = 2.0,
    ) -> float:
        """
        Berechne sinnvolle Stop-Loss Distanz basierend auf CVaR.

        Returns: Stop-Loss als Prozentsatz (z.B. 0.05 für 5%)
        """
        if risk_metrics is None:
            returns = self._get_historical_returns(symbol)
            risk_metrics = self.calculate_risk_metrics(returns)

        # Stop-Loss = CVaR * Multiplier
        # Multiplier > 1 gibt mehr Spielraum
        stop_loss = risk_metrics.cvar_95 * multiplier

        # Grenzen
        min_stop = 0.02  # Minimum 2%
        max_stop = 0.15  # Maximum 15%

        return max(min_stop, min(max_stop, stop_loss))

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def store_sizing_decision(
        self,
        symbol: str,
        result: PositionSizeResult,
        cycle_id: str | None = None,
    ):
        """Speichere Sizing-Entscheidung für Analyse"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO position_sizing_log (
                        symbol, cycle_id, recommended_size, max_position,
                        risk_adjusted_size, kelly_size, sizing_method,
                        risk_budget_used, confidence_multiplier,
                        expected_max_loss, cvar_used
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        cycle_id,
                        result.recommended_size,
                        result.max_position,
                        result.risk_adjusted_size,
                        result.kelly_size,
                        result.sizing_method,
                        result.risk_budget_used,
                        result.confidence_multiplier,
                        result.expected_max_loss,
                        result.cvar_used,
                    ),
                )
                self.conn.commit()

        except Exception as e:
            logger.debug(f"Sizing Log Error (table may not exist): {e}")
            self.conn.rollback()

    def get_sizing_history(self, symbol: str | None = None, days: int = 30) -> list[dict[str, Any]]:
        """Hole Sizing-Historie"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM position_sizing_log
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                """
                params = [days]

                if symbol:
                    query += " AND symbol = %s"
                    params.append(symbol)

                query += " ORDER BY created_at DESC"

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.debug(f"Sizing History Error: {e}")
            return []

    def close(self):
        """Schließe DB-Verbindung"""
        if self.conn:
            self.conn.close()
            self.conn = None
