"""
Tests für src/strategies/grid_strategy.py
"""

from decimal import Decimal

import pytest


class TestGridLevel:
    """Tests für GridLevel Dataclass"""

    def test_default_values(self):
        """Testet Standard-Werte"""
        from src.strategies.grid_strategy import GridLevel

        level = GridLevel(price=100.0)

        assert level.price == Decimal("100")
        assert level.buy_order_id is None
        assert level.sell_order_id is None
        assert level.filled is False
        assert level.quantity == Decimal("0")
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

        assert level.price == Decimal("50000")
        assert level.buy_order_id == 123
        assert level.quantity == Decimal("0.001")
        assert level.filled is True

    def test_accepts_decimal_directly(self):
        """Testet dass Decimal-Werte direkt akzeptiert werden"""
        from src.strategies.grid_strategy import GridLevel

        level = GridLevel(price=Decimal("42000.50"), quantity=Decimal("0.00123"))

        assert level.price == Decimal("42000.50")
        assert level.quantity == Decimal("0.00123")
        assert isinstance(level.price, Decimal)
        assert isinstance(level.quantity, Decimal)

    def test_auto_converts_float_to_decimal(self):
        """Testet dass float-Werte automatisch zu Decimal konvertiert werden"""
        from src.strategies.grid_strategy import GridLevel

        level = GridLevel(price=100.0, quantity=0.5)

        assert isinstance(level.price, Decimal)
        assert isinstance(level.quantity, Decimal)


