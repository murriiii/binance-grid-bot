"""Tests for Phase 10: AI Learning Loop Fix.

Covers:
- 10.1: Signal correctness (was_correct)
- 10.2: Trade decision quality (was_good_decision)
- 10.3: Multi-timeframe outcomes
- 10.5: Signal accuracy in playbook
- 10.6: Regime-stratified playbook rules
- 10.7: Portfolio snapshots
"""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _make_conn_and_cur():
    """Create a mock DB connection with a context-manager cursor."""
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


# ═══════════════════════════════════════════════════════════════
# 10.1: Signal Correctness Evaluation
# ═══════════════════════════════════════════════════════════════


class TestEvaluateSignalCorrectness:
    @patch("src.tasks.system_tasks.get_db_connection")
    def test_updates_signal_correctness(self, mock_db):
        from src.tasks.system_tasks import task_evaluate_signal_correctness

        conn, cur = _make_conn_and_cur()
        cur.rowcount = 15
        mock_db.return_value = conn

        task_evaluate_signal_correctness()

        cur.execute.assert_called_once()
        sql = cur.execute.call_args[0][0]
        assert "UPDATE signal_components" in sql
        assert "was_correct" in sql
        assert "final_score" in sql
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_handles_no_db(self, mock_db):
        from src.tasks.system_tasks import task_evaluate_signal_correctness

        mock_db.return_value = None
        task_evaluate_signal_correctness()

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_handles_db_error(self, mock_db):
        from src.tasks.system_tasks import task_evaluate_signal_correctness

        conn, cur = _make_conn_and_cur()
        cur.execute.side_effect = Exception("DB error")
        mock_db.return_value = conn

        task_evaluate_signal_correctness()
        conn.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# 10.2: Trade Decision Quality
# ═══════════════════════════════════════════════════════════════


class TestEvaluateTradeDecisions:
    @patch("src.tasks.system_tasks.get_db_connection")
    def test_updates_buy_and_sell_decisions(self, mock_db):
        from src.tasks.system_tasks import task_evaluate_trade_decisions

        conn, cur = _make_conn_and_cur()
        cur.rowcount = 5
        mock_db.return_value = conn

        task_evaluate_trade_decisions()

        assert cur.execute.call_count == 2
        calls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("entry_trade_id" in sql for sql in calls)
        assert any("exit_trade_id" in sql for sql in calls)
        conn.commit.assert_called_once()

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_handles_no_db(self, mock_db):
        from src.tasks.system_tasks import task_evaluate_trade_decisions

        mock_db.return_value = None
        task_evaluate_trade_decisions()


# ═══════════════════════════════════════════════════════════════
# 10.3: Multi-Timeframe Outcomes
# ═══════════════════════════════════════════════════════════════


