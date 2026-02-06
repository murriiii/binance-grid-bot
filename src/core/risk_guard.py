"""Risk validation mixin for GridBot."""

import logging

from src.strategies.grid_strategy import TAKER_FEE_RATE

logger = logging.getLogger("trading_bot")


class RiskGuardMixin:
    """Mixin providing risk validation methods for GridBot.

    Expects the host class to have: client, symbol, stop_loss_manager,
    cvar_sizer, allocation_constraints, active_orders, _last_known_price,
    running, telegram, memory, _emergency_stop().
    """

    CIRCUIT_BREAKER_PCT = 10.0  # Emergency stop bei >10% Drop pro Check-Zyklus

    def _validate_order_risk(self, side: str, quantity: float, price: float) -> tuple[bool, str]:
        """
        Validiert eine Order gegen Risk-Checks bevor sie platziert wird.

        Returns:
            (allowed, reason) - False + reason wenn Order abgelehnt
        """
        order_value = quantity * price

        # 1. Portfolio drawdown check
        if self.stop_loss_manager and self.stop_loss_manager.portfolio_stopped:
            return False, "Portfolio drawdown limit reached - all trading halted"

        # 2. CVaR position sizing check
        if self.cvar_sizer and side == "BUY":
            try:
                portfolio_value = self.client.get_account_balance("USDT")
                if portfolio_value > 0:
                    sizing = self.cvar_sizer.calculate_position_size(
                        symbol=self.symbol,
                        portfolio_value=portfolio_value,
                        signal_confidence=0.5,
                    )
                    if order_value > sizing.max_position:
                        return (
                            False,
                            f"Order ${order_value:.2f} exceeds CVaR max position "
                            f"${sizing.max_position:.2f}",
                        )
            except Exception as e:
                logger.warning(f"CVaR check failed (allowing order): {e}")

        # 3. Allocation constraints check
        if self.allocation_constraints and side == "BUY":
            try:
                portfolio_value = self.client.get_account_balance("USDT")
                if portfolio_value > 0:
                    current_invested = sum(
                        float(o["quantity"]) * float(o["price"])
                        for o in self.active_orders.values()
                        if o["type"] == "BUY"
                    )
                    available = self.allocation_constraints.get_available_capital(
                        total_capital=portfolio_value + current_invested,
                        current_invested=current_invested,
                    )
                    if order_value > available:
                        return (
                            False,
                            f"Order ${order_value:.2f} exceeds available capital "
                            f"${available:.2f} (cash reserve enforced)",
                        )
            except Exception as e:
                logger.warning(f"Allocation check failed (allowing order): {e}")

        return True, ""

    def _check_circuit_breaker(self, current_price: float) -> bool:
        """
        Emergency stop bei Flash-Crash (>10% Drop seit letztem Check).

        Returns:
            True wenn Circuit Breaker ausgelöst wurde
        """
        if self._last_known_price <= 0:
            self._last_known_price = current_price
            return False

        if current_price <= 0:
            return False

        drop_pct = (self._last_known_price - current_price) / self._last_known_price * 100

        if drop_pct >= self.CIRCUIT_BREAKER_PCT:
            self._emergency_stop(
                f"Circuit Breaker: {self.symbol} dropped {drop_pct:.1f}% "
                f"({self._last_known_price:.2f} → {current_price:.2f})"
            )
            return True

        self._last_known_price = current_price
        return False

    def _create_stop_loss(self, entry_price: float, quantity: float):
        """Erstellt einen Stop-Loss für eine Position"""
        if not self.stop_loss_manager:
            return

        try:
            from src.risk.stop_loss import StopType

            stop = self.stop_loss_manager.create_stop(
                symbol=self.symbol,
                entry_price=entry_price,
                quantity=quantity,
                stop_type=StopType.TRAILING,
                stop_percentage=5.0,
            )
            logger.info(f"Stop-Loss erstellt: {stop.current_stop_price:.2f} (Trailing 5%)")

        except Exception as e:
            logger.warning(f"Konnte Stop-Loss nicht erstellen: {e}")

    def _check_stop_losses(self, current_price: float):
        """Prüft und aktualisiert Stop-Losses"""
        if not self.stop_loss_manager:
            return

        try:
            from src.risk.stop_loss_executor import execute_stop_loss_sell

            triggered = self.stop_loss_manager.update_all(prices={self.symbol: current_price})

            for stop in triggered:
                logger.warning(f"STOP-LOSS TRIGGERED: {stop.symbol} @ {current_price}")
                self.telegram.send(
                    f"STOP-LOSS TRIGGERED\n"
                    f"Symbol: {stop.symbol}\n"
                    f"Preis: {current_price:.2f}\n"
                    f"Menge: {stop.quantity}",
                )

                result = execute_stop_loss_sell(
                    self.client,
                    stop.symbol,
                    stop.quantity,
                    telegram=self.telegram,
                )
                if result["success"]:
                    stop.confirm_trigger()
                    self.stop_loss_manager.notify_and_persist_trigger(stop)
                    logger.info(f"Stop-Loss sell confirmed: {stop.quantity} {stop.symbol}")
                    fee_usd = current_price * stop.quantity * float(TAKER_FEE_RATE)
                    self._save_trade_to_memory(
                        {"type": "SELL"},
                        current_price,
                        stop.quantity,
                        fee_usd,
                    )
                else:
                    stop.reactivate()
                    logger.critical(f"Stop-Loss sell FAILED, re-activated stop for {stop.symbol}")

        except Exception as e:
            logger.warning(f"Stop-Loss Check Fehler: {e}")
