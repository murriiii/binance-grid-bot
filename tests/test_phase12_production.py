"""Tests for Phase 12: Production Readiness.

Covers:
- ProductionValidator (all 9 criteria)
- ValidationReport
- GoLiveChecklist (environment, API keys, feature flags, capital)
- DeploymentPhase detection
"""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# 12.1: ProductionValidator
# ═══════════════════════════════════════════════════════════════


class TestProductionValidator:
    def _make_cursor(self):
        """Create a mock cursor with context manager support."""
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn, cur

    @patch("src.portfolio.validation.get_db_connection")
    def test_validate_no_db(self, mock_db):
        from src.portfolio.validation import ProductionValidator

        mock_db.return_value = None
        validator = ProductionValidator()
        is_ready, failures = validator.validate()
        assert is_ready is False
        assert "Cannot connect to database" in failures

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_validate_all_passing(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 5
        mock_playbook.return_value = pb

        # Set up cursor responses for each check
        cur.fetchone.side_effect = [
            {"count": 6000},  # min_trades
            {"sharpe_ratio": 0.8},  # sharpe
            {"count": 1500},  # signal_evaluations
            {"count": 3},  # regime_changes
            {"worst_drawdown": -10.0},  # drawdown
            {"total": 5000, "wins": 2500},  # win_rate
            {"target_pct": 65.0, "current_pct": 63.0},  # index tracking
            {"count": 3},  # ai_recommendations
        ]

        validator = ProductionValidator()
        report = validator.validate_detailed()

        assert report.is_ready is True
        assert report.passed_count == 9
        assert report.total_count == 9
        assert len(report.failures) == 0

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_validate_partial_pass(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 2  # Below min 4
        mock_playbook.return_value = pb

        cur.fetchone.side_effect = [
            {"count": 1000},  # min_trades: FAIL (need 5000)
            {"sharpe_ratio": 0.8},  # sharpe: PASS
            {"count": 1500},  # signal_evaluations: PASS
            {"count": 3},  # regime_changes: PASS
            {"worst_drawdown": -10.0},  # drawdown: PASS
            {"total": 1000, "wins": 500},  # win_rate: PASS (50%)
            {"target_pct": 65.0, "current_pct": 63.0},  # index: PASS
            {"count": 3},  # ai_recommendations: PASS
        ]

        validator = ProductionValidator()
        report = validator.validate_detailed()

        assert report.is_ready is False
        assert report.passed_count == 7  # trades and playbook fail
        assert len(report.failures) == 2

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_check_min_trades(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 0
        mock_playbook.return_value = pb

        # All zeros — everything fails
        cur.fetchone.return_value = {
            "count": 0,
            "sharpe_ratio": None,
            "worst_drawdown": None,
            "total": 0,
            "wins": 0,
            "target_pct": 65,
            "current_pct": None,
        }

        validator = ProductionValidator()
        report = validator.validate_detailed()

        trade_result = next(r for r in report.results if r.name == "min_trades")
        assert trade_result.passed is False
        assert trade_result.current_value == 0

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_check_drawdown_passes_when_mild(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 0
        mock_playbook.return_value = pb

        cur.fetchone.side_effect = [
            {"count": 0},  # trades
            {"sharpe_ratio": 0},  # sharpe
            {"count": 0},  # signals
            {"count": 0},  # regime
            {"worst_drawdown": -5.0},  # drawdown: PASS (-5 > -15)
            {"total": 0, "wins": 0},  # win rate
            {"target_pct": 65, "current_pct": None},  # index
            {"count": 0},  # ai recs
        ]

        validator = ProductionValidator()
        report = validator.validate_detailed()

        dd_result = next(r for r in report.results if r.name == "max_drawdown")
        assert dd_result.passed is True

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_check_drawdown_fails_when_severe(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 0
        mock_playbook.return_value = pb

        cur.fetchone.side_effect = [
            {"count": 0},
            {"sharpe_ratio": 0},
            {"count": 0},
            {"count": 0},
            {"worst_drawdown": -20.0},  # drawdown: FAIL (-20 < -15)
            {"total": 0, "wins": 0},
            {"target_pct": 65, "current_pct": None},
            {"count": 0},
        ]

        validator = ProductionValidator()
        report = validator.validate_detailed()

        dd_result = next(r for r in report.results if r.name == "max_drawdown")
        assert dd_result.passed is False

    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_check_index_tracking_no_data(self, mock_playbook, mock_db):
        from src.portfolio.validation import ProductionValidator

        conn, cur = self._make_cursor()
        mock_db.return_value = conn

        pb = MagicMock()
        pb.current_version = 0
        mock_playbook.return_value = pb

        cur.fetchone.side_effect = [
            {"count": 0},
            {"sharpe_ratio": 0},
            {"count": 0},
            {"count": 0},
            {"worst_drawdown": 0},
            {"total": 0, "wins": 0},
            None,  # No index tier data
            {"count": 0},
        ]

        validator = ProductionValidator()
        report = validator.validate_detailed()

        idx_result = next(r for r in report.results if r.name == "index_tracking_error")
        assert idx_result.passed is False
        assert "No index tier data" in idx_result.message

    def test_validation_report_progress(self):
        from src.portfolio.validation import ValidationReport, ValidationResult

        report = ValidationReport(
            results=[
                ValidationResult(name="a", passed=True, message="ok"),
                ValidationResult(name="b", passed=False, message="fail"),
                ValidationResult(name="c", passed=True, message="ok"),
            ],
            passed_count=2,
            total_count=3,
            failures=["fail"],
        )

        assert report.progress_pct == 2 / 3 * 100
        assert report.is_ready is False

    def test_custom_criteria(self):
        from src.portfolio.validation import ProductionValidator

        custom = {"min_trades": 100, "min_sharpe": 0.1}
        validator = ProductionValidator(criteria=custom)
        assert validator.criteria["min_trades"] == 100


# ═══════════════════════════════════════════════════════════════
# 12.3: GoLiveChecklist
# ═══════════════════════════════════════════════════════════════


class TestGoLiveChecklist:
    @patch.dict(
        "os.environ",
        {
            "DATABASE_URL": "postgresql://...",
            "REDIS_URL": "redis://...",
            "TZ": "Europe/Berlin",
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID": "123",
            "DEEPSEEK_API_KEY": "key",
            "PAPER_TRADING": "true",
            "BINANCE_TESTNET": "true",
            "PORTFOLIO_MANAGER": "true",
        },
    )
    def test_paper_phase_checks(self):
        from src.portfolio.go_live import DeploymentPhase, GoLiveChecklist

        checklist = GoLiveChecklist(target_phase=DeploymentPhase.PAPER)
        report = checklist.check()

        # Environment checks should pass
        env_checks = [c for c in report.checks if c.category == "environment"]
        assert all(c.passed for c in env_checks)

        # Paper mode should pass
        flag_checks = [c for c in report.checks if c.name == "paper_mode"]
        assert all(c.passed for c in flag_checks)

    @patch.dict(
        "os.environ",
        {
            "DATABASE_URL": "",
            "REDIS_URL": "",
            "TZ": "",
            "PAPER_TRADING": "true",
            "BINANCE_TESTNET": "true",
            "PORTFOLIO_MANAGER": "false",
        },
    )
    def test_missing_env_vars(self):
        from src.portfolio.go_live import DeploymentPhase, GoLiveChecklist

        checklist = GoLiveChecklist(target_phase=DeploymentPhase.PAPER)
        report = checklist.check()

        db_check = next(c for c in report.checks if c.name == "database_url")
        assert db_check.passed is False

    @patch.dict(
        "os.environ",
        {
            "DATABASE_URL": "postgresql://...",
            "REDIS_URL": "redis://...",
            "TZ": "Europe/Berlin",
            "BINANCE_API_KEY": "key",
            "BINANCE_API_SECRET": "secret",
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID": "123",
            "DEEPSEEK_API_KEY": "key",
            "PAPER_TRADING": "false",
            "BINANCE_TESTNET": "false",
            "PORTFOLIO_MANAGER": "true",
        },
    )
    @patch("src.tasks.base.get_db_connection")
    @patch("src.portfolio.validation.get_db_connection")
    @patch("src.data.playbook.get_playbook")
    def test_alpha_phase_checks(self, mock_playbook, mock_val_db, mock_gl_db):
        from src.portfolio.go_live import DeploymentPhase, GoLiveChecklist

        # Mock validation DB
        conn_val = MagicMock()
        cur_val = MagicMock()
        conn_val.cursor.return_value.__enter__ = MagicMock(return_value=cur_val)
        conn_val.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur_val.fetchone.return_value = {
            "count": 0,
            "sharpe_ratio": 0,
            "worst_drawdown": 0,
            "total": 0,
            "wins": 0,
            "target_pct": 65,
            "current_pct": None,
        }
        mock_val_db.return_value = conn_val

        pb = MagicMock()
        pb.current_version = 0
        mock_playbook.return_value = pb

        # Mock go-live DB
        conn_gl = MagicMock()
        cur_gl = MagicMock()
        conn_gl.cursor.return_value.__enter__ = MagicMock(return_value=cur_gl)
        conn_gl.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur_gl.fetchone.side_effect = [
            {"total": 500},  # capital check
            {"count": 2},  # cohort count
        ]
        mock_gl_db.return_value = conn_gl

        checklist = GoLiveChecklist(target_phase=DeploymentPhase.ALPHA)
        report = checklist.check()

        # Live mode flag should pass
        live_check = next(c for c in report.checks if c.name == "live_mode")
        assert live_check.passed is True

        # Capital within limit
        cap_check = next(c for c in report.checks if c.name == "capital_within_limit")
        assert cap_check.passed is True

    @patch.dict(
        "os.environ",
        {
            "PAPER_TRADING": "true",
            "BINANCE_TESTNET": "true",
        },
    )
    def test_detect_paper_phase(self):
        from src.portfolio.go_live import DeploymentPhase, GoLiveChecklist

        checklist = GoLiveChecklist()
        phase = checklist.detect_current_phase()
        assert phase == DeploymentPhase.PAPER

    @patch.dict(
        "os.environ",
        {
            "PAPER_TRADING": "false",
            "BINANCE_TESTNET": "true",
        },
    )
    def test_detect_testnet_as_paper(self):
        from src.portfolio.go_live import DeploymentPhase, GoLiveChecklist

        checklist = GoLiveChecklist()
        phase = checklist.detect_current_phase()
        assert phase == DeploymentPhase.PAPER


class TestDeploymentPhase:
    def test_phase_config_exists(self):
        from src.portfolio.go_live import PHASE_CONFIG, DeploymentPhase

        for phase in DeploymentPhase:
            assert phase in PHASE_CONFIG
            assert "max_capital_usd" in PHASE_CONFIG[phase]
            assert "max_cohorts" in PHASE_CONFIG[phase]

    def test_phase_capital_scaling(self):
        from src.portfolio.go_live import PHASE_CONFIG, DeploymentPhase

        # Capital should increase through phases
        assert (
            PHASE_CONFIG[DeploymentPhase.ALPHA]["max_capital_usd"]
            < PHASE_CONFIG[DeploymentPhase.BETA]["max_capital_usd"]
            < PHASE_CONFIG[DeploymentPhase.PRODUCTION]["max_capital_usd"]
        )

    def test_paper_no_validation_required(self):
        from src.portfolio.go_live import PHASE_CONFIG, DeploymentPhase

        assert PHASE_CONFIG[DeploymentPhase.PAPER]["requires_validation"] is False

    def test_live_phases_require_validation(self):
        from src.portfolio.go_live import PHASE_CONFIG, DeploymentPhase

        for phase in [DeploymentPhase.ALPHA, DeploymentPhase.BETA, DeploymentPhase.PRODUCTION]:
            assert PHASE_CONFIG[phase]["requires_validation"] is True


# ═══════════════════════════════════════════════════════════════
# Go-Live Report
# ═══════════════════════════════════════════════════════════════


class TestGoLiveReport:
    def test_report_properties(self):
        from src.portfolio.go_live import CheckItem, DeploymentPhase, GoLiveReport

        report = GoLiveReport(
            phase=DeploymentPhase.ALPHA,
            checks=[
                CheckItem(name="a", passed=True, message="ok"),
                CheckItem(name="b", passed=False, message="fail"),
            ],
        )

        assert report.passed_count == 1
        assert report.total_count == 2
        assert report.is_ready is False
        assert report.failures == ["fail"]

    def test_all_passed(self):
        from src.portfolio.go_live import CheckItem, DeploymentPhase, GoLiveReport

        report = GoLiveReport(
            phase=DeploymentPhase.PAPER,
            checks=[
                CheckItem(name="a", passed=True, message="ok"),
                CheckItem(name="b", passed=True, message="ok"),
            ],
        )

        assert report.is_ready is True
        assert report.failures == []
