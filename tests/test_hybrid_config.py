"""Tests for HybridConfig."""

from src.core.hybrid_config import HybridConfig


class TestHybridConfig:
    def test_defaults(self):
        config = HybridConfig()
        assert config.initial_mode == "GRID"
        assert config.enable_mode_switching is True
        assert config.min_regime_probability == 0.75
        assert config.min_regime_duration_days == 2
        assert config.mode_cooldown_hours == 24
        assert config.hold_trailing_stop_pct == 7.0
        assert config.grid_range_percent == 5.0
        assert config.num_grids == 3
        assert config.cash_exit_timeout_hours == 2.0
        assert config.max_symbols == 8
        assert config.min_position_usd == 10.0
        assert config.total_investment == 400.0
        assert config.portfolio_constraints_preset == "small"

    def test_validate_valid(self):
        config = HybridConfig()
        is_valid, errors = config.validate()
        assert is_valid
        assert errors == []

    def test_validate_invalid_mode(self):
        config = HybridConfig(initial_mode="INVALID")
        is_valid, errors = config.validate()
        assert not is_valid
        assert any("initial_mode" in e for e in errors)

    def test_validate_probability_too_low(self):
        config = HybridConfig(min_regime_probability=0.3)
        is_valid, errors = config.validate()
        assert not is_valid
        assert any("min_regime_probability" in e for e in errors)

    def test_validate_probability_too_high(self):
        config = HybridConfig(min_regime_probability=1.5)
        is_valid, _errors = config.validate()
        assert not is_valid

    def test_validate_trailing_stop_too_high(self):
        config = HybridConfig(hold_trailing_stop_pct=60)
        is_valid, errors = config.validate()
        assert not is_valid
        assert any("hold_trailing_stop_pct" in e for e in errors)

    def test_validate_investment_too_low(self):
        config = HybridConfig(total_investment=5)
        is_valid, errors = config.validate()
        assert not is_valid
        assert any("total_investment" in e for e in errors)

    def test_validate_max_symbols_out_of_range(self):
        config = HybridConfig(max_symbols=0)
        is_valid, _errors = config.validate()
        assert not is_valid

        config = HybridConfig(max_symbols=25)
        is_valid, _errors = config.validate()
        assert not is_valid

    def test_validate_min_position_too_low(self):
        config = HybridConfig(min_position_usd=2)
        is_valid, _errors = config.validate()
        assert not is_valid

    def test_validate_invalid_preset(self):
        config = HybridConfig(portfolio_constraints_preset="unknown")
        is_valid, _errors = config.validate()
        assert not is_valid

    def test_validate_all_presets(self):
        for preset in ("small", "conservative", "balanced", "aggressive"):
            config = HybridConfig(portfolio_constraints_preset=preset)
            is_valid, _ = config.validate()
            assert is_valid

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("HYBRID_INITIAL_MODE", "HOLD")
        monkeypatch.setenv("HYBRID_ENABLE_MODE_SWITCHING", "false")
        monkeypatch.setenv("HYBRID_TOTAL_INVESTMENT", "800")
        monkeypatch.setenv("HYBRID_MAX_SYMBOLS", "5")

        config = HybridConfig.from_env()
        assert config.initial_mode == "HOLD"
        assert config.enable_mode_switching is False
        assert config.total_investment == 800.0
        assert config.max_symbols == 5

    def test_from_env_defaults(self):
        config = HybridConfig.from_env()
        assert config.initial_mode == "GRID"
        assert config.enable_mode_switching is True

    def test_to_dict(self):
        config = HybridConfig(total_investment=500.0, max_symbols=6)
        d = config.to_dict()
        assert d["total_investment"] == 500.0
        assert d["max_symbols"] == 6
        assert d["initial_mode"] == "GRID"
        assert "enable_mode_switching" in d

    def test_multiple_validation_errors(self):
        config = HybridConfig(
            initial_mode="X",
            min_regime_probability=2.0,
            total_investment=1,
            max_symbols=50,
        )
        is_valid, errors = config.validate()
        assert not is_valid
        assert len(errors) >= 4


class TestHybridConfigInAppConfig:
    def test_app_config_has_hybrid(self, monkeypatch):
        """HybridConfig is accessible via AppConfig."""
        import src.core.config as config_module

        config_module._config = None

        config = config_module.get_config()
        assert hasattr(config, "hybrid")
        assert isinstance(config.hybrid, HybridConfig)

        config_module._config = None

    def test_app_config_hybrid_from_env(self, monkeypatch):
        """HybridConfig loads from env via AppConfig."""
        import src.core.config as config_module

        config_module._config = None
        monkeypatch.setenv("HYBRID_TOTAL_INVESTMENT", "600")

        config = config_module.get_config()
        assert config.hybrid.total_investment == 600.0

        config_module._config = None
