"""
Tests für CohortManager
"""


class TestCohortConfig:
    """Tests für CohortConfig Dataclass"""

    def test_default_values(self):
        """Test Default-Werte"""
        from src.core.cohort_manager import CohortConfig

        config = CohortConfig()

        assert config.grid_range_pct == 5.0
        assert config.min_confidence == 0.5
        assert config.min_fear_greed == 0
        assert config.max_fear_greed == 100
        assert config.use_playbook is True
        assert config.risk_tolerance == "medium"
        assert config.frozen is False

    def test_from_json(self):
        """Test CohortConfig Erstellung aus JSON"""
        from src.core.cohort_manager import CohortConfig

        config = CohortConfig.from_json(
            {
                "grid_range_pct": 3.0,
                "min_confidence": 0.7,
                "frozen": True,
            }
        )

        assert config.grid_range_pct == 3.0
        assert config.min_confidence == 0.7
        assert config.frozen is True

    def test_to_json(self):
        """Test CohortConfig Serialisierung"""
        from src.core.cohort_manager import CohortConfig

        config = CohortConfig(
            grid_range_pct=2.0,
            min_confidence=0.8,
            frozen=True,
        )

        data = config.to_json()

        assert data["grid_range_pct"] == 2.0
        assert data["min_confidence"] == 0.8
        assert data["frozen"] is True


class TestCohort:
    """Tests für Cohort Dataclass"""

    def test_cohort_creation(self):
        """Test Cohort Erstellung"""
        from src.core.cohort_manager import Cohort, CohortConfig

        config = CohortConfig()
        cohort = Cohort(
            id="test-id",
            name="test",
            description="Test Cohort",
            config=config,
            starting_capital=1000.0,
            current_capital=1050.0,
            is_active=True,
        )

        assert cohort.name == "test"
        assert cohort.is_active is True
        assert cohort.starting_capital == 1000.0

    def test_should_trade_confidence_check(self):
        """Test Trading-Entscheidung basierend auf Confidence"""
        from src.core.cohort_manager import Cohort, CohortConfig

        config = CohortConfig(min_confidence=0.6)
        cohort = Cohort(
            id="1",
            name="test",
            description="",
            config=config,
            starting_capital=1000.0,
            current_capital=1000.0,
        )

        # Confidence zu niedrig
        assert cohort.should_trade(0.5, 50) is False
        # Confidence hoch genug
        assert cohort.should_trade(0.7, 50) is True

    def test_should_trade_inactive(self):
        """Test dass inaktive Cohort nicht tradet"""
        from src.core.cohort_manager import Cohort, CohortConfig

        config = CohortConfig()
        cohort = Cohort(
            id="1",
            name="test",
            description="",
            config=config,
            starting_capital=1000.0,
            current_capital=1000.0,
            is_active=False,
        )

        assert cohort.should_trade(0.9, 50) is False


class TestHybridConfigFromCohort:
    """Tests for HybridConfig.from_cohort()."""

    def test_from_cohort_maps_fields(self):
        from src.core.cohort_manager import Cohort, CohortConfig
        from src.core.hybrid_config import HybridConfig

        config = CohortConfig(grid_range_pct=2.0, min_confidence=0.7, risk_tolerance="low")
        cohort = Cohort(
            id="1",
            name="conservative",
            description="test",
            config=config,
            starting_capital=100,
            current_capital=100,
        )

        hc = HybridConfig.from_cohort(cohort)
        assert hc.grid_range_percent == 2.0
        assert hc.min_confidence == 0.7
        assert hc.allowed_categories == ("LARGE_CAP",)
        assert hc.total_investment == 100
        assert hc.max_symbols == 2
        assert hc.portfolio_constraints_preset == "small"

    def test_from_cohort_aggressive(self):
        from src.core.cohort_manager import Cohort, CohortConfig
        from src.core.hybrid_config import HybridConfig

        config = CohortConfig(grid_range_pct=8.0, min_confidence=0.3, risk_tolerance="high")
        cohort = Cohort(
            id="2",
            name="aggressive",
            description="test",
            config=config,
            starting_capital=100,
            current_capital=95,
        )

        hc = HybridConfig.from_cohort(cohort)
        assert hc.grid_range_percent == 8.0
        assert hc.min_confidence == 0.3
        assert hc.allowed_categories == (
            "LARGE_CAP",
            "MID_CAP",
            "L2",
            "DEFI",
            "AI",
            "GAMING",
        )
        assert hc.total_investment == 95
        assert hc.portfolio_constraints_preset == "small"

    def test_from_cohort_validates(self):
        from src.core.cohort_manager import Cohort, CohortConfig
        from src.core.hybrid_config import HybridConfig

        config = CohortConfig(grid_range_pct=5.0, risk_tolerance="medium")
        cohort = Cohort(
            id="3",
            name="balanced",
            description="test",
            config=config,
            starting_capital=100,
            current_capital=100,
        )

        hc = HybridConfig.from_cohort(cohort)
        valid, errors = hc.validate()
        assert valid, errors


