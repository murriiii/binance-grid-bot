"""Hybrid Orchestrator for the regime-adaptive trading system.

Manages multi-coin trading across three modes:
- HOLD (BULL): Buy and hold with trailing stops
- GRID (SIDEWAYS): Grid trading via GridBot.tick()
- CASH (BEAR): Exit positions, preserve capital

The orchestrator delegates to ModeManager for mode decisions and
coordinates per-symbol execution based on the active mode.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.api.binance_client import BinanceClient
from src.core.bot import GridBot, TelegramNotifier
from src.core.mode_manager import ModeManager
from src.core.trading_mode import TradingMode
from src.risk.stop_loss import StopLossManager, StopType

if TYPE_CHECKING:
    from src.core.hybrid_config import HybridConfig
    from src.portfolio.allocator import AllocationResult

logger = logging.getLogger("trading_bot")


class SymbolState:
    """Per-symbol tracking state."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.mode: TradingMode = TradingMode.GRID
        self.grid_bot: GridBot | None = None
        self.hold_entry_price: float = 0.0
        self.hold_quantity: float = 0.0
        self.hold_stop_id: str | None = None
        self.allocation_usd: float = 0.0
        self.cash_exit_started: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "mode": self.mode.value,
            "hold_entry_price": self.hold_entry_price,
            "hold_quantity": self.hold_quantity,
            "hold_stop_id": self.hold_stop_id,
            "allocation_usd": self.allocation_usd,
            "cash_exit_started": self.cash_exit_started.isoformat()
            if self.cash_exit_started
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SymbolState:
        state = cls(data["symbol"])
        state.mode = TradingMode(data.get("mode", "GRID"))
        state.hold_entry_price = data.get("hold_entry_price", 0.0)
        state.hold_quantity = data.get("hold_quantity", 0.0)
        state.hold_stop_id = data.get("hold_stop_id")
        state.allocation_usd = data.get("allocation_usd", 0.0)
        if data.get("cash_exit_started"):
            state.cash_exit_started = datetime.fromisoformat(data["cash_exit_started"])
        return state


