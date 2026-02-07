"""Go-Live Checklist and Deployment Phase Management.

Manages gradual transition from paper trading to live:
  Paper → Alpha ($1K) → Beta ($3K) → Production ($5K+)

Each phase has specific requirements and capital limits.
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("trading_bot")


class DeploymentPhase(Enum):
    """Deployment phases for gradual capital scaling."""

    PAPER = "paper"
    ALPHA = "alpha"
    BETA = "beta"
    PRODUCTION = "production"


# Phase configurations
PHASE_CONFIG = {
    DeploymentPhase.PAPER: {
        "max_capital_usd": 10_000,  # Virtual
        "max_cohorts": 6,
        "description": "Paper trading with virtual capital",
        "requires_validation": False,
    },
    DeploymentPhase.ALPHA: {
        "max_capital_usd": 1_000,
        "max_cohorts": 2,
        "description": "Initial live trading with minimal capital",
        "requires_validation": True,
    },
    DeploymentPhase.BETA: {
        "max_capital_usd": 3_000,
        "max_cohorts": 4,
        "description": "Expanded live trading",
        "requires_validation": True,
    },
    DeploymentPhase.PRODUCTION: {
        "max_capital_usd": 100_000,
        "max_cohorts": 6,
        "description": "Full production deployment",
        "requires_validation": True,
    },
}


@dataclass
class CheckItem:
    """A single go-live checklist item."""

    name: str
    passed: bool
    message: str
    category: str = "general"


@dataclass
class GoLiveReport:
    """Full go-live checklist report."""

    phase: DeploymentPhase
    checks: list[CheckItem] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)

    @property
    def is_ready(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[str]:
        return [c.message for c in self.checks if not c.passed]


class GoLiveChecklist:
    """Validates environment and system state for go-live.

    Checks API keys, feature flags, validation status,
    and deployment phase constraints.
    """

    def __init__(self, target_phase: DeploymentPhase = DeploymentPhase.ALPHA):
        self.target_phase = target_phase

    def detect_current_phase(self) -> DeploymentPhase:
        """Detect current deployment phase from environment."""
        paper = os.getenv("PAPER_TRADING", "false").lower() == "true"
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if paper:
            return DeploymentPhase.PAPER
        if testnet:
            return DeploymentPhase.PAPER  # Testnet = still paper

        # Live mode — determine phase from capital
        portfolio_mgr = os.getenv("PORTFOLIO_MANAGER", "false").lower() == "true"
        if not portfolio_mgr:
            return DeploymentPhase.ALPHA

        from src.tasks.base import get_db_connection

        conn = get_db_connection()
        if not conn:
            return DeploymentPhase.ALPHA

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(current_value_usd), 0) as total "
                    "FROM portfolio_tiers WHERE is_active = TRUE"
                )
                row = cur.fetchone()
                total = float(row["total"]) if row else 0
        except Exception:
            total = 0
        finally:
            conn.close()

        if total > PHASE_CONFIG[DeploymentPhase.BETA]["max_capital_usd"]:
            return DeploymentPhase.PRODUCTION
        if total > PHASE_CONFIG[DeploymentPhase.ALPHA]["max_capital_usd"]:
            return DeploymentPhase.BETA
        return DeploymentPhase.ALPHA

    def check(self) -> GoLiveReport:
        """Run all go-live checks for the target phase."""
        report = GoLiveReport(phase=self.target_phase)

        # Environment checks
        report.checks.extend(self._check_environment())

        # API keys
        report.checks.extend(self._check_api_keys())

        # Feature flags
        report.checks.extend(self._check_feature_flags())

        # Production validation (if required)
        config = PHASE_CONFIG[self.target_phase]
        if config["requires_validation"]:
            report.checks.extend(self._check_production_validation())

        # Capital limits
        report.checks.extend(self._check_capital_limits())

        return report

    def _check_environment(self) -> list[CheckItem]:
        """Check environment configuration."""
        checks = []

        # Database
        db_url = os.getenv("DATABASE_URL", "")
        checks.append(
            CheckItem(
                name="database_url",
                passed=bool(db_url),
                message="DATABASE_URL configured" if db_url else "DATABASE_URL not set",
                category="environment",
            )
        )

        # Redis
        redis_url = os.getenv("REDIS_URL", "")
        checks.append(
            CheckItem(
                name="redis_url",
                passed=bool(redis_url),
                message="REDIS_URL configured" if redis_url else "REDIS_URL not set",
                category="environment",
            )
        )

        # Timezone
        tz = os.getenv("TZ", "")
        checks.append(
            CheckItem(
                name="timezone",
                passed=bool(tz),
                message=f"Timezone: {tz}" if tz else "TZ not set",
                category="environment",
            )
        )

        return checks

    def _check_api_keys(self) -> list[CheckItem]:
        """Check required API keys are present."""
        checks = []

        # Binance — for live, need prod keys (not testnet)
        if self.target_phase != DeploymentPhase.PAPER:
            api_key = os.getenv("BINANCE_API_KEY", "")
            api_secret = os.getenv("BINANCE_API_SECRET", "")
            checks.append(
                CheckItem(
                    name="binance_api_key",
                    passed=bool(api_key and api_secret),
                    message="Binance API keys configured"
                    if api_key and api_secret
                    else "Binance production API keys missing",
                    category="api_keys",
                )
            )

        # Telegram
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        checks.append(
            CheckItem(
                name="telegram",
                passed=bool(tg_token and tg_chat),
                message="Telegram configured"
                if tg_token and tg_chat
                else "Telegram token/chat_id missing",
                category="api_keys",
            )
        )

        # DeepSeek
        ds_key = os.getenv("DEEPSEEK_API_KEY", "")
        checks.append(
            CheckItem(
                name="deepseek",
                passed=bool(ds_key),
                message="DeepSeek API key configured" if ds_key else "DeepSeek API key missing",
                category="api_keys",
            )
        )

        return checks

    def _check_feature_flags(self) -> list[CheckItem]:
        """Check feature flags are set correctly for target phase."""
        checks = []

        paper = os.getenv("PAPER_TRADING", "false").lower() == "true"
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        portfolio = os.getenv("PORTFOLIO_MANAGER", "false").lower() == "true"

        if self.target_phase == DeploymentPhase.PAPER:
            checks.append(
                CheckItem(
                    name="paper_mode",
                    passed=paper or testnet,
                    message="Paper/testnet mode active"
                    if paper or testnet
                    else "WARNING: Not in paper/testnet mode!",
                    category="flags",
                )
            )
        else:
            checks.append(
                CheckItem(
                    name="live_mode",
                    passed=not paper and not testnet,
                    message="Live mode active (paper=false, testnet=false)"
                    if not paper and not testnet
                    else f"Still in {'paper' if paper else 'testnet'} mode",
                    category="flags",
                )
            )

        checks.append(
            CheckItem(
                name="portfolio_manager",
                passed=portfolio,
                message="PORTFOLIO_MANAGER=true" if portfolio else "PORTFOLIO_MANAGER not enabled",
                category="flags",
            )
        )

        return checks

    def _check_production_validation(self) -> list[CheckItem]:
        """Run ProductionValidator and include results."""
        checks = []

        try:
            from src.portfolio.validation import ProductionValidator

            validator = ProductionValidator()
            report = validator.validate_detailed()

            checks.append(
                CheckItem(
                    name="production_validation",
                    passed=report.is_ready,
                    message=f"Production validation: {report.passed_count}/{report.total_count} "
                    f"({'READY' if report.is_ready else 'NOT READY'})",
                    category="validation",
                )
            )

            if not report.is_ready:
                for failure in report.failures[:3]:
                    checks.append(
                        CheckItem(
                            name="validation_detail",
                            passed=False,
                            message=f"  → {failure}",
                            category="validation",
                        )
                    )

        except Exception as e:
            checks.append(
                CheckItem(
                    name="production_validation",
                    passed=False,
                    message=f"Validation error: {e}",
                    category="validation",
                )
            )

        return checks

    def _check_capital_limits(self) -> list[CheckItem]:
        """Verify capital doesn't exceed phase limits."""
        checks = []
        config = PHASE_CONFIG[self.target_phase]
        max_capital = config["max_capital_usd"]
        max_cohorts = config["max_cohorts"]

        from src.tasks.base import get_db_connection

        conn = get_db_connection()
        if not conn:
            checks.append(
                CheckItem(
                    name="capital_check",
                    passed=False,
                    message="Cannot check capital (no DB connection)",
                    category="capital",
                )
            )
            return checks

        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total portfolio value
                cur.execute(
                    "SELECT COALESCE(SUM(current_value_usd), 0) as total "
                    "FROM portfolio_tiers WHERE is_active = TRUE"
                )
                row = cur.fetchone()
                total = float(row["total"]) if row else 0

                checks.append(
                    CheckItem(
                        name="capital_within_limit",
                        passed=total <= max_capital,
                        message=f"Capital: ${total:,.0f} (max ${max_capital:,.0f})"
                        if total <= max_capital
                        else f"Capital ${total:,.0f} exceeds phase limit ${max_capital:,.0f}",
                        category="capital",
                    )
                )

                # Active cohort count
                cur.execute("SELECT COUNT(*) as count FROM cohorts WHERE is_active = TRUE")
                row = cur.fetchone()
                cohorts = row["count"] if row else 0

                checks.append(
                    CheckItem(
                        name="cohorts_within_limit",
                        passed=cohorts <= max_cohorts,
                        message=f"Cohorts: {cohorts} (max {max_cohorts})"
                        if cohorts <= max_cohorts
                        else f"Cohorts {cohorts} exceeds phase limit {max_cohorts}",
                        category="capital",
                    )
                )

        except Exception as e:
            checks.append(
                CheckItem(
                    name="capital_check",
                    passed=False,
                    message=f"Capital check error: {e}",
                    category="capital",
                )
            )
        finally:
            conn.close()

        return checks
