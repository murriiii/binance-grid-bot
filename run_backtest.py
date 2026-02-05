#!/usr/bin/env python3
"""
Backtest Runner
Testet die Portfolio-Strategie auf historischen Daten

Keine API Keys nötig - nutzt öffentliche Binance Daten!
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.fetcher import BinanceDataFetcher
from src.backtest.engine import BacktestEngine, print_backtest_report
from src.strategies.portfolio_rebalance import portfolio_rebalance_strategy


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║              PORTFOLIO BACKTEST - Altcoin Strategie               ║
    ╠═══════════════════════════════════════════════════════════════════╣
    ║  Keine API Keys nötig - nutzt öffentliche historische Daten!      ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)

    # 1. Historische Daten holen
    print("📊 Lade historische Daten von Binance...")
    fetcher = BinanceDataFetcher()

    # Versuche Cache zu laden, sonst neu fetchen
    prices = fetcher.load_from_cache("altcoin_prices_365d")
    if prices is None:
        prices = fetcher.fetch_multiple_symbols(days=365)
        fetcher.save_to_cache(prices, "altcoin_prices_365d")

    print(f"   ✓ {len(prices)} Tage Daten für {len(prices.columns)} Coins geladen")
    print(f"   Coins: {', '.join(prices.columns)}\n")

    # 2. Backtest konfigurieren
    initial_capital = 10.0  # Dein Startkapital

    print(f"💰 Startkapital: ${initial_capital}")
    print(f"📅 Zeitraum: {prices.index[0].strftime('%Y-%m-%d')} bis {prices.index[-1].strftime('%Y-%m-%d')}")
    print(f"🔄 Strategie: Portfolio Rebalancing mit Markowitz + Risiko-Skalierung\n")

    # 3. Backtest ausführen
    print("🚀 Starte Backtest...\n")

    engine = BacktestEngine(
        initial_capital=initial_capital,
        fee_rate=0.001,  # 0.1% Binance Fee
        slippage=0.0005  # 0.05% Slippage
    )

    result = engine.run(
        price_data=prices,
        strategy=portfolio_rebalance_strategy,
        price_history=prices,
        rebalance_interval_days=7  # Wöchentliches Rebalancing
    )

    # 4. Report ausgeben
    print_backtest_report(result)

    # 5. Vergleich mit Buy & Hold
    print("\n📈 VERGLEICH MIT BUY & HOLD:")
    print("─" * 50)

    for coin in ['BTC', 'ETH', 'SOL']:
        if coin in prices.columns:
            start_price = prices[coin].iloc[0]
            end_price = prices[coin].iloc[-1]
            bh_return = (end_price - start_price) / start_price
            print(f"   {coin}: {bh_return*100:+.1f}%")

    strategy_return = result.total_return * 100
    print(f"\n   Unsere Strategie: {strategy_return:+.1f}%")
    print("─" * 50)

    # 6. Trade-Log speichern
    log_file = "logs/backtest_trades.log"
    with open(log_file, 'w') as f:
        f.write("BACKTEST TRADE LOG\n")
        f.write("=" * 80 + "\n\n")

        for trade in result.trades:
            f.write(f"{trade.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"{trade.trade_type.value:4} | {trade.symbol:6} | "
                    f"${trade.value:>8.2f} @ ${trade.price:.2f}\n")
            f.write(f"   BEGRÜNDUNG: {trade.reasoning}\n\n")

    print(f"\n📝 Detailliertes Trade-Log gespeichert: {log_file}")
    print("   Dort siehst du WARUM jeder Trade gemacht wurde!\n")


if __name__ == '__main__':
    main()