class TestOutcomeTimeframes:
    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_update_outcomes_1h(self, mock_market, mock_db):
        from src.tasks.system_tasks import task_update_outcomes_1h

        market = MagicMock()
        market.get_price.return_value = 55000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"id": "t1", "symbol": "BTCUSDT", "price": 50000, "action": "BUY"}
        ]
        mock_db.return_value = conn

        task_update_outcomes_1h()

        select_sql = cur.execute.call_args_list[0][0][0]
        assert "1 hours" in select_sql
        assert "outcome_1h" in select_sql
        conn.commit.assert_called_once()

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_update_outcomes_4h(self, mock_market, mock_db):
        from src.tasks.system_tasks import task_update_outcomes_4h

        market = MagicMock()
        market.get_price.return_value = 55000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = []
        mock_db.return_value = conn

        task_update_outcomes_4h()
        select_sql = cur.execute.call_args_list[0][0][0]
        assert "4 hours" in select_sql
        assert "outcome_4h" in select_sql

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_update_outcomes_7d(self, mock_market, mock_db):
        from src.tasks.system_tasks import task_update_outcomes_7d

        market = MagicMock()
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = []
        mock_db.return_value = conn

        task_update_outcomes_7d()
        select_sql = cur.execute.call_args_list[0][0][0]
        assert "168 hours" in select_sql
        assert "outcome_7d" in select_sql

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_24h_outcome_sets_was_good_decision(self, mock_market, mock_db):
        from src.tasks.system_tasks import _update_outcomes_for_window

        market = MagicMock()
        market.get_price.return_value = 55000.0  # 10% up
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"id": "t1", "symbol": "BTCUSDT", "price": 50000, "action": "BUY"}
        ]
        mock_db.return_value = conn

        _update_outcomes_for_window(24, "outcome_24h")

        update_sql = cur.execute.call_args_list[1][0][0]
        assert "was_good_decision" in update_sql
        conn.commit.assert_called_once()

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_non_24h_does_not_set_was_good_decision(self, mock_market, mock_db):
        from src.tasks.system_tasks import _update_outcomes_for_window

        market = MagicMock()
        market.get_price.return_value = 55000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"id": "t1", "symbol": "BTCUSDT", "price": 50000, "action": "BUY"}
        ]
        mock_db.return_value = conn

        _update_outcomes_for_window(1, "outcome_1h")

        update_sql = cur.execute.call_args_list[1][0][0]
        assert "was_good_decision" not in update_sql

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_sell_trade_inverts_pct_change(self, mock_market, mock_db):
        from src.tasks.system_tasks import _update_outcomes_for_window

        market = MagicMock()
        market.get_price.return_value = 55000.0  # price went UP
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"id": "t1", "symbol": "BTCUSDT", "price": 50000, "action": "SELL"}
        ]
        mock_db.return_value = conn

        _update_outcomes_for_window(1, "outcome_1h")

        # For SELL, pct_change should be inverted (negative when price went up)
        update_args = cur.execute.call_args_list[1][0][1]
        pct_change = update_args[0]
        assert pct_change < 0  # Price up = bad for seller

    @patch("src.tasks.system_tasks.get_db_connection")
    @patch("src.data.market_data.get_market_data")
    def test_skips_zero_price(self, mock_market, mock_db):
        from src.tasks.system_tasks import _update_outcomes_for_window

        market = MagicMock()
        market.get_price.return_value = 0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"id": "t1", "symbol": "BTCUSDT", "price": 50000, "action": "BUY"}
        ]
        mock_db.return_value = conn

        _update_outcomes_for_window(1, "outcome_1h")

        # SELECT + no UPDATE (price was 0)
        assert cur.execute.call_count == 1

    @patch("src.tasks.system_tasks.get_db_connection")
    def test_handles_no_db(self, mock_db):
        from src.tasks.system_tasks import _update_outcomes_for_window

        mock_db.return_value = None
        _update_outcomes_for_window(1, "outcome_1h")  # Should not raise


# ═══════════════════════════════════════════════════════════════
# 10.5: Signal Accuracy in Playbook
# ═══════════════════════════════════════════════════════════════


