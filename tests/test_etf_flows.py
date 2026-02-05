"""
Tests für ETFFlowTracker
"""

from datetime import datetime


class TestETFFlowData:
    """Tests für ETFFlowData Dataclass"""

    def test_etf_flow_data_creation(self):
        """Test ETFFlowData Erstellung"""
        from src.data.etf_flows import ETFFlowData

        flows = ETFFlowData(
            date=datetime.now(),
            btc_total_flow=250.0,
            btc_cumulative_flow=8000.0,
            btc_aum=50000.0,
            gbtc_flow=-100.0,
            ibit_flow=200.0,
            fbtc_flow=150.0,
            arkb_flow=50.0,
            bitb_flow=30.0,
            eth_total_flow=50.0,
            eth_cumulative_flow=2000.0,
            flow_trend="INFLOW",
            seven_day_avg=200.0,
            thirty_day_avg=180.0,
            estimated_price_impact_pct=0.5,
        )

        assert flows.btc_total_flow == 250.0
        assert flows.flow_trend == "INFLOW"
        assert flows.ibit_flow == 200.0


class TestETFFlowTracker:
    """Tests für ETF Flow Tracker"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Test Singleton Pattern"""
        from src.data.etf_flows import ETFFlowTracker

        t1 = ETFFlowTracker.get_instance()
        t2 = ETFFlowTracker.get_instance()

        assert t1 is t2

    def test_tracker_initialization(self, reset_new_singletons):
        """Test Tracker Initialisierung"""
        from src.data.etf_flows import ETFFlowTracker

        tracker = ETFFlowTracker()

        # Sollte ohne Fehler initialisieren
        assert tracker is not None
