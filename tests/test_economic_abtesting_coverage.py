"""Tests for src/data/economic_events.py and src/optimization/ab_testing.py."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ═══════════════════════════════════════════════════════════════
# EconomicEvent
# ═══════════════════════════════════════════════════════════════


class TestEconomicEvent:
    def test_is_upcoming_true(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now() + timedelta(hours=12),
            name="FOMC Meeting",
            country="US",
            impact="HIGH",
            category="FOMC",
        )
        assert event.is_upcoming(hours=24) is True

    def test_is_upcoming_false_past(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now() - timedelta(hours=1),
            name="FOMC Meeting",
            country="US",
            impact="HIGH",
            category="FOMC",
        )
        assert event.is_upcoming(hours=24) is False

    def test_is_upcoming_false_too_far(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now() + timedelta(hours=48),
            name="CPI",
            country="US",
            impact="HIGH",
            category="CPI",
        )
        assert event.is_upcoming(hours=24) is False

    def test_crypto_impact_analysis_fomc(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now(),
            name="FOMC",
            country="US",
            impact="HIGH",
            category="FOMC",
        )
        analysis = event.crypto_impact_analysis()
        assert "Zinsentscheidung" in analysis or "Fed" in analysis

    def test_crypto_impact_analysis_cpi(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now(),
            name="CPI",
            country="US",
            impact="HIGH",
            category="CPI",
        )
        analysis = event.crypto_impact_analysis()
        assert "Inflation" in analysis or "CPI" in analysis

    def test_crypto_impact_analysis_unknown(self):
        from src.data.economic_events import EconomicEvent

        event = EconomicEvent(
            date=datetime.now(),
            name="Unknown",
            country="US",
            impact="LOW",
            category="UNKNOWN",
        )
        analysis = event.crypto_impact_analysis()
        assert "Keine" in analysis


# ═══════════════════════════════════════════════════════════════
# EconomicCalendar
# ═══════════════════════════════════════════════════════════════


class TestEconomicCalendar:
    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_categorize_event(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        assert cal._categorize_event("FOMC MEETING") == "FOMC"
        assert cal._categorize_event("CPI RELEASE") == "CPI"
        assert cal._categorize_event("NON-FARM PAYROLLS") == "NFP"
        assert cal._categorize_event("GDP Growth") == "GDP"
        assert cal._categorize_event("ECB Rate Decision") == "ECB"
        assert cal._categorize_event("Bitcoin ETF Approval") == "CRYPTO"
        assert cal._categorize_event("Something else") == "OTHER"

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_fetch_upcoming_events(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar

        config = MagicMock()
        config.api.economic_calendar_url = "https://example.com/calendar"
        mock_config.return_value = config

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "result": [
                {
                    "title": "FOMC Meeting",
                    "date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
                    + "Z",
                    "country": "US",
                    "importance": 3,
                    "previous": "5.25",
                    "forecast": "5.50",
                    "actual": "",
                },
            ]
        }
        mock_http.return_value = mock_client

        cal = EconomicCalendar()
        events = cal.fetch_upcoming_events(days=7)
        assert len(events) >= 1  # At least the API event

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_fetch_upcoming_events_api_error(self, mock_http, mock_config):
        from src.api.http_client import HTTPClientError
        from src.data.economic_events import EconomicCalendar

        config = MagicMock()
        config.api.economic_calendar_url = "https://example.com/calendar"
        mock_config.return_value = config

        mock_client = MagicMock()
        mock_client.get.side_effect = HTTPClientError("API down")
        mock_http.return_value = mock_client

        cal = EconomicCalendar()
        events = cal.fetch_upcoming_events(days=7)
        # Should still return recurring events
        assert isinstance(events, list)

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_get_upcoming_high_impact(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar, EconomicEvent

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        cal.cached_events = [
            EconomicEvent(
                date=datetime.now() + timedelta(hours=12),
                name="FOMC",
                country="US",
                impact="HIGH",
                category="FOMC",
            ),
            EconomicEvent(
                date=datetime.now() + timedelta(hours=12),
                name="Minor Event",
                country="US",
                impact="LOW",
                category="OTHER",
            ),
        ]
        high = cal.get_upcoming_high_impact(hours=24)
        assert len(high) == 1
        assert high[0].name == "FOMC"

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_should_trade_today_no_events(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        cal.cached_events = []
        should_trade, _reason = cal.should_trade_today()
        assert should_trade is True

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_should_trade_today_fomc(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar, EconomicEvent

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        cal.cached_events = [
            EconomicEvent(
                date=datetime.now() + timedelta(hours=6),
                name="FOMC Meeting",
                country="US",
                impact="HIGH",
                category="FOMC",
            ),
        ]
        should_trade, reason = cal.should_trade_today()
        assert should_trade is False
        assert "FOMC" in reason

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_should_trade_today_cpi(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar, EconomicEvent

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        cal.cached_events = [
            EconomicEvent(
                date=datetime.now() + timedelta(hours=6),
                name="CPI Release",
                country="US",
                impact="HIGH",
                category="CPI",
            ),
        ]
        should_trade, reason = cal.should_trade_today()
        assert should_trade is False
        assert "CPI" in reason

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_should_trade_today_other_high_impact(self, mock_http, mock_config):
        from src.data.economic_events import EconomicCalendar, EconomicEvent

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        cal = EconomicCalendar()
        cal.cached_events = [
            EconomicEvent(
                date=datetime.now() + timedelta(hours=6),
                name="GDP Release",
                country="US",
                impact="HIGH",
                category="GDP",
            ),
        ]
        should_trade, _reason = cal.should_trade_today()
        assert should_trade is True  # Non-FOMC/CPI high impact allows trading with caution


# ═══════════════════════════════════════════════════════════════
# CryptoSpecificEvents
# ═══════════════════════════════════════════════════════════════


class TestCryptoSpecificEvents:
    def test_get_token_unlocks(self):
        from src.data.economic_events import CryptoSpecificEvents

        events = CryptoSpecificEvents()
        unlocks = events.get_token_unlocks()
        assert unlocks == []

    def test_get_etf_flows(self):
        from src.data.economic_events import CryptoSpecificEvents

        events = CryptoSpecificEvents()
        flows = events.get_etf_flows()
        assert "btc_etf_flow_24h" in flows
        assert "trend" in flows

    def test_get_upcoming_crypto_events(self):
        from src.data.economic_events import CryptoSpecificEvents

        events = CryptoSpecificEvents()
        upcoming = events.get_upcoming_crypto_events()
        assert upcoming == []


# ═══════════════════════════════════════════════════════════════
# MacroAnalyzer
# ═══════════════════════════════════════════════════════════════


class TestMacroAnalyzer:
    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_get_macro_context(self, mock_http, mock_config):
        from src.data.economic_events import MacroAnalyzer

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        analyzer = MacroAnalyzer()
        analyzer.calendar.cached_events = []
        context = analyzer.get_macro_context()
        assert "should_trade" in context
        assert "reason" in context
        assert "etf_flows" in context

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_generate_macro_prompt(self, mock_http, mock_config):
        from src.data.economic_events import MacroAnalyzer

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        analyzer = MacroAnalyzer()
        analyzer.calendar.cached_events = []
        prompt = analyzer.generate_macro_prompt()
        assert "MAKROÖKONOMISCHER KONTEXT" in prompt
        assert "ETF Flows" in prompt

    @patch("src.data.economic_events.get_config")
    @patch("src.data.economic_events.get_http_client")
    def test_generate_macro_prompt_with_events(self, mock_http, mock_config):
        from src.data.economic_events import EconomicEvent, MacroAnalyzer

        mock_config.return_value = MagicMock()
        mock_http.return_value = MagicMock()

        analyzer = MacroAnalyzer()
        analyzer.calendar.cached_events = [
            EconomicEvent(
                date=datetime.now() + timedelta(hours=12),
                name="FOMC Meeting",
                country="US",
                impact="HIGH",
                category="FOMC",
            ),
        ]
        prompt = analyzer.generate_macro_prompt()
        assert "FOMC" in prompt


# ═══════════════════════════════════════════════════════════════
# ABTestingFramework
# ═══════════════════════════════════════════════════════════════


class TestABTestingFramework:
    @pytest.fixture()
    def framework(self):
        with patch("src.optimization.ab_testing.POSTGRES_AVAILABLE", False):
            from src.optimization.ab_testing import ABTestingFramework

            fw = ABTestingFramework.__new__(ABTestingFramework)
            fw.conn = None
            fw.experiments = {}
            return fw

    def test_create_experiment(self, framework):
        exp = framework.create_experiment(
            name="Test RSI Weight",
            description="Test if higher RSI weight improves performance",
            hypothesis="Higher RSI weight → better timing",
            control_config={"rsi_weight": 0.3},
            treatment_configs=[{"rsi_weight": 0.5}],
            metric="pnl",
            min_sample_size=30,
        )
        assert exp.name == "Test RSI Weight"
        assert exp.control.name == "control"
        assert len(exp.treatments) == 1
        assert exp.treatments[0].name == "treatment_A"

    def test_create_experiment_multiple_treatments(self, framework):
        exp = framework.create_experiment(
            name="Multi Test",
            description="Test multiple configs",
            hypothesis="Test",
            control_config={"weight": 0.3},
            treatment_configs=[{"weight": 0.4}, {"weight": 0.5}, {"weight": 0.6}],
            control_cohort_id="cohort_1",
            treatment_cohort_ids=["cohort_2", "cohort_3", "cohort_4"],
        )
        assert len(exp.treatments) == 3
        assert exp.treatments[0].cohort_id == "cohort_2"
        assert exp.treatments[2].name == "treatment_C"

    def test_start_experiment(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        result = framework.start_experiment(exp.id)
        assert result is True
        assert framework.experiments[exp.id].status.value == "RUNNING"
        assert framework.experiments[exp.id].start_date is not None

    def test_start_experiment_not_found(self, framework):
        result = framework.start_experiment("nonexistent")
        assert result is False

    def test_start_experiment_already_running(self, framework):
        from src.optimization.ab_testing import ExperimentStatus

        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        exp.status = ExperimentStatus.RUNNING
        result = framework.start_experiment(exp.id)
        assert result is False

    def test_pause_and_resume(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        framework.start_experiment(exp.id)
        assert framework.pause_experiment(exp.id) is True
        assert framework.experiments[exp.id].status.value == "PAUSED"
        assert framework.resume_experiment(exp.id) is True
        assert framework.experiments[exp.id].status.value == "RUNNING"

    def test_pause_not_running(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        # DRAFT state, can't pause
        assert framework.pause_experiment(exp.id) is False

    def test_resume_not_paused(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        assert framework.resume_experiment(exp.id) is False

    def test_record_trade(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        framework.start_experiment(exp.id)

        framework.record_trade(exp.id, "control", 1.5)
        framework.record_trade(exp.id, "control", -0.5)
        framework.record_trade(exp.id, "treatment_A", 2.0)

        assert exp.control.sample_size == 2
        assert exp.control.total_pnl == 1.0
        assert exp.treatments[0].sample_size == 1

    def test_record_trade_not_running(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        # Not started, so recording should be ignored
        framework.record_trade(exp.id, "control", 1.0)
        assert exp.control.sample_size == 0

    def test_record_trade_unknown_variant(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
        )
        framework.start_experiment(exp.id)
        # Unknown variant name should not crash
        framework.record_trade(exp.id, "unknown_variant", 1.0)

    def test_analyze_experiment_not_enough_data(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
            min_sample_size=30,
        )
        framework.start_experiment(exp.id)
        # Only 2 trades, not enough
        framework.record_trade(exp.id, "control", 1.0)
        framework.record_trade(exp.id, "control", 2.0)

        result = framework.analyze_experiment(exp.id)
        assert result is None

    def test_analyze_experiment_control_wins(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
            min_sample_size=5,
        )
        framework.start_experiment(exp.id)

        rng = np.random.default_rng(42)
        for _ in range(10):
            framework.record_trade(exp.id, "control", float(rng.normal(2.0, 0.5)))
        for _ in range(10):
            framework.record_trade(exp.id, "treatment_A", float(rng.normal(1.0, 0.5)))

        result = framework.analyze_experiment(exp.id)
        assert result is not None
        assert result.winner == "control"

    def test_analyze_experiment_treatment_wins(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
            min_sample_size=5,
        )
        framework.start_experiment(exp.id)

        rng = np.random.default_rng(42)
        for _ in range(30):
            framework.record_trade(exp.id, "control", float(rng.normal(0.5, 0.3)))
        for _ in range(30):
            framework.record_trade(exp.id, "treatment_A", float(rng.normal(3.0, 0.3)))

        result = framework.analyze_experiment(exp.id)
        assert result is not None
        assert result.winner == "treatment_A"
        assert result.winner_improvement > 0

    def test_complete_experiment(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={},
            treatment_configs=[{}],
            min_sample_size=5,
        )
        framework.start_experiment(exp.id)

        rng = np.random.default_rng(42)
        for _ in range(10):
            framework.record_trade(exp.id, "control", float(rng.normal(1.0, 0.5)))
            framework.record_trade(exp.id, "treatment_A", float(rng.normal(1.0, 0.5)))

        result = framework.complete_experiment(exp.id)
        assert result is not None
        assert exp.status.value == "COMPLETED"

    def test_complete_experiment_not_found(self, framework):
        result = framework.complete_experiment("nonexistent")
        assert result is None

    def test_bootstrap_ci(self, framework):
        control = [1.0, 1.5, 2.0, 0.5, 1.2]
        treatment = [2.0, 2.5, 3.0, 1.5, 2.2]
        lower, upper = framework._bootstrap_ci(control, treatment)
        assert lower < upper

    def test_simple_z_test(self, framework):
        from src.optimization.ab_testing import Variant

        control = Variant(id="c", name="control", config={})
        control.trades = [1.0, 1.5, 2.0, 0.5]
        control.mean_pnl = np.mean(control.trades)
        control.std_pnl = np.std(control.trades)
        control.sample_size = len(control.trades)

        treatment = Variant(id="t", name="treatment_A", config={})
        treatment.trades = [3.0, 3.5, 4.0, 2.5]
        treatment.mean_pnl = np.mean(treatment.trades)
        treatment.std_pnl = np.std(treatment.trades)
        treatment.sample_size = len(treatment.trades)

        p_value = framework._simple_z_test(control, treatment)
        assert 0.0 <= p_value <= 1.0

    def test_simple_z_test_zero_se(self, framework):
        from src.optimization.ab_testing import Variant

        control = Variant(id="c", name="control", config={})
        control.trades = [1.0]
        control.mean_pnl = 1.0
        control.std_pnl = 0.0
        control.sample_size = 1

        treatment = Variant(id="t", name="treatment_A", config={})
        treatment.trades = [1.0]
        treatment.mean_pnl = 1.0
        treatment.std_pnl = 0.0
        treatment.sample_size = 1

        p_value = framework._simple_z_test(control, treatment)
        assert p_value == 1.0

    def test_normal_cdf(self, framework):
        # CDF at 0 should be ~0.5
        assert abs(framework._normal_cdf(0) - 0.5) < 0.01
        # CDF at large positive should be ~1.0
        assert framework._normal_cdf(3.0) > 0.99

    def test_get_experiment_summary(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="Test",
            hypothesis="Test",
            control_config={"a": 1},
            treatment_configs=[{"a": 2}],
        )
        framework.start_experiment(exp.id)
        framework.record_trade(exp.id, "control", 1.0)

        summary = framework.get_experiment_summary(exp.id)
        assert summary["name"] == "Test"
        assert "control" in summary["variants"]

    def test_get_experiment_summary_not_found(self, framework):
        summary = framework.get_experiment_summary("nonexistent")
        assert summary == {}

    def test_get_all_experiments_summary(self, framework):
        framework.create_experiment(
            name="Test1",
            description="",
            hypothesis="",
            control_config={},
            treatment_configs=[{}],
        )
        framework.create_experiment(
            name="Test2",
            description="",
            hypothesis="",
            control_config={},
            treatment_configs=[{}],
        )
        summaries = framework.get_all_experiments_summary()
        assert len(summaries) == 2

    def test_check_early_stopping_not_enough_data(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="",
            hypothesis="",
            control_config={},
            treatment_configs=[{}],
            min_sample_size=30,
        )
        framework.start_experiment(exp.id)
        framework.record_trade(exp.id, "control", 1.0)

        should_stop, reason = framework.check_early_stopping(exp.id)
        assert should_stop is False
        assert "Nicht genug" in reason

    def test_check_early_stopping_not_found(self, framework):
        should_stop, _reason = framework.check_early_stopping("nonexistent")
        assert should_stop is False

    def test_promote_winner(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="",
            hypothesis="",
            control_config={"a": 1},
            treatment_configs=[{"a": 2}],
        )
        # Promote treatment winner (no DB, so just logs)
        framework._promote_winner(exp, "treatment_A")
        assert exp.treatments[0].status.value == "PROMOTED"

    def test_promote_winner_control(self, framework):
        exp = framework.create_experiment(
            name="Test",
            description="",
            hypothesis="",
            control_config={"a": 1},
            treatment_configs=[{"a": 2}],
        )
        # Promote control winner
        framework._promote_winner(exp, "control")

    def test_update_variant_stats_empty(self, framework):
        from src.optimization.ab_testing import Variant

        variant = Variant(id="v", name="test", config={})
        variant.trades = []
        framework._update_variant_stats(variant)
        assert variant.sample_size == 0

    def test_compare_variants(self, framework):
        from src.optimization.ab_testing import Variant

        control = Variant(id="c", name="control", config={})
        control.trades = list(np.random.default_rng(42).normal(1.0, 0.5, 30))
        control.mean_pnl = float(np.mean(control.trades))
        control.std_pnl = float(np.std(control.trades))
        control.sample_size = len(control.trades)

        treatment = Variant(id="t", name="treatment_A", config={})
        treatment.trades = list(np.random.default_rng(43).normal(2.0, 0.5, 30))
        treatment.mean_pnl = float(np.mean(treatment.trades))
        treatment.std_pnl = float(np.std(treatment.trades))
        treatment.sample_size = len(treatment.trades)

        result = framework._compare_variants(control, treatment, alpha=0.05)
        assert result.test_name == "welch_t_test"
        assert 0 <= result.p_value <= 1