class TestPlaybookSignalAccuracy:
    def _make_playbook(self):
        """Create a TradingPlaybook with mocked filesystem."""
        with (
            patch("src.data.playbook.Path.exists", return_value=False),
            patch("src.data.playbook.Path.write_text"),
            patch("src.data.playbook.Path.mkdir"),
        ):
            from src.data.playbook import TradingPlaybook

            pb = TradingPlaybook(db_connection=None)
        return pb

    def test_analyze_signal_accuracy_with_data(self):
        pb = self._make_playbook()

        cur = MagicMock()
        call_count = [0]

        def fake_fetchone():
            call_count[0] += 1
            # First 9 calls: per-signal queries
            if call_count[0] <= 9:
                if call_count[0] == 1:  # fear_greed_signal
                    return {"total": 100, "correct": 68, "avg_strength": 0.45}
                elif call_count[0] == 2:  # rsi_signal
                    return {"total": 90, "correct": 55, "avg_strength": 0.52}
                else:
                    return {"total": 3, "correct": 1, "avg_strength": 0.3}  # below threshold
            elif call_count[0] == 10:  # overall
                return {"total": 200, "correct": 120}
            else:  # per-regime (3 calls)
                return {"total": 60, "correct": 35}

        cur.fetchone = fake_fetchone

        result = pb._analyze_signal_accuracy(cur)

        assert result["overall_total"] == 200
        assert result["overall_accuracy"] == 60.0
        assert len(result["signals"]) == 2  # Only F&G and RSI meet threshold
        assert result["signals"][0]["signal"] == "Fear & Greed"  # Sorted by accuracy desc
        assert result["signals"][0]["accuracy"] == 68.0

    def test_analyze_signal_accuracy_no_data(self):
        pb = self._make_playbook()
        cur = MagicMock()
        cur.fetchone.return_value = {"total": 0, "correct": 0, "avg_strength": 0}

        result = pb._analyze_signal_accuracy(cur)

        assert result["overall_total"] == 0
        assert result["signals"] == []

    def test_generate_signal_accuracy_section_with_data(self):
        pb = self._make_playbook()

        metrics = {
            "signal_accuracy": {
                "signals": [
                    {
                        "signal": "Fear & Greed",
                        "accuracy": 68.0,
                        "avg_strength": 0.45,
                        "total": 100,
                    },
                    {"signal": "RSI", "accuracy": 52.0, "avg_strength": 0.50, "total": 90},
                    {"signal": "MACD", "accuracy": 40.0, "avg_strength": 0.35, "total": 80},
                ],
                "overall_total": 200,
                "overall_accuracy": 60.0,
                "regime_accuracy": {
                    "BULL": {"total": 80, "accuracy": 65.0},
                    "BEAR": {"total": 60, "accuracy": 48.0},
                },
            }
        }

        section = pb._generate_signal_accuracy_section(metrics)

        assert "SIGNAL ACCURACY" in section
        assert "60.0% Accuracy" in section
        assert "Fear & Greed" in section
        assert "BULL" in section
        assert "65.0%" in section
        assert "MACD" in section
        assert "Schwach" in section  # 40% < 45%

    def test_generate_signal_accuracy_section_no_data(self):
        pb = self._make_playbook()

        metrics = {
            "signal_accuracy": {
                "signals": [],
                "overall_total": 2,
                "overall_accuracy": 0,
                "regime_accuracy": {},
            }
        }

        section = pb._generate_signal_accuracy_section(metrics)
        assert "Noch nicht genug" in section

    def test_generate_signal_accuracy_reliable_signals(self):
        """Top reliable signals section appears when accuracy > 55%."""
        pb = self._make_playbook()

        metrics = {
            "signal_accuracy": {
                "signals": [
                    {
                        "signal": "Fear & Greed",
                        "accuracy": 70.0,
                        "avg_strength": 0.45,
                        "total": 100,
                    },
                ],
                "overall_total": 100,
                "overall_accuracy": 70.0,
                "regime_accuracy": {},
            }
        }

        section = pb._generate_signal_accuracy_section(metrics)
        assert "Zuverlässigste Signale" in section

    def test_generate_signal_accuracy_unreliable_signals(self):
        """Unreliable signals section appears when accuracy < 45%."""
        pb = self._make_playbook()

        metrics = {
            "signal_accuracy": {
                "signals": [
                    {"signal": "MACD", "accuracy": 38.0, "avg_strength": 0.3, "total": 50},
                ],
                "overall_total": 50,
                "overall_accuracy": 38.0,
                "regime_accuracy": {},
            }
        }

        section = pb._generate_signal_accuracy_section(metrics)
        assert "Unzuverlässige Signale" in section

    def test_playbook_prompt_includes_signal_section(self):
        pb = self._make_playbook()
        pb.playbook_content = """# Test Playbook

## 📊 MARKT-REGIME REGELN
Some market rules here.

## 🎯 SIGNAL ACCURACY
RSI: 68% accuracy
MACD: 45% accuracy

## ❌ WAS NICHT FUNKTIONIERT HAT
Bad patterns.

## ✅ WAS GUT FUNKTIONIERT HAT
Good patterns.

## 🎛️ AKTUELLE PARAMETER
Some params.

## 📈 OTHER
Not included.
"""
        prompt = pb.get_playbook_for_prompt()

        assert "SIGNAL ACCURACY" in prompt
        assert "RSI: 68% accuracy" in prompt
        assert "OTHER" not in prompt


