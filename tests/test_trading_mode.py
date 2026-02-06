"""Tests for TradingMode, ModeState, and ModeTransitionEvent."""

from datetime import datetime, timedelta

from src.core.trading_mode import ModeState, ModeTransitionEvent, TradingMode


class TestTradingMode:
    def test_enum_values(self):
        assert TradingMode.HOLD.value == "HOLD"
        assert TradingMode.GRID.value == "GRID"
        assert TradingMode.CASH.value == "CASH"

    def test_from_string(self):
        assert TradingMode("HOLD") is TradingMode.HOLD
        assert TradingMode("GRID") is TradingMode.GRID
        assert TradingMode("CASH") is TradingMode.CASH

    def test_invalid_mode_raises(self):
        import pytest

        with pytest.raises(ValueError):
            TradingMode("INVALID")


class TestModeState:
    def test_default_state(self):
        state = ModeState(current_mode=TradingMode.GRID)
        assert state.current_mode is TradingMode.GRID
        assert state.previous_mode is None
        assert state.regime_at_switch is None
        assert state.regime_probability == 0.0
        assert state.transition_count_24h == 0

    def test_mode_duration_hours(self):
        state = ModeState(
            current_mode=TradingMode.HOLD,
            mode_since=datetime.now() - timedelta(hours=5),
        )
        assert 4.9 < state.mode_duration_hours < 5.1

    def test_to_dict(self):
        state = ModeState(
            current_mode=TradingMode.HOLD,
            previous_mode=TradingMode.GRID,
            regime_at_switch="BULL",
            regime_probability=0.85,
            transition_count_24h=1,
        )
        d = state.to_dict()
        assert d["current_mode"] == "HOLD"
        assert d["previous_mode"] == "GRID"
        assert d["regime_at_switch"] == "BULL"
        assert d["regime_probability"] == 0.85
        assert d["transition_count_24h"] == 1

    def test_to_dict_no_previous(self):
        state = ModeState(current_mode=TradingMode.CASH)
        d = state.to_dict()
        assert d["previous_mode"] is None

    def test_from_dict_roundtrip(self):
        original = ModeState(
            current_mode=TradingMode.HOLD,
            previous_mode=TradingMode.GRID,
            regime_at_switch="BULL",
            regime_probability=0.82,
            transition_count_24h=2,
        )
        d = original.to_dict()
        restored = ModeState.from_dict(d)
        assert restored.current_mode is TradingMode.HOLD
        assert restored.previous_mode is TradingMode.GRID
        assert restored.regime_at_switch == "BULL"
        assert restored.regime_probability == 0.82
        assert restored.transition_count_24h == 2

    def test_from_dict_no_previous(self):
        d = {
            "current_mode": "CASH",
            "previous_mode": None,
            "mode_since": datetime.now().isoformat(),
        }
        state = ModeState.from_dict(d)
        assert state.current_mode is TradingMode.CASH
        assert state.previous_mode is None

    def test_from_dict_minimal(self):
        d = {
            "current_mode": "GRID",
            "mode_since": datetime.now().isoformat(),
        }
        state = ModeState.from_dict(d)
        assert state.current_mode is TradingMode.GRID
        assert state.regime_probability == 0.0


class TestModeTransitionEvent:
    def test_creation(self):
        event = ModeTransitionEvent(
            from_mode=TradingMode.GRID,
            to_mode=TradingMode.HOLD,
            regime="BULL",
            regime_probability=0.85,
            reason="Regime switched to BULL with high confidence",
        )
        assert event.from_mode is TradingMode.GRID
        assert event.to_mode is TradingMode.HOLD
        assert event.regime == "BULL"
        assert event.regime_probability == 0.85

    def test_to_dict(self):
        event = ModeTransitionEvent(
            from_mode=TradingMode.HOLD,
            to_mode=TradingMode.CASH,
            regime="BEAR",
            regime_probability=0.90,
            reason="Emergency BEAR detection",
        )
        d = event.to_dict()
        assert d["from_mode"] == "HOLD"
        assert d["to_mode"] == "CASH"
        assert d["regime"] == "BEAR"
        assert d["reason"] == "Emergency BEAR detection"
        assert "timestamp" in d
