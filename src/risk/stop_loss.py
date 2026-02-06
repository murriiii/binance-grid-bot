"""
Stop-Loss Management System
Automatischer Schutz vor großen Verlusten

Typen:
1. Fixed Stop-Loss: Verkaufe wenn Preis X% unter Entry fällt
2. Trailing Stop: Folgt dem Preis nach oben, stoppt bei Rücksetzer
3. ATR-basiert: Dynamischer Stop basierend auf Volatilität

Wichtig: Stop-Loss schützt vor katastrophalen Verlusten,
aber kann bei hoher Volatilität zu früh auslösen.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger("trading_bot")


class StopType(Enum):
    FIXED = "fixed"  # Fester Prozentsatz
    TRAILING = "trailing"  # Folgt dem Preis
    ATR = "atr"  # Volatilitätsbasiert
    BREAK_EVEN = "break_even"  # Auf Entry setzen nach X% Gewinn


@dataclass
class StopLossOrder:
    """Eine Stop-Loss Order"""

    id: str
    symbol: str
    entry_price: float
    quantity: float
    stop_type: StopType

    # Stop Konfiguration
    stop_percentage: float = 5.0  # Standard: 5% unter Entry
    trailing_distance: float = 3.0  # Für Trailing: 3% Abstand
    atr_multiplier: float = 2.0  # Für ATR: 2x ATR als Stop

    # Status
    current_stop_price: float = 0.0
    highest_price: float = 0.0  # Für Trailing
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    # Ergebnis
    triggered_at: datetime | None = None
    triggered_price: float | None = None
    result_pnl_pct: float | None = None

    def __post_init__(self):
        if self.current_stop_price == 0:
            self.current_stop_price = self._calculate_initial_stop()
        self.highest_price = self.entry_price

    def _calculate_initial_stop(self) -> float:
        """Berechnet initialen Stop-Preis"""
        if self.stop_type == StopType.FIXED:
            return self.entry_price * (1 - self.stop_percentage / 100)
        elif self.stop_type == StopType.TRAILING:
            return self.entry_price * (1 - self.trailing_distance / 100)
        else:
            return self.entry_price * (1 - self.stop_percentage / 100)

    def update(self, current_price: float, current_atr: float | None = None) -> bool:
        """
        Aktualisiert den Stop basierend auf aktuellem Preis.

        Returns:
            True wenn Stop getriggert wurde
        """
        if not self.is_active:
            return False

        # Trailing Stop: Ziehe Stop nach wenn Preis steigt
        if self.stop_type == StopType.TRAILING:
            if current_price > self.highest_price:
                self.highest_price = current_price
                new_stop = current_price * (1 - self.trailing_distance / 100)
                self.current_stop_price = max(self.current_stop_price, new_stop)

        # ATR Stop: Dynamisch basierend auf Volatilität
        elif self.stop_type == StopType.ATR and current_atr:
            new_stop = current_price - (current_atr * self.atr_multiplier)
            self.current_stop_price = max(self.current_stop_price, new_stop)

        # Break-Even: Nach X% Gewinn auf Entry setzen
        elif self.stop_type == StopType.BREAK_EVEN:
            pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
            if pnl_pct >= self.stop_percentage:  # Z.B. nach 5% Gewinn
                self.current_stop_price = max(
                    self.current_stop_price, self.entry_price
                )  # Break-Even

        # Check ob Stop getriggert — does NOT deactivate, caller must confirm
        if current_price <= self.current_stop_price:
            self.triggered_price = current_price
            self.triggered_at = datetime.now()
            return True

        return False

    def confirm_trigger(self):
        """Call ONLY after successful market sell to deactivate the stop."""
        self.is_active = False
        if self.triggered_price is not None:
            self.result_pnl_pct = (self.triggered_price - self.entry_price) / self.entry_price * 100

    def reactivate(self):
        """Re-enable stop if market sell failed."""
        self.is_active = True
        self.triggered_price = None
        self.triggered_at = None

    def trigger(self, trigger_price: float):
        """Legacy: marks stop as triggered AND deactivated in one step."""
        self.triggered_price = trigger_price
        self.triggered_at = datetime.now()
        self.confirm_trigger()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "current_stop": self.current_stop_price,
            "stop_type": self.stop_type.value,
            "is_active": self.is_active,
            "distance_pct": (self.entry_price - self.current_stop_price) / self.entry_price * 100,
        }


class StopLossManager:
    """
    Verwaltet alle Stop-Loss Orders.

    Features:
    - Automatisches Trailing
    - Benachrichtigung bei Trigger
    - Portfolio-weiter Drawdown-Schutz
    """

    def __init__(self, db_manager=None, telegram_bot=None):
        self.db = db_manager
        self.telegram = telegram_bot
        self.stops: dict[str, StopLossOrder] = {}
        self.lock = threading.Lock()

        # Portfolio Protection
        self.max_daily_drawdown_pct = 10.0  # Stop alles bei -10% am Tag
        self.daily_start_value: float = 0.0
        self.portfolio_stopped = False

        # Lade aktive Stops aus DB
        self._load_from_db()

    def create_stop(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        stop_type: StopType = StopType.TRAILING,
        stop_percentage: float = 5.0,
        trailing_distance: float | None = None,
    ) -> StopLossOrder:
        """Erstellt einen neuen Stop-Loss.

        For TRAILING stops, trailing_distance controls the trailing percentage.
        If not provided, stop_percentage is used as the trailing distance.
        """
        import uuid

        effective_trailing = trailing_distance if trailing_distance is not None else stop_percentage

        stop = StopLossOrder(
            id=str(uuid.uuid4()),
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            stop_type=stop_type,
            stop_percentage=stop_percentage,
            trailing_distance=effective_trailing,
        )

        with self.lock:
            self.stops[stop.id] = stop

        # In DB speichern
        self._save_to_db(stop)

        return stop

    def update_all(
        self, prices: dict[str, float], atrs: dict[str, float] | None = None
    ) -> list[StopLossOrder]:
        """
        Aktualisiert alle Stops mit aktuellen Preisen.

        Returns:
            Liste der getriggerten Stops
        """
        triggered = []

        with self.lock:
            for stop_id, stop in list(self.stops.items()):
                if not stop.is_active:
                    continue

                price = prices.get(stop.symbol)
                if not price:
                    continue

                atr = atrs.get(stop.symbol) if atrs else None

                if stop.update(price, atr):
                    triggered.append(stop)

        return triggered

    def notify_and_persist_trigger(self, stop: StopLossOrder):
        """Call after confirm_trigger() to send notifications and update DB."""
        self._on_stop_triggered(stop)

    def _on_stop_triggered(self, stop: StopLossOrder):
        """Callback wenn ein Stop getriggert wird"""
        # Telegram Benachrichtigung
        if self.telegram:
            emoji = "🛑" if stop.result_pnl_pct < 0 else "✅"
            msg = f"""
{emoji} *STOP-LOSS TRIGGERED*