# ═══════════════════════════════════════════════════════════════
# 10.6: Regime-Stratified Playbook Rules
# ═══════════════════════════════════════════════════════════════


class TestPlaybookRegimeStratification:
    def _make_playbook(self):
        with (
            patch("src.data.playbook.Path.exists", return_value=False),
            patch("src.data.playbook.Path.write_text"),
            patch("src.data.playbook.Path.mkdir"),
        ):
            from src.data.playbook import TradingPlaybook

            pb = TradingPlaybook(db_connection=None)
        return pb

    def test_fear_greed_patterns_include_regime(self):
        pb = self._make_playbook()

        cur = MagicMock()
        call_count = [0]

        def fake_fetchone():
            call_count[0] += 1
            # Return above threshold for some combos
            if call_count[0] % 7 == 1:
                return {"trades": 10, "wins": 7, "avg_return": 2.5, "volatility": 1.0}
            return {"trades": 2, "wins": 1, "avg_return": 0.5, "volatility": 0.5}

        cur.fetchone = fake_fetchone

        patterns = pb._analyze_fear_greed_patterns(cur)

        for p in patterns:
            assert "regime" in p
            assert p["regime"] in ["BULL", "BEAR", "SIDEWAYS", "ALL"]

    def test_anti_patterns_stratified_by_regime(self):
        pb = self._make_playbook()

        cur = MagicMock()
        call_count = [0]

        def fake_fetchall():
            call_count[0] += 1
            if call_count[0] == 1:  # BULL
                return [
                    {
                        "fear_greed": 80,
                        "action": "BUY",
                        "symbol": "BTCUSDT",
                        "market_trend": "BULL",
                        "trades": 8,
                        "avg_return": -3.5,
                    }
                ]
            elif call_count[0] == 2:  # BEAR
                return [
                    {
                        "fear_greed": 20,
                        "action": "SELL",
                        "symbol": "ETHUSDT",
                        "market_trend": "BEAR",
                        "trades": 6,
                        "avg_return": -2.0,
                    }
                ]
            else:
                return []

        cur.fetchall = fake_fetchall

        result = pb._analyze_anti_patterns(cur)

        assert isinstance(result, dict)
        assert "BULL" in result
        assert "BEAR" in result
        assert "SIDEWAYS" in result
        assert "ALL" in result
        assert len(result["BULL"]) == 1
        assert result["BULL"][0]["symbol"] == "BTCUSDT"

    def test_success_patterns_stratified_by_regime(self):
        pb = self._make_playbook()

        cur = MagicMock()
        call_count = [0]

        def fake_fetchall():
            call_count[0] += 1
            if call_count[0] == 1:  # BULL
                return [
                    {
                        "fear_greed": 30,
                        "action": "BUY",
                        "symbol": "BTCUSDT",
                        "market_trend": "BULL",
                        "trades": 12,
                        "avg_return": 4.5,
                        "win_rate": 0.75,
                    }
                ]
            return []

        cur.fetchall = fake_fetchall

        result = pb._analyze_success_patterns(cur)

        assert isinstance(result, dict)
        assert len(result["BULL"]) == 1
        assert result["BULL"][0]["win_rate"] == 75.0

    def test_generated_playbook_has_regime_sections(self):
        pb = self._make_playbook()

        metrics = {
            "total_trades": 100,
            "success_rate": 55.0,
            "fear_greed_patterns": [
                {
                    "range": "Fear",
                    "min": 20,
                    "max": 40,
                    "action": "BUY",
                    "regime": "BULL",
                    "trades": 15,
                    "success_rate": 70.0,
                    "avg_return": 3.0,
                    "volatility": 1.5,
                },
                {
                    "range": "Fear",
                    "min": 20,
                    "max": 40,
                    "action": "BUY",
                    "regime": "BEAR",
                    "trades": 12,
                    "success_rate": 35.0,
                    "avg_return": -2.0,
                    "volatility": 2.0,
                },
                {
                    "range": "Fear",
                    "min": 20,
                    "max": 40,
                    "action": "BUY",
                    "regime": "ALL",
                    "trades": 27,
                    "success_rate": 52.0,
                    "avg_return": 0.8,
                    "volatility": 1.8,
                },
            ],
            "symbol_patterns": [],
            "time_patterns": {"best_weekdays": [], "best_hours": []},
            "anti_patterns": {
                "BULL": [
                    {
                        "fear_greed": 80,
                        "action": "BUY",
                        "symbol": "DOGEUSDT",
                        "trend": "BULL",
                        "trades": 8,
                        "avg_return": -5.0,
                    }
                ],
                "BEAR": [],
                "SIDEWAYS": [],
                "ALL": [],
            },
            "success_patterns": {
                "BULL": [
                    {
                        "fear_greed": 25,
                        "action": "BUY",
                        "symbol": "BTCUSDT",
                        "trend": "BULL",
                        "trades": 15,
                        "avg_return": 4.0,
                        "win_rate": 72.0,
                    }
                ],
                "BEAR": [],
                "SIDEWAYS": [],
                "ALL": [],
            },
            "signal_accuracy": {
                "signals": [{"signal": "RSI", "accuracy": 65.0, "avg_strength": 0.5, "total": 80}],
                "overall_total": 100,
                "overall_accuracy": 58.0,
                "regime_accuracy": {},
            },
        }

        playbook = pb._generate_updated_playbook(metrics)

        assert "BULL Regime" in playbook
        assert "BEAR Regime" in playbook
        assert "Regime-spezifische F&G Regeln" in playbook
        assert "SIGNAL ACCURACY" in playbook
        assert "RSI" in playbook
        assert "DOGEUSDT" in playbook


