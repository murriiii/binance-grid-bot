"""Tests for remaining 0% modules: logging_system, ai_enhanced, portfolio models, backtest."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.api.http_client import HTTPClientError

# ═══════════════════════════════════════════════════════════════
# logging_system.py
# ═══════════════════════════════════════════════════════════════


class TestTradingLogger:
    @pytest.fixture()
    def logger(self):
        from src.core.logging_system import TradingLogger

        return TradingLogger()

    def test_error(self, logger):
        logger.error("Test error", Exception("boom"), {"key": "value"})

    def test_critical(self, logger):
        logger.critical("Critical error", Exception("boom"))

    def test_trade_executed(self, logger):
        logger.trade_executed("BTCUSDT", "BUY", 0.01, 65000.0, "ORD123")

    def test_trade_failed(self, logger):
        logger.trade_failed("BTCUSDT", "BUY", 0.01, "Insufficient balance")

    def test_order_filled(self, logger):
        logger.order_filled("ORD123", "BTCUSDT", "BUY", 0.01, 65000.0, grid_level=3)

    def test_ai_decision(self, logger):
        logger.ai_decision(
            symbol="BTCUSDT",
            direction="LONG",
            action="BUY",
            confidence=0.85,
            reasoning="RSI oversold",
        )

    def test_math_signal(self, logger):
        logger.math_signal("BTCUSDT", "BUY", {"rsi": 28, "macd": "bullish"})

    def test_decision_override(self, logger):
        logger.decision_override("BUY", "HOLD", "Market too volatile", "risk_guard")

    def test_daily_performance(self, logger):
        logger.daily_performance(
            portfolio_value=10000.0,
            daily_pnl=150.0,
            daily_pnl_pct=1.5,
            trades_count=5,
            win_rate=60.0,
            fear_greed=45,
        )

    def test_weekly_performance(self, logger):
        logger.weekly_performance(
            portfolio_value=10000.0,
            weekly_pnl=500.0,
            weekly_pnl_pct=5.0,
            total_trades=20,
            winning_trades=13,
            losing_trades=7,
        )

    def test_drawdown_alert(self, logger):
        logger.drawdown_alert(
            current_drawdown=8.5,
            max_allowed=10.0,
            portfolio_value=9150.0,
            peak_value=10000.0,
        )

    def test_system_start(self, logger):
        logger.system_start({"mode": "grid", "symbol": "BTCUSDT"})

    def test_system_stop(self, logger):
        logger.system_stop("Scheduled maintenance")

    def test_system_health(self, logger):
        logger.system_health(
            status="healthy",
            api_status="healthy",
            db_status="healthy",
            memory_usage_mb=512.0,
        )

    def test_playbook_updated(self, logger):
        logger.playbook_updated(
            version=3,
            changes=["New rule added"],
            patterns_found=5,
            anti_patterns_found=2,
        )

    def test_playbook_rule_triggered(self, logger):
        logger.playbook_rule_triggered(
            rule_name="fear_greed_extreme",
            rule_type="entry",
            market_conditions={"fear_greed": 15},
            action_taken="BUY",
        )

    def test_pattern_learned(self, logger):
        logger.pattern_learned(
            pattern_type="fear_greed_reversal",
            pattern_description="Buy when F&G < 20",
            sample_size=50,
            success_rate=72.0,
        )

    def test_api_call(self, logger):
        logger.api_call("binance", "/api/v3/ticker/price", "success", response_time_ms=45.0)

    def test_api_rate_limit(self, logger):
        logger.api_rate_limit("binance", retry_after=30.0)

    def test_get_log_files(self, logger):
        files = logger.get_log_files()
        assert isinstance(files, dict)

    def test_get_recent_errors(self, logger):
        errors = logger.get_recent_errors(limit=10)
        assert isinstance(errors, list)

    def test_get_analysis_summary(self, logger):
        summary = logger.get_analysis_summary()
        assert isinstance(summary, dict)


class TestLoggingModuleFunctions:
    def test_get_logger(self):
        from src.core.logging_system import get_logger

        logger = get_logger()
        assert logger is not None

        logger2 = get_logger()
        assert logger is logger2  # Singleton

    def test_log_error(self):
        from src.core.logging_system import log_error

        log_error("Test error message")

    def test_log_trade(self):
        from src.core.logging_system import log_trade

        log_trade("BTCUSDT", "BUY", 0.01, 65000.0, "ORD123")

    def test_log_decision(self):
        from src.core.logging_system import log_decision

        log_decision("BTCUSDT", "LONG", "BUY", 0.85, "RSI oversold")


# ═══════════════════════════════════════════════════════════════
# ai_enhanced.py
# ═══════════════════════════════════════════════════════════════


class TestAITradingEnhancer:
    @patch("src.strategies.ai_enhanced.get_http_client")
    def test_analyze_news(self, mock_http):
        from src.strategies.ai_enhanced import AITradingEnhancer

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"direction": "BULLISH", "confidence": 0.7, '
                        '"reasoning": "Positive news", "action": "HOLD", '
                        '"affected_assets": ["BTC"], "risk_level": "LOW"}'
                    }
                }
            ]
        }
        mock_http.return_value = mock_client

        enhancer = AITradingEnhancer()
        result = enhancer.analyze_news([{"title": "BTC ETF approved", "summary": "Great news"}])
        assert result is not None
        assert result.direction == "BULLISH"

    @patch("src.strategies.ai_enhanced.get_http_client")
    def test_analyze_news_api_error(self, mock_http):
        from src.strategies.ai_enhanced import AITradingEnhancer

        mock_client = MagicMock()
        mock_client.post.side_effect = HTTPClientError("API error")
        mock_http.return_value = mock_client

        enhancer = AITradingEnhancer()
        result = enhancer.analyze_news([{"title": "test"}])
        # Should fall back to NEUTRAL via _get_fallback_response → _parse_signal
        assert result.direction == "NEUTRAL"

    def test_is_api_healthy_default(self):
        from src.strategies.ai_enhanced import AITradingEnhancer

        enhancer = AITradingEnhancer()
        # Default: no errors, so healthy
        assert enhancer.is_api_healthy() is True

    def test_is_api_healthy_after_errors(self):
        from src.strategies.ai_enhanced import AITradingEnhancer

        enhancer = AITradingEnhancer()
        enhancer.consecutive_errors = 3
        assert enhancer.is_api_healthy() is False

    @patch("src.strategies.ai_enhanced.get_http_client")
    def test_call_api_no_key(self, mock_http):
        from src.strategies.ai_enhanced import AITradingEnhancer

        enhancer = AITradingEnhancer()
        enhancer.api_key = None
        result = enhancer._call_api("test prompt")
        assert "Fallback" in result


class TestHybridStrategy:
    def test_make_decision_no_ai(self):
        from src.strategies.ai_enhanced import HybridStrategy

        strategy = HybridStrategy(use_ai=False)
        result = strategy.make_decision(
            math_recommendation={"action": "BUY", "confidence": 0.8, "reasoning": "RSI low"},
            market_data={"fear_greed": 30, "btc_price": 65000},
        )

        assert result["final_action"] == "BUY"
        assert result["ai_enhanced"] is False

    @patch("src.strategies.ai_enhanced.get_http_client")
    def test_make_decision_with_ai(self, mock_http):
        from src.strategies.ai_enhanced import HybridStrategy

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"direction": "BULLISH", "confidence": 0.9, '
                        '"reasoning": "Confirmed", "action": "BUY", '
                        '"affected_assets": ["BTC"], "risk_level": "LOW"}'
                    }
                }
            ]
        }
        mock_http.return_value = mock_client

        strategy = HybridStrategy(use_ai=True)

        result = strategy.make_decision(
            math_recommendation={"action": "BUY", "confidence": 0.8, "reasoning": "RSI low"},
            market_data={"fear_greed": 20, "btc_price": 65000},
        )

        assert result["ai_enhanced"] is True
        assert "final_action" in result


# ═══════════════════════════════════════════════════════════════
# models/portfolio.py
# ═══════════════════════════════════════════════════════════════


class TestPortfolioOptimizer:
    def test_load_returns_and_optimize(self):
        from src.models.portfolio import PortfolioOptimizer

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 100).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 100).cumsum(),
                "SOL": 100 + rng.normal(0, 5, 100).cumsum(),
            },
            index=dates,
        )

        optimizer = PortfolioOptimizer()
        optimizer.load_returns(prices)

        assert optimizer.mean_returns is not None
        assert optimizer.cov_matrix is not None

    def test_optimize_sharpe(self):
        from src.models.portfolio import PortfolioOptimizer

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 100).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 100).cumsum(),
            },
            index=dates,
        )

        optimizer = PortfolioOptimizer()
        optimizer.load_returns(prices)
        weights = optimizer.optimize_sharpe()

        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_optimize_min_variance(self):
        from src.models.portfolio import PortfolioOptimizer

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 100).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 100).cumsum(),
            },
            index=dates,
        )

        optimizer = PortfolioOptimizer()
        optimizer.load_returns(prices)
        weights = optimizer.optimize_min_variance()

        assert isinstance(weights, dict)

    def test_efficient_frontier(self):
        from src.models.portfolio import PortfolioOptimizer

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 100).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 100).cumsum(),
            },
            index=dates,
        )

        optimizer = PortfolioOptimizer()
        optimizer.load_returns(prices)
        frontier = optimizer.efficient_frontier(n_points=10)

        assert isinstance(frontier, list)
        assert len(frontier) > 0

    def test_portfolio_return_and_volatility(self):
        from src.models.portfolio import PortfolioOptimizer

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 100).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 100).cumsum(),
            },
            index=dates,
        )

        optimizer = PortfolioOptimizer()
        optimizer.load_returns(prices)

        weights = np.array([0.6, 0.4])
        ret = optimizer.portfolio_return(weights)
        vol = optimizer.portfolio_volatility(weights)
        sharpe = optimizer.sharpe_ratio(weights)

        assert isinstance(ret, float)
        assert isinstance(vol, float)
        assert isinstance(sharpe, float)


class TestKellyCriterion:
    def test_optimal_fraction(self):
        from src.models.portfolio import KellyCriterion

        fraction = KellyCriterion.optimal_fraction(win_rate=0.6, win_loss_ratio=1.5)
        assert fraction > 0
        assert fraction < 1

    def test_optimal_fraction_losing(self):
        from src.models.portfolio import KellyCriterion

        fraction = KellyCriterion.optimal_fraction(win_rate=0.3, win_loss_ratio=0.8)
        assert fraction >= 0


class TestRiskScaler:
    def test_small_portfolio(self):
        from src.models.portfolio import RiskScaler

        scaler = RiskScaler()
        alloc = scaler.get_altcoin_allocation(500.0)

        assert 0 <= alloc <= 100

    def test_large_portfolio(self):
        from src.models.portfolio import RiskScaler

        scaler = RiskScaler()
        alloc = scaler.get_altcoin_allocation(50000.0)

        assert 0 <= alloc <= 100

    def test_reasoning(self):
        from src.models.portfolio import RiskScaler

        scaler = RiskScaler()
        reasoning = scaler.get_allocation_reasoning(5000.0)

        assert isinstance(reasoning, str)


# ═══════════════════════════════════════════════════════════════
# backtest/engine.py
# ═══════════════════════════════════════════════════════════════


class TestBacktestEngine:
    def test_init_and_reset(self):
        from src.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000.0)
        assert engine.cash == 10000.0
        engine.reset()
        assert engine.cash == 10000.0

    def test_execute_buy(self):
        from src.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.001, slippage=0.0)
        trade = engine.execute_buy(
            timestamp=datetime.now(),
            symbol="BTC",
            amount_usd=1000.0,
            price=65000.0,
            reasoning="Test buy",
        )

        assert trade is not None
        assert trade.trade_type.value == "BUY"
        assert engine.cash < 10000.0

    def test_execute_sell(self):
        from src.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.001, slippage=0.0)
        engine.execute_buy(
            timestamp=datetime.now(),
            symbol="BTC",
            amount_usd=1000.0,
            price=65000.0,
            reasoning="Buy",
        )

        qty = engine.positions.get("BTC", 0)
        trade = engine.execute_sell(
            timestamp=datetime.now(),
            symbol="BTC",
            quantity=qty,
            price=66000.0,
            reasoning="Test sell",
        )

        assert trade is not None

    def test_get_portfolio_value(self):
        from src.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000.0)
        engine.execute_buy(
            timestamp=datetime.now(),
            symbol="BTC",
            amount_usd=5000.0,
            price=65000.0,
            reasoning="Buy",
        )

        value = engine.get_portfolio_value({"BTC": 66000.0})
        assert value > 0

    def test_run_backtest(self):
        from src.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.001, slippage=0.0)

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        price_data = pd.DataFrame({"BTC": 60000 + rng.normal(0, 500, 50).cumsum()}, index=dates)

        def simple_strategy(engine, timestamp, prices, **kwargs):
            if len(engine.trades) == 0:
                engine.execute_buy(timestamp, "BTC", 5000, prices["BTC"], "Initial buy")

        result = engine.run(price_data, simple_strategy)
        assert result is not None
        assert result.initial_value == 10000.0
        assert result.total_trades >= 1


# ═══════════════════════════════════════════════════════════════
# strategies/portfolio_rebalance.py
# ═══════════════════════════════════════════════════════════════


class TestPortfolioRebalanceStrategy:
    def test_get_rebalance_trades(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        strategy = PortfolioRebalanceStrategy()
        trades = strategy.get_rebalance_trades(
            current_positions={"BTC": 0.1, "ETH": 2.0},
            target_weights={"BTC": 0.6, "ETH": 0.4},
            prices={"BTC": 65000, "ETH": 3000},
            portfolio_value=12500,
        )

        assert isinstance(trades, list)

    def test_calculate_target_weights(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 50).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 50).cumsum(),
            },
            index=dates,
        )

        strategy = PortfolioRebalanceStrategy()
        weights, reasoning = strategy.calculate_target_weights(
            price_history=prices,
            portfolio_value=10000.0,
            available_coins=["BTC", "ETH"],
        )

        assert isinstance(weights, dict)
        assert isinstance(reasoning, str)

    def test_calculate_target_weights_with_altcoins(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        prices = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 50).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 50).cumsum(),
                "SOL": 100 + rng.normal(0, 5, 50).cumsum(),
                "AVAX": 30 + rng.normal(0, 2, 50).cumsum(),
            },
            index=dates,
        )

        strategy = PortfolioRebalanceStrategy(lookback_days=30)
        weights, _reasoning = strategy.calculate_target_weights(
            price_history=prices,
            portfolio_value=10000.0,
            available_coins=["BTC", "ETH", "SOL", "AVAX"],
        )

        assert "BTC" in weights
        assert "SOL" in weights
        assert sum(weights.values()) > 0

    def test_calculate_target_weights_fallback(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        # Not enough history for lookback
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        prices = pd.DataFrame(
            {"SOL": [100, 101, 102, 103, 104]},
            index=dates,
        )

        strategy = PortfolioRebalanceStrategy(lookback_days=30)
        _weights, reasoning = strategy.calculate_target_weights(
            price_history=prices,
            portfolio_value=10000.0,
            available_coins=["SOL"],
        )
        assert "Gleichverteilung" in reasoning

    def test_get_rebalance_trades_buy_and_sell(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        strategy = PortfolioRebalanceStrategy(rebalance_threshold=0.03)
        trades = strategy.get_rebalance_trades(
            current_positions={"BTC": 0.1, "ETH": 5.0},
            target_weights={"BTC": 0.7, "ETH": 0.3},
            prices={"BTC": 65000.0, "ETH": 3000.0},
            portfolio_value=21500.0,
        )

        assert any(t["action"] == "BUY" for t in trades) or any(
            t["action"] == "SELL" for t in trades
        )

    def test_get_rebalance_trades_no_drift(self):
        from src.strategies.portfolio_rebalance import PortfolioRebalanceStrategy

        strategy = PortfolioRebalanceStrategy(rebalance_threshold=0.10)
        trades = strategy.get_rebalance_trades(
            current_positions={"BTC": 0.01},
            target_weights={"BTC": 0.65},
            prices={"BTC": 65000.0},
            portfolio_value=1000.0,
        )
        # Within threshold, no trades needed
        assert len(trades) == 0


class TestPortfolioRebalanceFunction:
    def test_initial_allocation(self):
        from src.strategies.portfolio_rebalance import portfolio_rebalance_strategy

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        price_history = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 50).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 50).cumsum(),
            },
            index=dates,
        )

        engine = MagicMock()
        engine.positions = {}
        engine.cash = 10000.0

        portfolio_rebalance_strategy(
            engine=engine,
            timestamp=dates[-1],
            prices={"BTC": 65000.0, "ETH": 3500.0},
            price_history=price_history,
        )

        # Should have called execute_buy for initial allocation
        assert engine.execute_buy.call_count >= 1

    def test_rebalance_too_soon(self):
        from src.strategies.portfolio_rebalance import (
            PortfolioRebalanceStrategy,
            portfolio_rebalance_strategy,
        )

        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        price_history = pd.DataFrame(
            {"BTC": np.linspace(60000, 65000, 50)},
            index=dates,
        )

        engine = MagicMock()
        engine.positions = {"BTC": 0.1}
        engine.cash = 5000.0
        engine.get_portfolio_value.return_value = 11500.0

        # Pre-create strategy with recent rebalance
        strategy = PortfolioRebalanceStrategy()
        strategy.last_rebalance = dates[28]

        kwargs = {"_strategy_instance": strategy}
        portfolio_rebalance_strategy(
            engine=engine,
            timestamp=dates[30],
            prices={"BTC": 62000.0},
            price_history=price_history,
            rebalance_interval_days=7,
            **kwargs,
        )
        # Should not rebalance (only 2 days since last)
        engine.execute_buy.assert_not_called()
        engine.execute_sell.assert_not_called()

    def test_rebalance_executes(self):
        from src.strategies.portfolio_rebalance import portfolio_rebalance_strategy

        rng = np.random.default_rng(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        price_history = pd.DataFrame(
            {
                "BTC": 60000 + rng.normal(0, 500, 50).cumsum(),
                "ETH": 3000 + rng.normal(0, 50, 50).cumsum(),
            },
            index=dates,
        )

        engine = MagicMock()
        engine.positions = {"BTC": 0.1}
        engine.cash = 5000.0
        engine.get_portfolio_value.return_value = 11500.0

        kwargs = {}
        # Call with no last_rebalance (will trigger rebalance)
        portfolio_rebalance_strategy(
            engine=engine,
            timestamp=dates[-1],
            prices={"BTC": 65000.0, "ETH": 3500.0},
            price_history=price_history,
            **kwargs,
        )
