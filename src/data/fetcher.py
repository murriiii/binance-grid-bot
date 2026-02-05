"""
Historical Data Fetcher
Holt historische Krypto-Daten von Binance (öffentliche API, kein Key nötig)
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


class BinanceDataFetcher:
    """
    Fetcht historische Klines (Candlestick) Daten von Binance.
    Öffentliche API - kein API Key erforderlich!
    """

    BASE_URL = "https://api.binance.com/api/v3"
    CACHE_DIR = Path("data/cache")

    # Beliebte Altcoins für unser Portfolio
    DEFAULT_ALTCOINS = [
        "BTCUSDT",  # Bitcoin - Referenz
        "ETHUSDT",  # Ethereum - Large Cap
        "SOLUSDT",  # Solana - High Performance L1
        "AVAXUSDT",  # Avalanche - L1
        "LINKUSDT",  # Chainlink - Oracle
        "DOTUSDT",  # Polkadot - Interoperability
        "MATICUSDT",  # Polygon - L2
        "ARBUSDT",  # Arbitrum - L2
        "OPUSDT",  # Optimism - L2
        "INJUSDT",  # Injective - DeFi
    ]

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Holt Kline/Candlestick Daten.

        Args:
            symbol: Trading Pair (z.B. "BTCUSDT")
            interval: Zeitintervall ("1m", "5m", "1h", "4h", "1d", "1w")
            start_date: Start-Datum "YYYY-MM-DD"
            end_date: End-Datum "YYYY-MM-DD"
            limit: Max Anzahl Kerzen (max 1000)

        Returns:
            DataFrame mit OHLCV Daten
        """
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        if start_date:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            params["startTime"] = start_ts

        if end_date:
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
            params["endTime"] = end_ts

        response = requests.get(f"{self.BASE_URL}/klines", params=params)
        response.raise_for_status()

        data = response.json()

        df = pd.DataFrame(
            data,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )

        # Konvertierungen
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        df.set_index("timestamp", inplace=True)

        return df[["open", "high", "low", "close", "volume"]]

    def fetch_multiple_symbols(
        self, symbols: list[str] = None, interval: str = "1d", days: int = 365
    ) -> pd.DataFrame:
        """
        Holt Daten für mehrere Symbole und erstellt Price-Matrix.

        Returns:
            DataFrame mit Close-Preisen, Spalten = Symbole
        """
        symbols = symbols or self.DEFAULT_ALTCOINS

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        prices = {}

        for symbol in symbols:
            print(f"Fetching {symbol}...")
            try:
                df = self.fetch_klines(
                    symbol=symbol, interval=interval, start_date=start_date, end_date=end_date
                )
                prices[symbol.replace("USDT", "")] = df["close"]
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                print(f"  Fehler bei {symbol}: {e}")

        result = pd.DataFrame(prices)
        result = result.dropna()  # Nur Zeilen wo alle Coins Daten haben

        return result

    def get_available_symbols(self) -> list[str]:
        """Gibt alle verfügbaren USDT Trading Pairs zurück"""
        response = requests.get(f"{self.BASE_URL}/exchangeInfo")
        response.raise_for_status()

        symbols = [
            s["symbol"]
            for s in response.json()["symbols"]
            if s["symbol"].endswith("USDT") and s["status"] == "TRADING"
        ]

        return sorted(symbols)

    def save_to_cache(self, df: pd.DataFrame, name: str):
        """Speichert DataFrame im Cache"""
        path = self.CACHE_DIR / f"{name}.csv"
        df.to_csv(path)
        print(f"Gespeichert: {path}")

    def load_from_cache(self, name: str) -> pd.DataFrame | None:
        """Lädt DataFrame aus Cache"""
        path = self.CACHE_DIR / f"{name}.csv"
        if path.exists():
            return pd.read_csv(path, index_col=0, parse_dates=True)
        return None


if __name__ == "__main__":
    # Test
    fetcher = BinanceDataFetcher()

    print("Hole Daten für Standard-Altcoins (letzte 365 Tage)...")
    prices = fetcher.fetch_multiple_symbols(days=365)

    print(f"\nDaten geladen: {len(prices)} Tage, {len(prices.columns)} Coins")
    print(f"Coins: {list(prices.columns)}")
    print("\nLetzte Preise:")
    print(prices.tail())

    fetcher.save_to_cache(prices, "altcoin_prices_365d")