class TestGridStrategy:
    """Tests für GridStrategy"""

    @pytest.fixture
    def basic_symbol_info(self):
        """Standard Symbol Info für Tests (flat dict format)"""
        return {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
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

        assert strategy.lower_price == Decimal("40000")
        assert strategy.upper_price == Decimal("50000")
        assert strategy.num_grids == 5
        assert strategy.total_investment == Decimal("100")
        assert isinstance(strategy.lower_price, Decimal)
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
        expected_step = Decimal("10000") / 5

        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            assert abs(diff - expected_step) < Decimal("1")

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
                expected_qty = Decimal("20") / level.price
                # Quantity should be <= expected (rounded down to step_size)
                assert level.quantity <= expected_qty
                # But not too far off (within 1 step_size)
                assert expected_qty - level.quantity < Decimal("0.00001")

    def test_quantities_are_decimal(self, basic_symbol_info):
        """Testet dass alle Quantities Decimal sind"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=basic_symbol_info,
        )

        for level in strategy.levels:
            assert isinstance(level.price, Decimal)
            assert isinstance(level.quantity, Decimal)

    def test_min_notional_validation(self):
        """Testet min_notional Validierung"""
        from src.strategies.grid_strategy import GridStrategy

        # Symbol mit hohem min_notional
        high_min_notional_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
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
        assert all(o["price"] < Decimal("45000") for o in result["buy_orders"])
        assert all(o["price"] > Decimal("45000") for o in result["sell_orders"])
        # Order prices should be Decimal
        if result["buy_orders"]:
            assert isinstance(result["buy_orders"][0]["price"], Decimal)

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
        """Testet on_buy_filled - sollte Sell-Order mit fee-adjusted Qty platzieren"""
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
        original_qty = strategy.levels[0].quantity
        result = strategy.on_buy_filled(first_level_price)

        assert result["action"] == "PLACE_SELL"
        assert result["price"] == strategy.levels[1].price
        # Sell qty must be less than buy qty (fee deducted)
        assert result["quantity"] < original_qty
        # fee_qty should be returned
        assert result["fee_qty"] > Decimal("0")

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
            "tick_size": 0.01,
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
            "tick_size": 0.01,
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
        assert price_diff < Decimal("30")

    def test_step_size_rounding(self):
        """Testet korrekte step_size Rundung"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.001,
            "step_size": 0.001,  # 3 Dezimalstellen
            "tick_size": 0.01,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        step = Decimal("0.001")
        for level in strategy.levels:
            # Quantity must be an exact multiple of step_size
            remainder = level.quantity % step
            assert remainder == Decimal("0"), (
                f"Quantity {level.quantity} is not a multiple of step_size {step}"
            )

    def test_no_scientific_notation_in_quantity(self):
        """Testet dass keine Scientific Notation bei kleinen Quantities"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=90000.0,
            upper_price=110000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        for level in strategy.levels:
            qty_str = str(level.quantity)
            assert "E" not in qty_str and "e" not in qty_str, (
                f"Scientific notation in quantity: {qty_str}"
            )

    def test_no_price_match_on_buy_filled(self):
        """Testet on_buy_filled wenn kein passendes Level gefunden wird"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
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
            "tick_size": 0.01,
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
            "tick_size": 0.01,
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

    def test_low_cap_coin_precision(self):
        """Testet Decimal-Präzision bei Low-Cap Coins ($0.001)"""
        from src.strategies.grid_strategy import GridStrategy

        symbol_info = {
            "symbol": "SHIBUSDT",
            "min_qty": 1.0,
            "step_size": 1.0,
            "tick_size": 0.00000001,
            "min_notional": 5.00,
        }

        strategy = GridStrategy(
            lower_price=0.00001,
            upper_price=0.00002,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        for level in strategy.levels:
            assert isinstance(level.price, Decimal)
            assert isinstance(level.quantity, Decimal)
            # No scientific notation
            assert "E" not in str(level.quantity) and "e" not in str(level.quantity)
            assert "E" not in str(level.price) and "e" not in str(level.price)


class TestFeeCalculation:
    """Tests für die Fee-Berechnung in GridStrategy"""

    @pytest.fixture
    def symbol_info(self):
        return {
            "symbol": "BTCUSDT",
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
            "min_notional": 5.00,
        }

    def test_buy_fill_sell_qty_reduced_by_fee(self, symbol_info):
        """BUY 0.001 BTC → SELL 0.000999 BTC (minus 0.1% fee)"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        buy_qty = strategy.levels[0].quantity
        result = strategy.on_buy_filled(strategy.levels[0].price)

        assert result["action"] == "PLACE_SELL"
        # Sell qty = buy_qty * (1 - 0.001), rounded down to step_size
        expected_sell = buy_qty * Decimal("0.999")
        assert result["quantity"] <= expected_sell
        # Should not be too far off (within 1 step_size)
        assert expected_sell - result["quantity"] < Decimal("0.00001")

    def test_fee_qty_matches_difference(self, symbol_info):
        """fee_qty should equal buy_qty - sell_qty"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        buy_qty = strategy.levels[0].quantity
        result = strategy.on_buy_filled(strategy.levels[0].price)

        assert result["fee_qty"] == buy_qty - result["quantity"]

    def test_sell_fill_buy_qty_not_reduced(self, symbol_info):
        """SELL fill → BUY should use full grid quantity (no fee adjustment needed)"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
        )

        result = strategy.on_sell_filled(strategy.levels[1].price)
        assert result["action"] == "PLACE_BUY"
        # BUY quantity should be the full grid level quantity (no fee deduction)
        assert result["quantity"] == strategy.levels[0].quantity

    def test_custom_fee_rate(self, symbol_info):
        """Testet benutzerdefinierte Fee-Rate (z.B. BNB-Rabatt 0.075%)"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
            fee_rate=Decimal("0.00075"),  # BNB discount
        )

        buy_qty = strategy.levels[0].quantity
        result = strategy.on_buy_filled(strategy.levels[0].price)

        expected_sell = buy_qty * Decimal("0.99925")
        assert result["quantity"] <= expected_sell

    def test_zero_fee_rate(self, symbol_info):
        """Testet mit Fee-Rate 0 (Maker-Rabatt oder Promo)"""
        from src.strategies.grid_strategy import GridStrategy

        strategy = GridStrategy(
            lower_price=40000.0,
            upper_price=50000.0,
            num_grids=5,
            total_investment=100.0,
            symbol_info=symbol_info,
            fee_rate=Decimal("0"),
        )

        buy_qty = strategy.levels[0].quantity
        result = strategy.on_buy_filled(strategy.levels[0].price)

        # With 0 fee, sell qty should equal buy qty
        assert result["quantity"] == buy_qty

    def test_fee_constant_exported(self):
        """Testet dass TAKER_FEE_RATE korrekt exportiert wird"""
        from src.strategies.grid_strategy import TAKER_FEE_RATE

        assert Decimal("0.001") == TAKER_FEE_RATE


class TestFormatDecimal:
    """Tests für die format_decimal Hilfsfunktion"""

    def test_no_scientific_notation(self):
        """Testet dass keine Scientific Notation produziert wird"""
        from src.api.binance_client import format_decimal

        assert format_decimal(0.0000123) == "0.0000123"
        assert format_decimal(1.23e-5) == "0.0000123"

    def test_integer_values(self):
        """Testet Integer-Werte"""
        from src.api.binance_client import format_decimal

        assert format_decimal(100) == "100"
        assert format_decimal(42000.0) == "42000"

    def test_decimal_input(self):
        """Testet Decimal-Input"""
        from src.api.binance_client import format_decimal

        assert format_decimal(Decimal("0.001")) == "0.001"
        assert format_decimal(Decimal("100.00")) == "100"

    def test_strips_trailing_zeros(self):
        """Testet dass unnötige Trailing-Zeros entfernt werden"""
        from src.api.binance_client import format_decimal

        assert format_decimal(1.50) == "1.5"
        assert format_decimal(Decimal("0.00100")) == "0.001"