class HybridOrchestrator:
    """Main orchestrator for the hybrid trading system.

    Coordinates mode evaluation, per-symbol execution, and transitions.
    """

    TICK_INTERVAL_SECONDS = 30
    MAX_CONSECUTIVE_ERRORS = 5
    REBALANCE_INTERVAL_HOURS = 6
    REBALANCE_DRIFT_PCT = 5.0  # Only rebalance if >5% drift

    def __init__(
        self,
        config: HybridConfig,
        client: BinanceClient | None = None,
    ):
        self.config = config
        self.client = client or BinanceClient(testnet=True)
        self.mode_manager = ModeManager(config)
        self.telegram = TelegramNotifier()
        self.stop_loss_manager = StopLossManager()

        self.symbols: dict[str, SymbolState] = {}
        self.running = False
        self.consecutive_errors = 0

        self._last_rebalance: datetime | None = None

        # State persistence
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        self.state_file = config_dir / "hybrid_state.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_symbol(self, symbol: str, allocation_usd: float) -> None:
        """Add a symbol to the orchestrator with its capital allocation."""
        if symbol in self.symbols:
            self.symbols[symbol].allocation_usd = allocation_usd
            return

        state = SymbolState(symbol)
        state.allocation_usd = allocation_usd
        state.mode = self.mode_manager.get_current_mode().current_mode
        self.symbols[symbol] = state
        logger.info(f"Orchestrator: added {symbol} with ${allocation_usd:.2f}")

    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol, canceling any open orders first."""
        state = self.symbols.get(symbol)
        if not state:
            return

        self._cleanup_symbol(state)
        del self.symbols[symbol]
        logger.info(f"Orchestrator: removed {symbol}")

    def tick(self) -> bool:
        """Execute one iteration of the orchestrator loop.

        Returns True to continue, False to stop.
        """
        current_mode = self.mode_manager.get_current_mode().current_mode

        for symbol, state in list(self.symbols.items()):
            try:
                if current_mode == TradingMode.HOLD:
                    self._execute_hold(state)
                elif current_mode == TradingMode.GRID:
                    self._execute_grid(state)
                elif current_mode == TradingMode.CASH:
                    self._execute_cash(state)
            except Exception as e:
                logger.error(f"Orchestrator: error on {symbol}: {e}")

        # Update stop losses with current prices
        self._update_stop_losses()

        self.save_state()
        self.consecutive_errors = 0
        return True

    def evaluate_and_switch(
        self,
        regime: str | None,
        regime_probability: float = 0.0,
        regime_duration_days: int = 0,
    ) -> bool:
        """Evaluate current regime and switch mode if warranted.

        Returns True if a mode switch occurred.
        """
        self.mode_manager.update_regime_info(regime, regime_probability)

        target_mode, reason = self.mode_manager.evaluate_mode(
            regime, regime_probability, regime_duration_days
        )

        current_mode = self.mode_manager.get_current_mode().current_mode
        if target_mode == current_mode:
            return False

        switched = self.mode_manager.request_switch(target_mode, reason)
        if switched:
            self._transition_mode(current_mode, target_mode, reason)
            return True

        return False

    def run(self) -> None:
        """Main loop - runs until stopped."""
        if not self.symbols:
            logger.error("Orchestrator: no symbols configured")
            return

        self.running = True
        self.load_state()

        logger.info(
            f"Orchestrator: starting with {len(self.symbols)} symbols "
            f"in {self.mode_manager.get_current_mode().current_mode.value} mode"
        )
        self.telegram.send(
            f"Hybrid Orchestrator gestartet\n"
            f"Modus: {self.mode_manager.get_current_mode().current_mode.value}\n"
            f"Symbols: {len(self.symbols)}"
        )

        try:
            while self.running:
                try:
                    if not self.tick():
                        break
                    time.sleep(self.TICK_INTERVAL_SECONDS)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.consecutive_errors += 1
                    logger.error(
                        f"Orchestrator: error ({self.consecutive_errors}/"
                        f"{self.MAX_CONSECUTIVE_ERRORS}): {e}"
                    )
                    if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        logger.critical("Orchestrator: too many errors, stopping")
                        self.telegram.send(
                            "Hybrid Orchestrator: Emergency Stop - zu viele Fehler",
                            urgent=True,
                        )
                        break
                    time.sleep(30 * self.consecutive_errors)
        except KeyboardInterrupt:
            logger.info("Orchestrator: stopped (Ctrl+C)")

        self.running = False
        self.save_state()
        self.telegram.send("Hybrid Orchestrator gestoppt")

    def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        self.running = False

    # ------------------------------------------------------------------
    # Mode execution
    # ------------------------------------------------------------------

    def _execute_hold(self, state: SymbolState) -> None:
        """HOLD mode: buy and hold with trailing stop."""
        if state.hold_quantity > 0:
            # Already holding - nothing to do, trailing stop handles exit
            return

        # Need to buy
        price = self.client.get_current_price(state.symbol)
        if not price or price <= 0:
            return

        # Market buy with allocated capital
        result = self.client.place_market_buy(state.symbol, state.allocation_usd)
        if not result["success"]:
            logger.error(f"HOLD buy failed for {state.symbol}: {result.get('error')}")
            return

        # Parse executed quantity from order response
        order = result["order"]
        executed_qty = float(order.get("executedQty", 0))
        avg_price = self._get_avg_fill_price(order)

        if executed_qty <= 0:
            return

        state.hold_entry_price = avg_price
        state.hold_quantity = executed_qty

        # Create wide trailing stop
        stop = self.stop_loss_manager.create_stop(
            symbol=state.symbol,
            entry_price=avg_price,
            quantity=executed_qty,
            stop_type=StopType.TRAILING,
            stop_percentage=self.config.hold_trailing_stop_pct,
        )
        state.hold_stop_id = stop.id

        logger.info(
            f"HOLD: bought {executed_qty} {state.symbol} @ {avg_price:.2f} "
            f"(trailing stop {self.config.hold_trailing_stop_pct}%)"
        )
        self.telegram.send(
            f"HOLD Buy: {state.symbol}\n"
            f"Menge: {executed_qty}\n"
            f"Preis: {avg_price:.2f}\n"
            f"Trailing Stop: {self.config.hold_trailing_stop_pct}%"
        )

    def _execute_grid(self, state: SymbolState) -> None:
        """GRID mode: delegate to GridBot.tick()."""
        if state.grid_bot is None:
            state.grid_bot = self._create_grid_bot(state)
            if state.grid_bot is None:
                return

        state.grid_bot.tick()

    def _execute_cash(self, state: SymbolState) -> None:
        """CASH mode: exit all positions."""
        # Cancel grid bot orders
        if state.grid_bot is not None:
            self._cancel_grid_orders(state)
            state.grid_bot = None

        # Sell hold positions
        if state.hold_quantity > 0:
            if state.cash_exit_started is None:
                # First: tighten trailing stop to 3%
                self._tighten_trailing_stop(state)
                state.cash_exit_started = datetime.now()
                return

            # Check timeout
            elapsed_hours = (datetime.now() - state.cash_exit_started).total_seconds() / 3600

            if elapsed_hours >= self.config.cash_exit_timeout_hours:
                # Timeout: market sell
                self._market_sell_position(state)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def _transition_mode(self, from_mode: TradingMode, to_mode: TradingMode, reason: str) -> None:
        """Handle graceful mode transition for all symbols."""
        logger.info(f"Orchestrator: {from_mode.value} -> {to_mode.value} ({reason})")
        self.telegram.send(
            f"Mode Switch: {from_mode.value} -> {to_mode.value}\nGrund: {reason}",
            urgent=True,
        )

        for state in self.symbols.values():
            self._transition_symbol(state, from_mode, to_mode)
            state.mode = to_mode

    def _transition_symbol(
        self, state: SymbolState, from_mode: TradingMode, to_mode: TradingMode
    ) -> None:
        """Transition a single symbol between modes."""
        if from_mode == TradingMode.GRID and to_mode == TradingMode.HOLD:
            self._transition_grid_to_hold(state)
        elif from_mode == TradingMode.GRID and to_mode == TradingMode.CASH:
            self._transition_grid_to_cash(state)
        elif from_mode == TradingMode.HOLD and to_mode == TradingMode.GRID:
            self._transition_hold_to_grid(state)
        elif from_mode == TradingMode.HOLD and to_mode == TradingMode.CASH:
            self._transition_hold_to_cash(state)
        elif from_mode == TradingMode.CASH and to_mode == TradingMode.GRID:
            self._transition_cash_to_grid(state)
        elif from_mode == TradingMode.CASH and to_mode == TradingMode.HOLD:
            self._transition_cash_to_hold(state)

    def _transition_grid_to_hold(self, state: SymbolState) -> None:
        """GRID -> HOLD: Cancel unfilled grid orders, keep positions with trailing stop."""
        self._cancel_grid_orders(state)

        # If the grid bot had bought positions, treat them as hold positions
        if state.grid_bot is not None:
            buy_value = sum(
                float(o["price"]) * float(o["quantity"])
                for o in state.grid_bot.active_orders.values()
                if o["type"] == "SELL"  # SELL orders represent bought inventory
            )
            if buy_value > 0:
                price = self.client.get_current_price(state.symbol) or 0
                if price > 0:
                    state.hold_entry_price = price
                    state.hold_quantity = buy_value / price
                    stop = self.stop_loss_manager.create_stop(
                        symbol=state.symbol,
                        entry_price=price,
                        quantity=state.hold_quantity,
                        stop_type=StopType.TRAILING,
                        stop_percentage=self.config.hold_trailing_stop_pct,
                    )
                    state.hold_stop_id = stop.id

        state.grid_bot = None

    def _transition_grid_to_cash(self, state: SymbolState) -> None:
        """GRID -> CASH: Cancel grid orders, initiate exit."""
        self._cancel_grid_orders(state)
        state.grid_bot = None
        state.cash_exit_started = None  # Will be set on first _execute_cash

    def _transition_hold_to_grid(self, state: SymbolState) -> None:
        """HOLD -> GRID: Convert hold position to grid bot."""
        # Cancel hold trailing stop
        if state.hold_stop_id:
            self.stop_loss_manager.cancel_stop(state.hold_stop_id)
            state.hold_stop_id = None

        # Grid bot will be created on next _execute_grid
        state.hold_entry_price = 0.0
        state.hold_quantity = 0.0
        state.grid_bot = None

    def _transition_hold_to_cash(self, state: SymbolState) -> None:
        """HOLD -> CASH: Tighten stop, market sell on timeout."""
        if state.hold_quantity > 0:
            self._tighten_trailing_stop(state)
            state.cash_exit_started = datetime.now()

    def _transition_cash_to_grid(self, state: SymbolState) -> None:
        """CASH -> GRID: Reset for fresh grid start."""
        state.cash_exit_started = None
        state.hold_quantity = 0.0
        state.hold_entry_price = 0.0
        state.grid_bot = None  # Will be created on next _execute_grid

    def _transition_cash_to_hold(self, state: SymbolState) -> None:
        """CASH -> HOLD: Reset for fresh buy."""
        state.cash_exit_started = None
        state.hold_quantity = 0.0
        state.hold_entry_price = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_grid_bot(self, state: SymbolState) -> GridBot | None:
        """Create and initialize a GridBot for a symbol."""
        bot_config = {
            "symbol": state.symbol,
            "investment": state.allocation_usd,
            "num_grids": self.config.num_grids,
            "grid_range_percent": self.config.grid_range_percent,
            "testnet": self.client.testnet,
        }
        try:
            bot = GridBot(bot_config, client=self.client)
            if bot.initialize():
                bot.place_initial_orders()
                logger.info(f"GRID: initialized {state.symbol}")
                return bot
            logger.error(f"GRID: init failed for {state.symbol}")
        except Exception as e:
            logger.error(f"GRID: error creating bot for {state.symbol}: {e}")
        return None

    def _cancel_grid_orders(self, state: SymbolState) -> None:
        """Cancel all open grid orders for a symbol."""
        if state.grid_bot is None:
            return

        for order_id in list(state.grid_bot.active_orders.keys()):
            self.client.cancel_order(state.symbol, order_id)
        state.grid_bot.active_orders.clear()

    def _tighten_trailing_stop(self, state: SymbolState) -> None:
        """Tighten trailing stop to 3% for CASH exit."""
        if state.hold_stop_id:
            self.stop_loss_manager.cancel_stop(state.hold_stop_id)

        if state.hold_quantity > 0:
            price = self.client.get_current_price(state.symbol) or state.hold_entry_price
            stop = self.stop_loss_manager.create_stop(
                symbol=state.symbol,
                entry_price=price,
                quantity=state.hold_quantity,
                stop_type=StopType.TRAILING,
                stop_percentage=3.0,
            )
            state.hold_stop_id = stop.id
            logger.info(f"CASH: tightened stop to 3% for {state.symbol}")

    def _market_sell_position(self, state: SymbolState) -> None:
        """Market sell the entire hold position."""
        if state.hold_quantity <= 0:
            return

        result = self.client.place_market_sell(state.symbol, state.hold_quantity)
        if result["success"]:
            logger.info(f"CASH: sold {state.hold_quantity} {state.symbol}")
            self.telegram.send(f"CASH Sell: {state.symbol}\nMenge: {state.hold_quantity}")
        else:
            logger.error(f"CASH: sell failed for {state.symbol}: {result.get('error')}")

        # Cancel stop and reset
        if state.hold_stop_id:
            self.stop_loss_manager.cancel_stop(state.hold_stop_id)
            state.hold_stop_id = None
        state.hold_quantity = 0.0
        state.hold_entry_price = 0.0
        state.cash_exit_started = None

    def _update_stop_losses(self) -> None:
        """Update all stop losses with current prices."""
        prices: dict[str, float] = {}
        for symbol in self.symbols:
            price = self.client.get_current_price(symbol)
            if price and price > 0:
                prices[symbol] = price

        if not prices:
            return

        triggered = self.stop_loss_manager.update_all(prices)
        for stop in triggered:
            state = self.symbols.get(stop.symbol)
            if not state:
                continue

            logger.warning(f"Stop triggered: {stop.symbol} @ {stop.triggered_price}")
            self.telegram.send(
                f"Stop-Loss Triggered: {stop.symbol}\nPreis: {stop.triggered_price:.2f}",
                urgent=True,
            )

            # Execute market sell
            result = self.client.place_market_sell(stop.symbol, stop.quantity)
            if result["success"]:
                logger.info(f"Stop sell executed: {stop.quantity} {stop.symbol}")
            else:
                logger.error(f"Stop sell failed: {result.get('error')}")

            # Reset hold state
            state.hold_quantity = 0.0
            state.hold_entry_price = 0.0
            state.hold_stop_id = None

    def _cleanup_symbol(self, state: SymbolState) -> None:
        """Clean up a symbol before removal."""
        self._cancel_grid_orders(state)
        if state.hold_stop_id:
            self.stop_loss_manager.cancel_stop(state.hold_stop_id)

    def _get_avg_fill_price(self, order: dict) -> float:
        """Extract average fill price from a Binance order response."""
        # cummulativeQuoteQty / executedQty = avg price
        cum_quote = float(order.get("cummulativeQuoteQty", 0))
        exec_qty = float(order.get("executedQty", 0))
        if exec_qty > 0 and cum_quote > 0:
            return cum_quote / exec_qty
        return float(order.get("price", 0))

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """Save orchestrator state to JSON (atomic write)."""
        try:
            mode_state = self.mode_manager.get_current_mode()
            state = {
                "timestamp": datetime.now().isoformat(),
                "current_mode": mode_state.current_mode.value,
                "mode_since": mode_state.mode_since.isoformat(),
                "symbols": {s: st.to_dict() for s, st in self.symbols.items()},
                "config": self.config.to_dict(),
                "last_rebalance": self._last_rebalance.isoformat()
                if self._last_rebalance
                else None,
            }

            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"Orchestrator: save state error: {e}")

    def load_state(self) -> bool:
        """Load orchestrator state from JSON."""
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file) as f:
                data = json.load(f)

            # Restore symbol states
            for symbol, sdata in data.get("symbols", {}).items():
                if symbol in self.symbols:
                    saved = SymbolState.from_dict(sdata)
                    self.symbols[symbol].mode = saved.mode
                    self.symbols[symbol].hold_entry_price = saved.hold_entry_price
                    self.symbols[symbol].hold_quantity = saved.hold_quantity
                    self.symbols[symbol].hold_stop_id = saved.hold_stop_id
                    self.symbols[symbol].cash_exit_started = saved.cash_exit_started

            # Restore rebalance timestamp
            if data.get("last_rebalance"):
                self._last_rebalance = datetime.fromisoformat(data["last_rebalance"])

            logger.info(f"Orchestrator: state loaded ({len(data.get('symbols', {}))} symbols)")
            return True
        except Exception as e:
            logger.error(f"Orchestrator: load state error: {e}")
            return False

    # ------------------------------------------------------------------
    # Multi-coin: scan, allocate, rebalance
    # ------------------------------------------------------------------

    def scan_and_allocate(self, regime: str | None = None) -> AllocationResult | None:
        """Scan for opportunities and allocate capital across symbols.

        Uses CoinScanner for opportunity scoring and PortfolioAllocator
        for capital distribution. Updates the orchestrator's symbol list.

        Returns:
            AllocationResult or None if scanning fails.
        """
        try:
            from src.portfolio.allocator import PortfolioAllocator
            from src.scanner.coin_scanner import CoinScanner
        except ImportError:
            logger.warning("Orchestrator: CoinScanner/Allocator not available")
            return None

        try:
            scanner = CoinScanner.get_instance()
            opportunities = scanner.scan_opportunities(force_refresh=True)

            if not opportunities:
                logger.info("Orchestrator: no opportunities found")
                return None

            # Limit to max_symbols
            opportunities = opportunities[: self.config.max_symbols]

            allocator = PortfolioAllocator.get_instance()
            constraints = self.mode_manager.get_constraints_for_mode()
            allocator.set_constraints(constraints)

            # Build current portfolio for allocator
            current_portfolio = {}
            for symbol, state in self.symbols.items():
                if state.allocation_usd > 0:
                    current_portfolio[symbol] = {"amount": state.allocation_usd}

            result = allocator.calculate_allocation(
                opportunities=opportunities,
                available_capital=self.config.total_investment,
                current_portfolio=current_portfolio,
                regime=regime,
            )

            if not result.allocations:
                logger.info("Orchestrator: allocator returned no allocations")
                return result

            # Apply allocations: add new symbols, update existing
            for symbol, amount in result.allocations.items():
                self.add_symbol(symbol, amount)

            # Remove symbols no longer in allocation
            current_symbols = set(self.symbols.keys())
            allocated_symbols = set(result.allocations.keys())
            for symbol in current_symbols - allocated_symbols:
                # Keep symbols with open positions, just zero their allocation
                state = self.symbols[symbol]
                if state.hold_quantity > 0 or (state.grid_bot and state.grid_bot.active_orders):
                    state.allocation_usd = 0.0
                else:
                    self.remove_symbol(symbol)

            logger.info(
                f"Orchestrator: allocated ${result.total_allocated:.2f} "
                f"across {len(result.allocations)} symbols"
            )
            self.telegram.send(
                f"Portfolio Update: {len(result.allocations)} Coins\n"
                f"Investiert: ${result.total_allocated:.2f}\n"
                f"Cash: ${result.cash_remaining:.2f}"
            )
            return result

        except Exception as e:
            logger.error(f"Orchestrator: scan_and_allocate error: {e}")
            return None

    def rebalance(self) -> dict[str, dict]:
        """Check allocation drift and rebalance if needed.

        Only rebalances if:
        - At least REBALANCE_INTERVAL_HOURS since last rebalance
        - Any symbol drifted more than REBALANCE_DRIFT_PCT from target

        Returns:
            Dict of adjustments made: {symbol: {action, amount}}
        """
        now = datetime.now()
        if self._last_rebalance:
            hours_since = (now - self._last_rebalance).total_seconds() / 3600
            if hours_since < self.REBALANCE_INTERVAL_HOURS:
                return {}

        if not self.symbols:
            return {}

        # Calculate current values
        total_value = 0.0
        current_values: dict[str, float] = {}
        for symbol, state in self.symbols.items():
            price = self.client.get_current_price(symbol)
            if not price or price <= 0:
                continue

            if state.hold_quantity > 0:
                current_values[symbol] = state.hold_quantity * price
            elif state.grid_bot and state.grid_bot.active_orders:
                # Estimate grid value from active orders
                order_value = sum(
                    float(o["price"]) * float(o["quantity"])
                    for o in state.grid_bot.active_orders.values()
                )
                current_values[symbol] = order_value
            else:
                current_values[symbol] = state.allocation_usd

            total_value += current_values.get(symbol, 0)

        if total_value <= 0:
            return {}

        # Check drift
        adjustments: dict[str, dict] = {}
        for symbol, state in self.symbols.items():
            if state.allocation_usd <= 0:
                continue

            current = current_values.get(symbol, 0)
            target = state.allocation_usd
            if target <= 0:
                continue

            drift_pct = abs(current - target) / target * 100
            if drift_pct > self.REBALANCE_DRIFT_PCT:
                diff = target - current
                if diff > self.config.min_position_usd:
                    adjustments[symbol] = {"action": "INCREASE", "amount": diff}
                elif diff < -self.config.min_position_usd:
                    adjustments[symbol] = {"action": "DECREASE", "amount": abs(diff)}

        if adjustments:
            self._last_rebalance = now
            logger.info(f"Orchestrator: rebalance needed for {len(adjustments)} symbols")
            self.telegram.send(
                f"Rebalance: {len(adjustments)} Anpassungen\n"
                + "\n".join(
                    f"  {s}: {a['action']} ${a['amount']:.2f}" for s, a in adjustments.items()
                )
            )
        else:
            self._last_rebalance = now

        return adjustments

    def get_status(self) -> dict[str, Any]:
        """Return current orchestrator status."""
        mode_state = self.mode_manager.get_current_mode()
        return {
            "mode": mode_state.current_mode.value,
            "mode_since": mode_state.mode_since.isoformat(),
            "symbols": {s: st.to_dict() for s, st in self.symbols.items()},
            "running": self.running,
        }
