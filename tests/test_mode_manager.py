"""Tests for ModeManager with hysteresis logic."""

from datetime import datetime, timedelta

from src.core.hybrid_config import HybridConfig
from src.core.mode_manager import (
    EMERGENCY_BEAR_PROBABILITY,
    MAX_TRANSITIONS_48H,
    REGIME_MODE_MAP,
    ModeManager,
)
from src.core.trading_mode import TradingMode
from src.portfolio.constraints import (
    AGGRESSIVE_CONSTRAINTS,
    BALANCED_CONSTRAINTS,
    CONSERVATIVE_CONSTRAINTS,
    SMALL_PORTFOLIO_CONSTRAINTS,
)


class TestModeManagerInit:
    def test_default_mode_is_grid(self):
        mm = ModeManager()
        assert mm.get_current_mode().current_mode is TradingMode.GRID

    def test_custom_initial_mode(self):
        config = HybridConfig(initial_mode="HOLD")
        mm = ModeManager(config)
        assert mm.get_current_mode().current_mode is TradingMode.HOLD

    def test_config_from_constructor(self):
        config = HybridConfig(total_investment=800)
        mm = ModeManager(config)
        assert mm.config.total_investment == 800

    def test_separate_instances_are_independent(self):
        m1 = ModeManager()
        m2 = ModeManager()
        assert m1 is not m2
        m1.request_switch(TradingMode.HOLD, "test")
        assert m1.get_current_mode().current_mode is TradingMode.HOLD
        assert m2.get_current_mode().current_mode is TradingMode.GRID


class TestRegimeModeMapping:
    def test_bull_maps_to_hold(self):
        assert REGIME_MODE_MAP["BULL"] is TradingMode.HOLD

    def test_sideways_maps_to_grid(self):
        assert REGIME_MODE_MAP["SIDEWAYS"] is TradingMode.GRID

    def test_bear_maps_to_cash(self):
        assert REGIME_MODE_MAP["BEAR"] is TradingMode.CASH


class TestEvaluateMode:
    def test_none_regime_keeps_current(self):
        mm = ModeManager()
        mode, reason = mm.evaluate_mode(regime=None)
        assert mode is TradingMode.GRID
        assert "None" in reason

    def test_transition_regime_keeps_current(self):
        mm = ModeManager()
        mode, reason = mm.evaluate_mode(regime="TRANSITION", regime_probability=0.8)
        assert mode is TradingMode.GRID
        assert "TRANSITION" in reason

    def test_already_in_correct_mode(self):
        mm = ModeManager()  # starts GRID
        mode, reason = mm.evaluate_mode(
            regime="SIDEWAYS", regime_probability=0.9, regime_duration_days=5
        )
        assert mode is TradingMode.GRID
        assert "Already" in reason

    def test_bull_with_high_confidence_suggests_hold(self):
        mm = ModeManager()
        mode, _reason = mm.evaluate_mode(
            regime="BULL", regime_probability=0.85, regime_duration_days=3
        )
        assert mode is TradingMode.HOLD

    def test_bear_with_high_confidence_suggests_cash(self):
        mm = ModeManager()
        mode, _reason = mm.evaluate_mode(
            regime="BEAR", regime_probability=0.80, regime_duration_days=3
        )
        assert mode is TradingMode.CASH

    def test_probability_below_threshold_keeps_current(self):
        mm = ModeManager(HybridConfig(min_regime_probability=0.75))
        mode, reason = mm.evaluate_mode(
            regime="BULL", regime_probability=0.60, regime_duration_days=5
        )
        assert mode is TradingMode.GRID  # stays
        assert "below threshold" in reason

    def test_duration_below_threshold_keeps_current(self):
        mm = ModeManager(HybridConfig(min_regime_duration_days=2))
        mode, reason = mm.evaluate_mode(
            regime="BULL", regime_probability=0.85, regime_duration_days=1
        )
        assert mode is TradingMode.GRID
        assert "duration" in reason

    def test_emergency_bear_skips_hysteresis(self):
        mm = ModeManager(HybridConfig(min_regime_duration_days=5))
        mode, reason = mm.evaluate_mode(
            regime="BEAR",
            regime_probability=EMERGENCY_BEAR_PROBABILITY,
            regime_duration_days=0,
        )
        assert mode is TradingMode.CASH
        assert "Emergency" in reason

    def test_emergency_bear_below_threshold(self):
        mm = ModeManager(HybridConfig(min_regime_duration_days=5))
        mode, reason = mm.evaluate_mode(
            regime="BEAR",
            regime_probability=0.80,  # below emergency threshold
            regime_duration_days=0,
        )
        # Not emergency, and duration too short
        assert mode is TradingMode.GRID
        assert "duration" in reason

    def test_mode_switching_disabled(self):
        mm = ModeManager(HybridConfig(enable_mode_switching=False))
        mode, reason = mm.evaluate_mode(
            regime="BULL", regime_probability=0.95, regime_duration_days=10
        )
        assert mode is TradingMode.GRID
        assert "disabled" in reason


class TestRequestSwitch:
    def test_switch_success(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))
        result = mm.request_switch(TradingMode.HOLD, "BULL detected")
        assert result is True
        assert mm.get_current_mode().current_mode is TradingMode.HOLD

    def test_switch_same_mode_returns_false(self):
        mm = ModeManager()
        result = mm.request_switch(TradingMode.GRID, "Already in GRID")
        assert result is False

    def test_switch_records_previous_mode(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))
        mm.request_switch(TradingMode.HOLD, "test")
        state = mm.get_current_mode()
        assert state.previous_mode is TradingMode.GRID
        assert state.current_mode is TradingMode.HOLD

    def test_switch_records_transition_event(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))
        mm.request_switch(TradingMode.CASH, "Bear market")
        history = mm.get_transition_history()
        assert len(history) == 1
        assert history[0].from_mode is TradingMode.GRID
        assert history[0].to_mode is TradingMode.CASH
        assert history[0].reason == "Bear market"