class TestCohortOrchestrator:
    """Tests for CohortOrchestrator."""

    def test_initialize_no_cohorts(self, reset_new_singletons):
        from unittest.mock import MagicMock, patch

        from src.core.cohort_orchestrator import CohortOrchestrator

        mock_cm = MagicMock()
        mock_cm.get_active_cohorts.return_value = []

        with patch(
            "src.core.cohort_orchestrator.CohortManager.get_instance",
            return_value=mock_cm,
        ):
            co = CohortOrchestrator(client=MagicMock())
            assert co.initialize() is False
            assert len(co.orchestrators) == 0

    def test_initialize_with_cohorts(self, reset_new_singletons):
        from unittest.mock import MagicMock, patch

        from src.core.cohort_manager import Cohort, CohortConfig
        from src.core.cohort_orchestrator import CohortOrchestrator

        cohorts = [
            Cohort(
                id="1",
                name="conservative",
                description="test",
                config=CohortConfig(grid_range_pct=2.0, risk_tolerance="low"),
                starting_capital=100,
                current_capital=100,
            ),
            Cohort(
                id="2",
                name="aggressive",
                description="test",
                config=CohortConfig(grid_range_pct=8.0, risk_tolerance="high"),
                starting_capital=100,
                current_capital=100,
            ),
        ]

        mock_cm = MagicMock()
        mock_cm.get_active_cohorts.return_value = cohorts

        with (
            patch(
                "src.core.cohort_orchestrator.CohortManager.get_instance",
                return_value=mock_cm,
            ),
            patch("src.core.hybrid_orchestrator.TelegramNotifier"),
            patch("src.core.hybrid_orchestrator.StopLossManager"),
        ):
            co = CohortOrchestrator(client=MagicMock())
            assert co.initialize() is True
            assert len(co.orchestrators) == 2
            assert "conservative" in co.orchestrators
            assert "aggressive" in co.orchestrators

    def test_tick_calls_all_orchestrators(self, reset_new_singletons):
        from unittest.mock import MagicMock

        from src.core.cohort_orchestrator import CohortOrchestrator

        co = CohortOrchestrator(client=MagicMock())
        mock_orch1 = MagicMock()
        mock_orch2 = MagicMock()
        co.orchestrators = {"a": mock_orch1, "b": mock_orch2}

        co.tick()

        mock_orch1.tick.assert_called_once()
        mock_orch2.tick.assert_called_once()

    def test_stop_stops_all(self, reset_new_singletons):
        from unittest.mock import MagicMock

        from src.core.cohort_orchestrator import CohortOrchestrator

        co = CohortOrchestrator(client=MagicMock())
        mock_orch = MagicMock()
        co.orchestrators = {"a": mock_orch}
        co.running = True

        co.stop()

        assert co.running is False
        mock_orch.stop.assert_called_once()

    def test_get_all_status(self, reset_new_singletons):
        from unittest.mock import MagicMock

        from src.core.cohort_orchestrator import CohortOrchestrator

        co = CohortOrchestrator(client=MagicMock())
        mock_orch = MagicMock()
        mock_orch.get_status.return_value = {"mode": "GRID", "symbols": {}}
        co.orchestrators = {"conservative": mock_orch}
        co.cohort_configs = {"conservative": {"id": "1"}}

        status = co.get_all_status()
        assert "conservative" in status
        assert status["conservative"]["mode"] == "GRID"
        assert status["conservative"]["cohort_config"]["id"] == "1"


class TestCohortManager:
    """Tests für Cohort Manager"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.core.cohort_manager import CohortManager

        c1 = CohortManager.get_instance()
        c2 = CohortManager.get_instance()

        assert c1 is c2