# ═══════════════════════════════════════════════════════════════
# 10.7: Portfolio Snapshots
# ═══════════════════════════════════════════════════════════════


class TestPortfolioSnapshot:
    @patch("src.data.market_data.get_market_data")
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_takes_snapshot(self, mock_db, mock_market):
        from src.tasks.portfolio_tasks import task_portfolio_snapshot

        market = MagicMock()
        market.get_price.return_value = 60000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        call_count = [0]

        def fake_fetchall():
            call_count[0] += 1
            if call_count[0] == 1:  # positions query
                return [
                    {
                        "symbol": "BTCUSDT",
                        "total_qty": 0.1,
                        "cost_basis": 5000.0,
                        "cohort_id": "c1",
                    }
                ]
            return []

        cur.fetchall = fake_fetchall
        cur.fetchone.return_value = None  # No previous snapshot
        mock_db.return_value = conn

        task_portfolio_snapshot()

        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO portfolio_snapshots" in str(c)
        ]
        assert len(insert_calls) == 1
        conn.commit.assert_called_once()

    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_handles_no_db(self, mock_db):
        from src.tasks.portfolio_tasks import task_portfolio_snapshot

        mock_db.return_value = None
        task_portfolio_snapshot()

    @patch("src.data.market_data.get_market_data")
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_calculates_daily_pnl(self, mock_db, mock_market):
        from src.tasks.portfolio_tasks import task_portfolio_snapshot

        market = MagicMock()
        market.get_price.return_value = 60000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        call_count = [0]

        def fake_fetchall():
            call_count[0] += 1
            if call_count[0] == 1:
                return [
                    {"symbol": "BTCUSDT", "total_qty": 0.1, "cost_basis": 5000, "cohort_id": "c1"}
                ]
            return []

        cur.fetchall = fake_fetchall
        cur.fetchone.return_value = {"total_value_usd": 5500}  # Previous snapshot
        mock_db.return_value = conn

        task_portfolio_snapshot()

        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO portfolio_snapshots" in str(c)
        ]
        assert len(insert_calls) == 1
        args = insert_calls[0][0][1]
        # total_value = 0.1 * 60000 = 6000
        assert args[0] == 6000.0  # total_value
        assert abs(args[1] - 500.0) < 0.01  # daily_pnl = 6000 - 5500

    @patch("src.data.market_data.get_market_data")
    @patch("src.tasks.portfolio_tasks.get_db_connection")
    def test_skips_zero_quantity_positions(self, mock_db, mock_market):
        from src.tasks.portfolio_tasks import task_portfolio_snapshot

        market = MagicMock()
        market.get_price.return_value = 60000.0
        mock_market.return_value = market

        conn, cur = _make_conn_and_cur()
        cur.fetchall.return_value = [
            {"symbol": "BTCUSDT", "total_qty": 0, "cost_basis": 0, "cohort_id": "c1"}
        ]
        cur.fetchone.return_value = None
        mock_db.return_value = conn

        task_portfolio_snapshot()

        # Should still insert but with 0 value
        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO portfolio_snapshots" in str(c)
        ]
        assert len(insert_calls) == 1
        args = insert_calls[0][0][1]
        assert args[0] == 0.0  # total_value = 0