Symbol: *{stop.symbol}*
Entry: `${stop.entry_price:,.2f}`
Stop: `${stop.triggered_price:,.2f}`
Result: `{stop.result_pnl_pct:+.2f}%`

Type: {stop.stop_type.value}
"""
            self.telegram.send_message(msg)

        # In DB aktualisieren
        self._update_db(stop)

    def check_portfolio_drawdown(self, current_value: float) -> tuple[bool, str]:
        """
        Prüft ob Portfolio-weiter Stop erreicht ist.

        Returns:
            (should_stop_all, reason)
        """
        if self.daily_start_value == 0:
            self.daily_start_value = current_value
            return False, ""

        drawdown = (current_value - self.daily_start_value) / self.daily_start_value * 100

        if drawdown <= -self.max_daily_drawdown_pct:
            self.portfolio_stopped = True
            return (
                True,
                f"Portfolio Drawdown {drawdown:.1f}% erreicht Maximum von {self.max_daily_drawdown_pct}%",
            )

        return False, ""

    def reset_daily(self, start_value: float):
        """Reset für neuen Tag"""
        self.daily_start_value = start_value
        self.portfolio_stopped = False

    def get_active_stops(self) -> list[dict]:
        """Gibt alle aktiven Stops zurück"""
        with self.lock:
            return [s.to_dict() for s in self.stops.values() if s.is_active]

    def cancel_stop(self, stop_id: str) -> bool:
        """Storniert einen Stop"""
        with self.lock:
            if stop_id in self.stops:
                self.stops[stop_id].is_active = False
                return True
        return False

    def _load_from_db(self):
        """Lädt aktive Stops aus der Datenbank beim Start"""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, symbol, entry_price, stop_price, quantity,
                           stop_type, stop_percentage, trailing_distance,
                           highest_price, is_active, created_at
                    FROM stop_loss_orders
                    WHERE is_active = true
                    """
                )
                rows = cur.fetchall()

            for row in rows:
                stop = StopLossOrder(
                    id=row["id"],
                    symbol=row["symbol"],
                    entry_price=float(row["entry_price"]),
                    quantity=float(row["quantity"]),
                    stop_type=StopType(row["stop_type"]),
                    stop_percentage=float(row.get("stop_percentage") or 5.0),
                    trailing_distance=float(row.get("trailing_distance") or 3.0),
                    current_stop_price=float(row["stop_price"]),
                    is_active=True,
                )
                # Restore highest_price for trailing stops
                if row.get("highest_price"):
                    stop.highest_price = float(row["highest_price"])

                with self.lock:
                    self.stops[stop.id] = stop

            if rows:
                logger.info(f"Stop-Loss Manager: {len(rows)} aktive Stops aus DB geladen")

        except Exception as e:
            logger.warning(f"Stop-Loss DB Load fehlgeschlagen: {e}")

    def _save_to_db(self, stop: StopLossOrder):
        """Speichert Stop in Datenbank"""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stop_loss_orders
                    (id, symbol, entry_price, stop_price, quantity, stop_type,
                     stop_percentage, trailing_distance, highest_price, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        stop_price = EXCLUDED.stop_price,
                        highest_price = EXCLUDED.highest_price,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        stop.id,
                        stop.symbol,
                        stop.entry_price,
                        stop.current_stop_price,
                        stop.quantity,
                        stop.stop_type.value,
                        stop.stop_percentage,
                        stop.trailing_distance,
                        stop.highest_price,
                        stop.is_active,
                    ),
                )
        except Exception as e:
            logger.error(f"Stop-Loss DB Save Error: {e}")

    def _update_db(self, stop: StopLossOrder):
        """Aktualisiert Stop in Datenbank"""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    UPDATE stop_loss_orders
                    SET is_active = %s, triggered_at = %s,
                        triggered_price = %s, result_pnl = %s,
                        stop_price = %s, highest_price = %s
                    WHERE id = %s
                    """,
                    (
                        stop.is_active,
                        stop.triggered_at,
                        stop.triggered_price,
                        stop.result_pnl_pct,
                        stop.current_stop_price,
                        stop.highest_price,
                        stop.id,
                    ),
                )
        except Exception as e:
            logger.error(f"Stop-Loss DB Update Error: {e}")


def get_recommended_stop(
    symbol: str, entry_price: float, volatility: str, risk_tolerance: str = "medium"
) -> tuple[StopType, float]:
    """
    Empfiehlt Stop-Loss Konfiguration basierend auf Volatilität und Risiko.

    Args:
        symbol: Trading Symbol
        entry_price: Einstiegspreis
        volatility: "LOW", "MEDIUM", "HIGH"
        risk_tolerance: "low", "medium", "high"

    Returns:
        (stop_type, stop_percentage)
    """
    # Basis Stop-Prozent basierend auf Volatilität
    base_stops = {"LOW": 3.0, "MEDIUM": 5.0, "HIGH": 8.0}

    # Risiko-Multiplikator
    risk_mult = {
        "low": 0.7,  # Engere Stops
        "medium": 1.0,
        "high": 1.3,  # Weitere Stops
    }

    base = base_stops.get(volatility, 5.0)
    mult = risk_mult.get(risk_tolerance, 1.0)
    stop_pct = base * mult

    # Stop-Typ basierend auf Volatilität
    if volatility == "LOW":
        stop_type = StopType.FIXED  # Bei niedriger Vola reicht fixed
    elif volatility == "HIGH":
        stop_type = StopType.ATR  # Bei hoher Vola ATR-basiert
    else:
        stop_type = StopType.TRAILING  # Standard: Trailing

    return stop_type, stop_pct
