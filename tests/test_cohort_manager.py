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


class TestCohortManager:
    """Tests für Cohort Manager"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.core.cohort_manager import CohortManager

        c1 = CohortManager.get_instance()
        c2 = CohortManager.get_instance()

        assert c1 is c2
