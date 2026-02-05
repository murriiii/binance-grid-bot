"""
Tests für src/strategies/grid_strategy.py
"""

import pytest


class TestGridLevel:
    """Tests für GridLevel Dataclass"""

    def test_default_values(self):
        """Testet Standard-Werte"""
        from src.strategies.grid_strategy import GridLevel

        level = GridLevel(price=100.0)

        assert level.price == 100.0
        assert level.buy_order_id is None
        assert level.sell_order_id is None
        assert level.filled is False
        assert level.quantity == 0.0
        assert level.valid is True

    def test_custom_values(self):
        """Testet benutzerdefinierte Werte"""
        from src.strategies.grid_strategy import GridLevel

        level = GridLevel(
            price=50000.0,
            buy_order_id=123,
            quantity=0.001,
            filled=True,
            valid=True,
        )

        assert level.price == 50000.0
        assert level.buy_order_id == 123
        assert level.quantity == 0.001
        assert level.filled is True


class TestGridStrategy:
    """Tests für GridStrategy"""

    @pytest.fixture
    def basic_symbol_info(self):
        """Standard Symbol Info für Tests (flat dict format)"""
        return {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

    def test_initialization(self, basic_symbol_info):
        """Testet Grid-Initialisierung"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        assert strategy.lower_price == 40000.0
        assert strategy.upper_price == 50000.0
        assert strategy.num_grids == 5
        assert strategy.total_investment == 100.0
        # num_grids + 1 levels are created (including both endpoints)
        assert len(strategy.levels) == 6

    def test_grid_levels_are_evenly_spaced(self, basic_symbol_info):
        """Testet gleichmäßige Abstände zwischen Levels"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        prices = [level.price for level in strategy.levels]
        # With num_grids=5, spacing = 10000/5 = 2000
        expected_step = (50000.0 - 40000.0) / 5

        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            assert abs(diff - expected_step) < 1.0  # Toleranz für Rundung

    def test_quantity_per_level(self, basic_symbol_info):
        """Testet Quantity-Berechnung pro Level"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        # Investment pro Level = 100 / 5 = 20 USDT
        for level in strategy.levels:
            if level.valid:
                expected_qty = 20.0 / level.price
                # Allow some tolerance for rounding
                assert abs(level.quantity - expected_qty) < 0.0001 or level.quantity < expected_qty

    def test_min_notional_validation(self):
        """Testet min_notional Validierung"""
        from src.strategies.grid_strategy import GridStrategy

        # Symbol mit hohem min_notional
        high_min_notional_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 500.00,  # 500 USDT minimum
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,  # Zu wenig für min_notional von 500
            symbol_info=high_min_notional_info,
        )

        # Sollte keine oder sehr wenige gültige Levels haben
        # da 100 USDT total / 5 = 20 USDT per level < 500 min_notional
        assert strategy.skipped_levels > 0 or len(strategy.levels) < 6

    def test_get_initial_orders_below_price(self, basic_symbol_info):
        """Testet get_initial_orders mit Preis in der Mitte"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        result = strategy.get_initial_orders(45000.0)

        # Sollte Buy-Orders unter 45000 und Sell-Orders über 45000 haben
        assert "buy_orders" in result
        assert "sell_orders" in result
        assert all(o["price"] < 45000.0 for o in result["buy_orders"])
        assert all(o["price"] > 45000.0 for o in result["sell_orders"])

    def test_get_initial_orders_at_bottom(self, basic_symbol_info):
        """Testet get_initial_orders wenn Preis am unteren Ende"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        result = strategy.get_initial_orders(35000.0)  # Unter lower_price

        # Alle Orders sollten Sell-Orders sein
        assert len(result["buy_orders"]) == 0
        assert len(result["sell_orders"]) > 0

    def test_get_initial_orders_at_top(self, basic_symbol_info):
        """Testet get_initial_orders wenn Preis am oberen Ende"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        result = strategy.get_initial_orders(55000.0)  # Über upper_price

        # Alle Orders sollten Buy-Orders sein
        assert len(result["buy_orders"]) > 0
        assert len(result["sell_orders"]) == 0

    def test_on_buy_filled(self, basic_symbol_info):
        """Testet on_buy_filled - sollte Sell-Order platzieren"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        # Simuliere Buy Fill auf erstem Level
        first_level_price = strategy.levels[0].price
        result = strategy.on_buy_filled(first_level_price)

        assert result["action"] == "PLACE_SELL"
        assert result["price"] == strategy.levels[1].price

    def test_on_sell_filled(self, basic_symbol_info):
        """Testet on_sell_filled - sollte Buy-Order platzieren"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        # Simuliere Sell Fill auf zweitem Level
        second_level_price = strategy.levels[1].price
        result = strategy.on_sell_filled(second_level_price)

        assert result["action"] == "PLACE_BUY"
        assert result["price"] == strategy.levels[0].price

    def test_on_buy_filled_marks_level_as_filled(self, basic_symbol_info):
        """Testet dass on_buy_filled das Level als gefüllt markiert"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        first_level_price = strategy.levels[0].price
        strategy.on_buy_filled(first_level_price)

        assert strategy.levels[0].filled is True

    def test_on_sell_filled_marks_level_as_unfilled(self, basic_symbol_info):
        """Testet dass on_sell_filled das Level als nicht gefüllt markiert"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        # Erst als filled markieren
        strategy.levels[1].filled = True

        second_level_price = strategy.levels[1].price
        strategy.on_sell_filled(second_level_price)

        assert strategy.levels[1].filled is False


class TestGridStrategyEdgeCases:
    """Edge Cases für Grid Strategy"""

    def test_single_grid_level(self):
        """Testet mit nur 2 Grid Levels (Minimum)"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=2,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # num_grids=2 means 3 levels (0, 1, 2)
        assert len(strategy.levels) == 3

    def test_very_narrow_range(self):
        """Testet mit sehr engem Preisbereich"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=42000.0,
            upper_price=42100.0,  # Nur 100 USDT Range
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # num_grids=5 means 6 levels
        assert len(strategy.levels) == 6
        # Aber der Abstand ist sehr klein
        price_diff = strategy.levels[1].price - strategy.levels[0].price
        assert price_diff < 30  # ~20 USDT pro Level

    def test_step_size_rounding(self):
        """Testet korrekte step_size Rundung"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.001,
            "step_size": 0.001,  # 3 Dezimalstellen
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # Quantity sollte auf step_size gerundet sein (floor)
        for level in strategy.levels:
            # Prüfe dass Quantity auf 3 Dezimalstellen gerundet ist
            rounded = round(level.quantity, 3)
            assert abs(level.quantity - rounded) < 0.0001 or level.quantity <= rounded

    def test_no_price_match_on_buy_filled(self):
        """Testet on_buy_filled wenn kein passendes Level gefunden wird"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # Preis der nicht zu einem Level passt
        result = strategy.on_buy_filled(99999.0)
        assert result["action"] == "NONE"

    def test_on_buy_filled_at_highest_level(self):
        """Testet on_buy_filled am höchsten Level (kein nächsthöheres)"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # Buy fill am höchsten Level
        last_level_price = strategy.levels[-1].price
        result = strategy.on_buy_filled(last_level_price)

        # Sollte NONE zurückgeben da kein höheres Level existiert
        assert result["action"] == "NONE"

    def test_on_sell_filled_at_lowest_level(self):
        """Testet on_sell_filled am niedrigsten Level (kein nächstniedrigeres)"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        # Sell fill am niedrigsten Level
        first_level_price = strategy.levels[0].price
        result = strategy.on_sell_filled(first_level_price)

        # Sollte NONE zurückgeben da kein niedrigeres Level existiert
        assert result["action"] == "NONE"