# ═══════════════════════════════════════════════════════════════
# Playbook Full Integration
# ═══════════════════════════════════════════════════════════════


class TestPlaybookAnalyzeAndUpdate:
    def _make_playbook_with_conn(self, conn):
        with (
            patch("src.data.playbook.Path.exists", return_value=False),
            patch("src.data.playbook.Path.write_text"),
            patch("src.data.playbook.Path.mkdir"),
        ):
            from src.data.playbook import TradingPlaybook

            pb = TradingPlaybook(db_connection=conn)
        return pb

    def test_analyze_includes_signal_accuracy(self):
        """Verify analyze_and_update() calls _analyze_signal_accuracy."""
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        # fetchone returns basic stats first, then zeros for everything else
        stats_result = {
            "total_trades": 20,
            "good_trades": 12,
            "avg_return_24h": 1.5,
            "avg_return_7d": 3.0,
        }
        default_result = {
            "total": 0,
            "correct": 0,
            "avg_strength": 0,
            "trades": 0,
            "wins": 0,
            "avg_return": 0,
            "volatility": 0,
        }

        results = [stats_result] + [default_result] * 100
        cur.fetchone.side_effect = results
        cur.fetchall.return_value = []

        pb = self._make_playbook_with_conn(conn)

        with patch.object(pb, "_save_playbook"), patch.object(pb, "_save_to_database"):
            result = pb.analyze_and_update()

        assert "metrics" in result
        assert "signal_accuracy" in result["metrics"]
        assert result["version"] == 2

    def test_no_db_returns_error(self):
        with (
            patch("src.data.playbook.Path.exists", return_value=False),
            patch("src.data.playbook.Path.write_text"),
            patch("src.data.playbook.Path.mkdir"),
        ):
            from src.data.playbook import TradingPlaybook

            pb = TradingPlaybook(db_connection=None)

        result = pb.analyze_and_update()
        assert "error" in result

    def test_not_enough_trades_skips_update(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        stats_result = {
            "total_trades": 2,
            "good_trades": 1,
            "avg_return_24h": 0,
            "avg_return_7d": 0,
        }
        default_result = {
            "total": 0,
            "correct": 0,
            "avg_strength": 0,
            "trades": 0,
            "wins": 0,
            "avg_return": 0,
            "volatility": 0,
        }

        cur.fetchone.side_effect = [stats_result] + [default_result] * 100
        cur.fetchall.return_value = []

        pb = self._make_playbook_with_conn(conn)
        result = pb.analyze_and_update()

        assert result["version"] == 1  # Not incremented
        assert any("Nicht genug" in c for c in result["changes"])
