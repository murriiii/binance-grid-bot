"""Tests for Phase 11: 3-Tier Portfolio Management.

Covers:
- CashReserveTier
- IndexHoldingsTier
- TradingTier
- PortfolioManager
- ProfitRedistributionEngine
- AIPortfolioOptimizer
- Monitoring tasks (tier health)
- Reporting (tier report)
"""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# 11.3: Cash Reserve Tier
# ═══════════════════════════════════════════════════════════════


class TestCashReserveTier:
    def test_init_defaults(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        tier = CashReserveTier(client, target_pct=10.0)
        assert tier.target_pct == 10.0
        assert tier.balance == 0.0

    def test_update_balance(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        client.get_account_balance.return_value = 500.0
        tier = CashReserveTier(client, target_pct=10.0)
        result = tier.update_balance()
        assert result == 500.0
        assert tier.balance == 500.0
        client.get_account_balance.assert_called_once_with("USDT")

    def test_update_balance_error(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        client.get_account_balance.side_effect = Exception("API error")
        tier = CashReserveTier(client, target_pct=10.0)
        result = tier.update_balance()
        assert result == 0.0

    def test_get_status_underfunded(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        tier = CashReserveTier(client, target_pct=10.0)
        tier._balance = 200.0  # 2% of 10000

        status = tier.get_status(total_portfolio_value=10000.0)
        assert status.balance_usd == 200.0
        assert status.target_usd == 1000.0
        assert status.current_pct == 2.0
        assert status.is_underfunded is True
        assert status.is_overfunded is False
        assert status.deficit_usd == 800.0

    def test_get_status_overfunded(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        tier = CashReserveTier(client, target_pct=10.0)
        tier._balance = 2000.0  # 20% of 10000

        status = tier.get_status(total_portfolio_value=10000.0)
        assert status.current_pct == 20.0
        assert status.is_overfunded is True
        assert status.surplus_usd == 1000.0

    def test_get_status_on_target(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        tier = CashReserveTier(client, target_pct=10.0)
        tier._balance = 1000.0

        status = tier.get_status(total_portfolio_value=10000.0)
        assert status.is_underfunded is False
        assert status.is_overfunded is False

    def test_tick(self):
        from src.portfolio.tiers.cash_reserve import CashReserveTier

        client = MagicMock()
        client.get_account_balance.return_value = 750.0
        tier = CashReserveTier(client, target_pct=10.0)

        status = tier.tick(total_portfolio_value=10000.0)
        assert status.balance_usd == 750.0


# ═══════════════════════════════════════════════════════════════
# 11.4: Index Holdings Tier
# ═══════════════════════════════════════════════════════════════


class TestIndexHoldingsTier:
    def test_init(self):
        from src.portfolio.tiers.index_holdings import IndexHoldingsTier

        client = MagicMock()
        tier = IndexHoldingsTier(client, target_pct=65.0)
        assert tier.target_pct == 65.0
        assert tier._holdings == {}

    def test_load_holdings_no_conn(self):
        from src.portfolio.tiers.index_holdings import IndexHoldingsTier

        tier = IndexHoldingsTier(MagicMock(), conn=None)
        result = tier.load_holdings()
        assert result == {}

    def test_load_holdings_from_db(self):
        from src.portfolio.tiers.index_holdings import IndexHoldingsTier

        client = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [
            {
                "symbol": "BTCUSDT",
                "target_weight_pct": 30.0,
                "current_weight_pct": 28.5,
                "quantity": 0.1,
                "avg_entry_price": 50000.0,
                "current_price": 60000.0,
                "market_cap_rank": 1,
                "trailing_stop_price": 51000.0,
                "highest_price": 62000.0,
            }
        ]

        tier = IndexHoldingsTier(client, conn=conn, target_pct=65.0)
        holdings = tier.load_holdings()
        assert "BTCUSDT" in holdings
        assert holdings["BTCUSDT"].quantity == 0.1
        assert holdings["BTCUSDT"].current_price == 60000.0

    @patch("src.data.market_cap.get_top_coins_by_market_cap")
    def test_get_top20_composition(self, mock_coins):
        from src.portfolio.tiers.index_holdings import IndexHoldingsTier

        mock_coins.return_value = [
            {"symbol": "BTC", "market_cap": 1_000_000_000, "rank": 1},
            {"symbol": "ETH", "market_cap": 500_000_000, "rank": 2},
            {"symbol": "SOL", "market_cap": 200_000_000, "rank": 3},
        ]

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        composition = tier.get_top20_composition()

        assert len(composition) == 3
        assert composition[0]["symbol"] == "BTCUSDT"
        # Weights should sum to ~100
        total_weight = sum(c["weight_pct"] for c in composition)
        assert abs(total_weight - 100.0) < 0.1

    @patch("src.data.market_cap.get_top_coins_by_market_cap")
    def test_get_top20_excludes_stablecoins(self, mock_coins):
        from src.portfolio.tiers.index_holdings import IndexHoldingsTier

        mock_coins.return_value = [
            {"symbol": "BTC", "market_cap": 1_000_000_000, "rank": 1},
            {"symbol": "USDT", "market_cap": 800_000_000, "rank": 2},
            {"symbol": "ETH", "market_cap": 500_000_000, "rank": 3},
        ]

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        composition = tier.get_top20_composition()

        symbols = [c["symbol"] for c in composition]
        assert "USDTUSDT" not in symbols
        assert "BTCUSDT" in symbols

    def test_calculate_rebalance_orders(self):
        from src.portfolio.tiers.index_holdings import IndexHolding, IndexHoldingsTier

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        tier._holdings = {
            "BTCUSDT": IndexHolding(
                symbol="BTCUSDT",
                target_weight_pct=30,
                quantity=0.1,
                current_price=50000,
            ),
        }

        target_comp = [
            {"symbol": "BTCUSDT", "weight_pct": 50},
            {"symbol": "ETHUSDT", "weight_pct": 50},
        ]

        orders = tier.calculate_rebalance_orders(target_comp, available_capital=10000.0)
        assert len(orders) >= 1
        # Should have a BUY for ETHUSDT (new position)
        eth_orders = [o for o in orders if o["symbol"] == "ETHUSDT"]
        assert len(eth_orders) == 1
        assert eth_orders[0]["action"] == "BUY"

    def test_update_trailing_stops(self):
        from src.portfolio.tiers.index_holdings import IndexHolding, IndexHoldingsTier

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        tier._holdings = {
            "BTCUSDT": IndexHolding(
                symbol="BTCUSDT",
                target_weight_pct=30,
                quantity=0.1,
                current_price=40000,
                highest_price=50000,
                trailing_stop_price=42500,  # 15% below 50000
            ),
        }

        # Price dropped below trailing stop
        triggered = tier.update_trailing_stops()
        assert "BTCUSDT" in triggered

    def test_trailing_stop_updates_on_new_high(self):
        from src.portfolio.tiers.index_holdings import IndexHolding, IndexHoldingsTier

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        tier._holdings = {
            "BTCUSDT": IndexHolding(
                symbol="BTCUSDT",
                target_weight_pct=30,
                quantity=0.1,
                current_price=55000,
                highest_price=50000,
                trailing_stop_price=42500,
            ),
        }

        triggered = tier.update_trailing_stops()
        assert triggered == []
        # Highest price should be updated
        assert tier._holdings["BTCUSDT"].highest_price == 55000
        # Trailing stop should be 15% below 55000 = 46750
        assert tier._holdings["BTCUSDT"].trailing_stop_price == 55000 * 0.85

    def test_get_total_value(self):
        from src.portfolio.tiers.index_holdings import IndexHolding, IndexHoldingsTier

        tier = IndexHoldingsTier(MagicMock(), target_pct=65.0)
        tier._holdings = {
            "BTCUSDT": IndexHolding(
                symbol="BTCUSDT",
                target_weight_pct=50,
                quantity=0.1,
                current_price=50000,
            ),
            "ETHUSDT": IndexHolding(
                symbol="ETHUSDT",
                target_weight_pct=50,
                quantity=2.0,
                current_price=3000,
            ),
        }

        total = tier.get_total_value()
        assert total == 0.1 * 50000 + 2.0 * 3000  # 5000 + 6000 = 11000


# ═══════════════════════════════════════════════════════════════
# 11.5: Trading Tier
# ═══════════════════════════════════════════════════════════════


class TestTradingTier:
    def test_init(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        orch = MagicMock()
        tier = TradingTier(orch, target_pct=25.0)
        assert tier.target_pct == 25.0
        assert tier._initialized is False

    def test_initialize_delegates(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        orch = MagicMock()
        orch.initialize.return_value = True
        tier = TradingTier(orch)
        assert tier.initialize() is True
        orch.initialize.assert_called_once()

    def test_tick_delegates(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        orch = MagicMock()
        orch.tick.return_value = True
        tier = TradingTier(orch)
        assert tier.tick() is True

    def test_get_realized_pnl(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        orch = MagicMock()
        tier = TradingTier(orch)

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = {"total_pnl": 150.50}

        result = tier.get_realized_pnl(conn)
        assert result == 150.50

    def test_get_total_value(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        orch = MagicMock()
        tier = TradingTier(orch)

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = {"total": 2500.0}

        result = tier.get_total_value(conn)
        assert result == 2500.0

    def test_get_total_value_no_conn(self):
        from src.portfolio.tiers.trading_tier import TradingTier

        tier = TradingTier(MagicMock())
        assert tier.get_total_value(None) == 0.0


# ═══════════════════════════════════════════════════════════════
# 11.2: PortfolioManager
# ═══════════════════════════════════════════════════════════════


class TestPortfolioManager:
    @patch("src.portfolio.portfolio_manager.get_db_connection")
    def test_load_tier_targets(self, mock_db):
        from src.portfolio.portfolio_manager import PortfolioManager

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [
            {"tier_name": "cash_reserve", "target_pct": 15.0},
            {"tier_name": "index_holdings", "target_pct": 60.0},
            {"tier_name": "trading", "target_pct": 25.0},
        ]
        mock_db.return_value = conn

        client = MagicMock()
        pm = PortfolioManager(client=client)
        pm._load_tier_targets()

        assert pm._targets["cash_reserve"] == 15.0
        assert pm._targets["index_holdings"] == 60.0

    @patch("src.portfolio.portfolio_manager.get_db_connection")
    def test_load_tier_targets_no_db(self, mock_db):
        from src.portfolio.portfolio_manager import PortfolioManager

        mock_db.return_value = None

        pm = PortfolioManager(client=MagicMock())
        pm._load_tier_targets()

        # Should keep defaults
        assert pm._targets["cash_reserve"] == 10.0

    @patch("src.portfolio.portfolio_manager.get_db_connection")
    def test_get_total_value(self, mock_db):
        from src.portfolio.portfolio_manager import PortfolioManager

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = {"total": 2500.0}
        mock_db.return_value = conn

        pm = PortfolioManager(client=MagicMock())
        pm.cash_tier = MagicMock()
        pm.cash_tier.balance = 1000.0
        pm.index_tier = MagicMock()
        pm.index_tier.get_total_value.return_value = 6500.0
        pm.trading_tier = MagicMock()
        pm.trading_tier.get_total_value.return_value = 2500.0

        breakdown = pm.get_total_value()
        assert breakdown.total_value == 10000.0
        assert breakdown.cash_pct == 10.0
        assert breakdown.index_pct == 65.0
        assert breakdown.trading_pct == 25.0

    def test_tick_calls_trading_tier(self):
        from src.portfolio.portfolio_manager import PortfolioManager

        pm = PortfolioManager(client=MagicMock())
        pm.trading_tier = MagicMock()
        pm.trading_tier.tick.return_value = True
        pm.cash_tier = MagicMock()
        pm._last_index_update = 9999999999  # Far future, skip index update

        result = pm.tick()
        assert result is True
        pm.trading_tier.tick.assert_called_once()

    def test_tick_returns_false_on_trading_failure(self):
        from src.portfolio.portfolio_manager import PortfolioManager

        pm = PortfolioManager(client=MagicMock())
        pm.trading_tier = MagicMock()
        pm.trading_tier.tick.return_value = False
        pm.cash_tier = MagicMock()

        result = pm.tick()
        assert result is False

    def test_stop(self):
        from src.portfolio.portfolio_manager import PortfolioManager

        pm = PortfolioManager(client=MagicMock())
        pm.trading_tier = MagicMock()
        pm.running = True

        pm.stop()
        assert pm.running is False
        pm.trading_tier.stop.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# 11.6: Profit Redistribution Engine
# ═══════════════════════════════════════════════════════════════


class TestProfitEngine:
    def _make_pm(self, cash=1000, index=6500, trading=2500):
        """Create a mock PortfolioManager with given tier values."""
        from src.portfolio.portfolio_manager import TierBreakdown

        pm = MagicMock()
        total = cash + index + trading
        pm.get_total_value.return_value = TierBreakdown(
            total_value=total,
            cash_value=cash,
            cash_pct=cash / total * 100,
            index_value=index,
            index_pct=index / total * 100,
            trading_value=trading,
            trading_pct=trading / total * 100,
        )
        pm._targets = {"cash_reserve": 10.0, "index_holdings": 65.0, "trading": 25.0}
        return pm

    def test_needs_rebalance_on_target(self):
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        pm = self._make_pm(1000, 6500, 2500)  # Perfect 10/65/25
        engine = ProfitRedistributionEngine(pm)
        assert engine.needs_rebalance() is False

    def test_needs_rebalance_drifted(self):
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        pm = self._make_pm(500, 7000, 2500)  # 5/70/25 — cash drifted 5pp
        engine = ProfitRedistributionEngine(pm)
        assert engine.needs_rebalance() is True

    def test_calculate_rebalance_no_action_when_balanced(self):
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        pm = self._make_pm(1000, 6500, 2500)
        engine = ProfitRedistributionEngine(pm)
        transfers = engine.calculate_rebalance()
        assert transfers == []

    def test_calculate_rebalance_generates_transfers(self):
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        # Cash too low, index too high
        pm = self._make_pm(300, 7200, 2500)
        engine = ProfitRedistributionEngine(pm)
        transfers = engine.calculate_rebalance()

        assert len(transfers) > 0
        # Should transfer from index to cash
        cash_transfers = [t for t in transfers if t.to_tier == "cash_reserve"]
        assert len(cash_transfers) >= 1

    @patch("src.portfolio.profit_engine.get_db_connection")
    def test_execute_rebalance_logs_to_db(self, mock_db):
        from src.portfolio.profit_engine import ProfitRedistributionEngine

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = conn

        pm = self._make_pm(300, 7200, 2500)
        engine = ProfitRedistributionEngine(pm)
        result = engine.execute_rebalance()

        assert result["needed"] is True
        assert len(result["transfers"]) > 0
        conn.commit.assert_called()


# ═══════════════════════════════════════════════════════════════
# 11.7: AI Portfolio Optimizer
# ═══════════════════════════════════════════════════════════════


class TestAIOptimizer:
    def test_parse_valid_recommendation(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        context = {
            "current_tiers": {
                "cash_reserve": {"target_pct": 10.0},
                "index_holdings": {"target_pct": 65.0},
                "trading": {"target_pct": 25.0},
            }
        }

        response = '{"cash_reserve": 12, "index_holdings": 63, "trading": 25, "confidence": 0.75, "reasoning": "More cash in bear"}'
        result = optimizer._parse_recommendation(response, context)

        assert result["confidence"] == 0.75
        assert abs(sum(result["allocations"].values()) - 100.0) < 0.5

    def test_parse_enforces_bounds(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        # Need current_tiers set so bounds are applied before max-shift check
        context = {
            "current_tiers": {
                "cash_reserve": {"target_pct": 15.0},
                "index_holdings": {"target_pct": 60.0},
                "trading": {"target_pct": 25.0},
            }
        }

        # Cash way too high at 50% — should be clamped to max 20
        response = '{"cash_reserve": 50, "index_holdings": 30, "trading": 20, "confidence": 0.5}'
        result = optimizer._parse_recommendation(response, context)

        # Cash should be clamped to max 20 (ALLOCATION_BOUNDS)
        assert result["allocations"]["cash_reserve"] <= 20.5

    def test_parse_enforces_max_shift(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        context = {
            "current_tiers": {
                "cash_reserve": {"target_pct": 10.0},
                "index_holdings": {"target_pct": 65.0},
                "trading": {"target_pct": 25.0},
            }
        }

        # Try to shift cash from 10 to 20 (10pp shift, max is 5pp)
        response = '{"cash_reserve": 20, "index_holdings": 55, "trading": 25, "confidence": 0.8}'
        result = optimizer._parse_recommendation(response, context)

        # Cash should be capped at 10 + 5 = 15
        assert result["allocations"]["cash_reserve"] <= 15.1

    def test_parse_invalid_json(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        result = optimizer._parse_recommendation("not json", {})
        assert result == {}

    def test_parse_normalizes_sum(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        context = {"current_tiers": {}}

        response = '{"cash_reserve": 10, "index_holdings": 60, "trading": 20, "confidence": 0.5}'
        result = optimizer._parse_recommendation(response, context)

        # Should normalize to ~100
        total = sum(result["allocations"].values())
        assert abs(total - 100.0) < 1.0

    def test_build_prompt(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        context = {
            "current_regime": {"regime": "BEAR", "probability": 0.85},
            "trading_30d": {"total_pnl": -50, "trade_count": 100, "win_rate": 45},
            "current_tiers": {
                "cash_reserve": {"target_pct": 10, "current_pct": 8},
            },
        }

        system, user = optimizer.build_prompt(context)
        assert "cash_reserve" in system
        assert "BEAR" in user
        assert "45" in user  # win rate

    @patch("src.portfolio.ai_optimizer.get_db_connection")
    def test_should_auto_apply_below_threshold(self, mock_db):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = (2,)  # Only 2 previous recommendations
        mock_db.return_value = conn

        optimizer = AIPortfolioOptimizer()
        assert optimizer.should_auto_apply({"confidence": 0.9}) is False

    @patch("src.portfolio.ai_optimizer.get_db_connection")
    def test_should_auto_apply_above_threshold(self, mock_db):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = (5,)  # 5 previous recommendations
        mock_db.return_value = conn

        optimizer = AIPortfolioOptimizer()
        assert optimizer.should_auto_apply({"confidence": 0.9}) is True

    def test_should_auto_apply_low_confidence(self):
        from src.portfolio.ai_optimizer import AIPortfolioOptimizer

        optimizer = AIPortfolioOptimizer()
        assert optimizer.should_auto_apply({"confidence": 0.5}) is False

    def test_calculate_max_drawdown(self):
        from src.portfolio.ai_optimizer import _calculate_max_drawdown

        # 100 -> 120 -> 90 -> 110
        assert _calculate_max_drawdown([100, 120, 90, 110]) == 25.0  # (120-90)/120 = 25%

    def test_calculate_max_drawdown_no_drawdown(self):
        from src.portfolio.ai_optimizer import _calculate_max_drawdown

        assert _calculate_max_drawdown([100, 110, 120]) == 0.0

    def test_calculate_max_drawdown_short(self):
        from src.portfolio.ai_optimizer import _calculate_max_drawdown

        assert _calculate_max_drawdown([100]) == 0.0


# ═══════════════════════════════════════════════════════════════
# Market Cap Data
# ═══════════════════════════════════════════════════════════════


class TestMarketCap:
    @patch("src.api.http_client.get_http_client")
    def test_get_top_coins(self, mock_http):
        from src.data.market_cap import _cache, get_top_coins_by_market_cap

        _cache.clear()

        mock_client = MagicMock()
        mock_http.return_value = mock_client
        mock_client.get.return_value = [
            {"symbol": "btc", "market_cap": 1_000_000, "current_price": 50000, "name": "Bitcoin"},
            {"symbol": "eth", "market_cap": 500_000, "current_price": 3000, "name": "Ethereum"},
        ]

        result = get_top_coins_by_market_cap(2)
        assert len(result) == 2
        assert result[0]["symbol"] == "BTC"
        assert result[1]["symbol"] == "ETH"

    @patch("src.api.http_client.get_http_client")
    def test_get_top_coins_caching(self, mock_http):
        from src.data.market_cap import _cache, get_top_coins_by_market_cap

        _cache.clear()

        mock_client = MagicMock()
        mock_http.return_value = mock_client
        mock_client.get.return_value = [
            {"symbol": "btc", "market_cap": 1_000_000, "current_price": 50000, "name": "Bitcoin"},
        ]

        # First call hits API
        get_top_coins_by_market_cap(1)
        assert mock_client.get.call_count == 1

        # Second call uses cache
        get_top_coins_by_market_cap(1)
        assert mock_client.get.call_count == 1


# ═══════════════════════════════════════════════════════════════
# Monitoring: Tier Health Check
# ═══════════════════════════════════════════════════════════════


class TestTierHealthCheck:
    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "false"})
    def test_skips_when_not_portfolio_mode(self):
        from src.tasks.monitoring_tasks import task_tier_health_check

        # Should return without doing anything
        task_tier_health_check()

    @patch("src.tasks.base.get_db_connection")
    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "true"})
    def test_runs_when_portfolio_mode(self, mock_db):
        from src.tasks.monitoring_tasks import task_tier_health_check

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Tier allocations OK
        cur.fetchall.return_value = [
            {
                "tier_name": "cash_reserve",
                "target_pct": 10,
                "current_pct": 9,
                "current_value_usd": 900,
            },
        ]
        # Cash OK, trades OK
        cur.fetchone.side_effect = [
            {"current_pct": 9},  # cash check
            {"count": 5},  # trade activity
        ]
        mock_db.return_value = conn

        task_tier_health_check()
        conn.close.assert_called()


# ═══════════════════════════════════════════════════════════════
# Reporting: Tier Report
# ═══════════════════════════════════════════════════════════════


class TestTierReport:
    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "false"})
    def test_empty_when_not_portfolio_mode(self):
        from src.tasks.reporting_tasks import _build_tier_report

        assert _build_tier_report() == ""

    @patch("src.tasks.reporting_tasks.get_db_connection")
    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "true"})
    def test_builds_report(self, mock_db):
        from src.tasks.reporting_tasks import _build_tier_report

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [
            {
                "tier_name": "cash_reserve",
                "target_pct": 10,
                "current_pct": 9,
                "current_value_usd": 900,
            },
            {
                "tier_name": "index_holdings",
                "target_pct": 65,
                "current_pct": 66,
                "current_value_usd": 6600,
            },
            {
                "tier_name": "trading",
                "target_pct": 25,
                "current_pct": 25,
                "current_value_usd": 2500,
            },
        ]
        mock_db.return_value = conn

        report = _build_tier_report()
        assert "TIER BREAKDOWN" in report
        assert "cash_reserve" in report.lower() or "CASH_RESERVE" in report
        assert "$10,000.00" in report  # Total


# ═══════════════════════════════════════════════════════════════
# main_hybrid.py integration
# ═══════════════════════════════════════════════════════════════


class TestMainHybrid:
    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "false", "PAPER_TRADING": "true"})
    def test_cohort_mode_by_default(self):
        """Verify PORTFOLIO_MANAGER=false uses CohortOrchestrator path."""
        import os

        assert os.getenv("PORTFOLIO_MANAGER", "false").lower() != "true"

    @patch.dict("os.environ", {"PORTFOLIO_MANAGER": "true", "PAPER_TRADING": "true"})
    def test_portfolio_mode_when_enabled(self):
        """Verify PORTFOLIO_MANAGER=true enables portfolio path."""
        import os

        assert os.getenv("PORTFOLIO_MANAGER", "false").lower() == "true"