class TestCooldown:
    def test_cooldown_blocks_switch(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=24))
        # First switch succeeds
        mm.request_switch(TradingMode.HOLD, "BULL")
        # Evaluate should be blocked by cooldown
        mode, reason = mm.evaluate_mode(
            regime="BEAR", regime_probability=0.80, regime_duration_days=3
        )
        assert mode is TradingMode.HOLD  # stays
        assert "cooldown" in reason

    def test_cooldown_expires(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=1))
        # Execute a switch with a past timestamp
        mm._execute_switch(TradingMode.HOLD, "test")
        # Move the transition timestamp to the past
        mm._transition_history[-1].timestamp = datetime.now() - timedelta(hours=2)

        # Now evaluate should not be blocked
        mode, _reason = mm.evaluate_mode(
            regime="BEAR", regime_probability=0.80, regime_duration_days=3
        )
        assert mode is TradingMode.CASH

    def test_emergency_bear_bypasses_cooldown(self):
        """Emergency BEAR skips hysteresis checks including cooldown."""
        mm = ModeManager(HybridConfig(mode_cooldown_hours=24))
        mm.request_switch(TradingMode.HOLD, "BULL")
        # Emergency BEAR evaluation bypasses cooldown because evaluate_mode
        # returns early before cooldown check for emergency
        mode, reason = mm.evaluate_mode(
            regime="BEAR",
            regime_probability=EMERGENCY_BEAR_PROBABILITY,
            regime_duration_days=0,
        )
        assert mode is TradingMode.CASH
        assert "Emergency" in reason


class TestSafetyLock:
    def test_too_many_transitions_locks_to_grid(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))

        # Execute multiple transitions to trigger lock
        for i in range(MAX_TRANSITIONS_48H):
            target = TradingMode.HOLD if i % 2 == 0 else TradingMode.CASH
            mm._execute_switch(target, f"test {i}")

        # Next request should trigger lock
        result = mm.request_switch(TradingMode.HOLD, "should be locked")
        assert result is False

    def test_locked_mode_persists_in_evaluate(self):
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))

        # Manually set lock
        mm._locked_mode = TradingMode.GRID

        mode, reason = mm.evaluate_mode(
            regime="BULL", regime_probability=0.95, regime_duration_days=10
        )
        assert mode is TradingMode.GRID
        assert "Safety lock" in reason


class TestConstraintsForMode:
    def test_small_portfolio_preset(self):
        mm = ModeManager(HybridConfig(portfolio_constraints_preset="small"))
        constraints = mm.get_constraints_for_mode()
        assert constraints is SMALL_PORTFOLIO_CONSTRAINTS

    def test_preset_takes_priority_over_mode(self):
        mm = ModeManager(HybridConfig(portfolio_constraints_preset="balanced"))
        # Preset always takes priority over mode-based mapping
        assert mm.get_constraints_for_mode(TradingMode.HOLD) is BALANCED_CONSTRAINTS
        assert mm.get_constraints_for_mode(TradingMode.GRID) is BALANCED_CONSTRAINTS
        assert mm.get_constraints_for_mode(TradingMode.CASH) is BALANCED_CONSTRAINTS

    def test_all_presets_return_correct_constraints(self):
        mm_c = ModeManager(HybridConfig(portfolio_constraints_preset="conservative"))
        assert mm_c.get_constraints_for_mode() is CONSERVATIVE_CONSTRAINTS

        mm_a = ModeManager(HybridConfig(portfolio_constraints_preset="aggressive"))
        assert mm_a.get_constraints_for_mode() is AGGRESSIVE_CONSTRAINTS

    def test_unknown_preset_falls_back_to_mode_mapping(self):
        mm = ModeManager(HybridConfig(portfolio_constraints_preset="unknown"))
        # Unknown preset -> falls through to mode-based mapping (GRID -> BALANCED)
        assert mm.get_constraints_for_mode() is BALANCED_CONSTRAINTS
        assert mm.get_constraints_for_mode(TradingMode.HOLD) is AGGRESSIVE_CONSTRAINTS


class TestUpdateRegimeInfo:
    def test_update_regime_info(self):
        mm = ModeManager()
        mm.update_regime_info("BULL", 0.82)
        state = mm.get_current_mode()
        assert state.regime_at_switch == "BULL"
        assert state.regime_probability == 0.82


class TestModeManagerIntegration:
    """Full workflow tests."""

    def test_full_lifecycle_grid_to_hold_to_cash(self):
        """GRID -> HOLD -> CASH lifecycle."""
        mm = ModeManager(HybridConfig(mode_cooldown_hours=0))

        # Start in GRID
        assert mm.get_current_mode().current_mode is TradingMode.GRID

        # BULL detected -> HOLD
        mode, reason = mm.evaluate_mode("BULL", 0.85, 3)
        assert mode is TradingMode.HOLD
        mm.request_switch(mode, reason)
        assert mm.get_current_mode().current_mode is TradingMode.HOLD

        # BEAR detected -> CASH (emergency)
        mode, reason = mm.evaluate_mode("BEAR", 0.90, 0)
        assert mode is TradingMode.CASH
        assert "Emergency" in reason

    def test_sideways_stays_grid(self):
        """SIDEWAYS regime keeps GRID mode."""
        mm = ModeManager()
        mode, reason = mm.evaluate_mode("SIDEWAYS", 0.90, 5)
        assert mode is TradingMode.GRID
        assert "Already" in reason
