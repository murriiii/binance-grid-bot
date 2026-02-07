"""Analysis and detection tasks."""

from datetime import datetime

from psycopg2.extras import RealDictCursor

from src.tasks.base import get_db_connection, logger
from src.utils.task_lock import task_locked


@task_locked
def task_regime_detection():
    """Erkennt aktuelles Markt-Regime (BULL/BEAR/SIDEWAYS). Läuft alle 4 Stunden."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Running regime detection...")

    try:
        from src.analysis.regime_detection import RegimeDetector

        detector = RegimeDetector.get_instance()
        regime_state = detector.predict_regime()

        if not regime_state:
            logger.warning("Regime detection returned None - using SIDEWAYS fallback")

        if regime_state:
            logger.info(
                f"Market Regime: {regime_state.current_regime.value} "
                f"(probability: {regime_state.regime_probability:.2f})"
            )

            detector.store_regime(regime_state)

            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT regime FROM regime_history
                            ORDER BY timestamp DESC
                            OFFSET 1 LIMIT 1
                        """)
                        prev = cur.fetchone()

                        if prev and prev["regime"] != regime_state.current_regime.value:
                            telegram = get_telegram()
                            telegram.send(f"""
🔄 <b>REGIME CHANGE DETECTED</b>

{prev["regime"]} → <b>{regime_state.current_regime.value}</b>

Probability: {regime_state.regime_probability:.1%}
Confidence: {regime_state.model_confidence:.1%}

<i>Signal-Gewichte werden angepasst.</i>
""")
                finally:
                    conn.close()

    except Exception as e:
        logger.error(f"Regime Detection Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Regime detection failed", e, {"task": "regime_detection"})


def task_update_signal_weights():
    """Aktualisiert Bayesian Signal Weights. Läuft täglich um 22:00."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Updating Bayesian signal weights...")

    try:
        from src.analysis.bayesian_weights import BayesianWeightLearner

        learner = BayesianWeightLearner.get_instance()
        result = learner.weekly_update()

        updates_count = len(result.get("updates", []))
        errors_count = len(result.get("errors", []))

        logger.info(f"Bayesian Weights: {updates_count} updates, {errors_count} errors")

        if updates_count > 0:
            global_update = None
            for update in result["updates"]:
                if update["type"] == "global":
                    global_update = update
                    break

            if global_update:
                weights = global_update["weights"]
                top_signals = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]

                message = f"""
📊 <b>SIGNAL WEIGHTS UPDATED</b>

Confidence: {global_update["confidence"]:.1%}
Sample Size: {global_update["sample_size"]} trades

<b>Top Signals:</b>
"""
                for name, weight in top_signals:
                    bar = "█" * int(weight * 20)
                    message += f"• {name}: {weight:.1%} {bar}\n"

                telegram = get_telegram()
                telegram.send(message)

    except Exception as e:
        logger.error(f"Signal Weight Update Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Signal weight update failed", e, {"task": "update_signal_weights"})


def task_divergence_scan():
    """Scannt nach Divergenzen in wichtigen Symbolen. Läuft alle 2 Stunden."""
    from src.core.logging_system import get_logger
    from src.notifications.telegram_service import get_telegram

    logger.info("Scanning for divergences...")

    try:
        from src.analysis.divergence_detector import DivergenceDetector

        detector = DivergenceDetector.get_instance()

        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in symbols:
            analysis = detector.analyze(symbol, timeframe="1h")

            if analysis.divergence_count > 0 and analysis.average_confidence > 0.6:
                logger.info(
                    f"Divergence found in {symbol}: "
                    f"{analysis.dominant_type.value}, "
                    f"confidence={analysis.average_confidence:.2f}"
                )

                if abs(analysis.net_signal) > 0.5:
                    direction = "🟢 BULLISH" if analysis.net_signal > 0 else "🔴 BEARISH"

                    div_list = "\n".join(
                        [
                            f"• {d.indicator}: {d.divergence_type.value}"
                            for d in analysis.divergences[:3]
                        ]
                    )

                    telegram = get_telegram()
                    telegram.send(f"""
📊 <b>DIVERGENCE ALERT</b>

<b>{symbol}</b>
{direction} Signal: {analysis.net_signal:.2f}

<b>Divergenzen:</b>
{div_list}

Confidence: {analysis.average_confidence:.1%}
""")

    except Exception as e:
        logger.error(f"Divergence Scan Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Divergence scan failed", e, {"task": "divergence_scan"})


def task_learn_patterns():
    """Analysiert Trades und aktualisiert Patterns. Läuft täglich um 21:00."""
    from src.core.logging_system import get_logger

    logger.info("Learning patterns from trade history...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        from src.data.memory import TradingMemory

        memory = TradingMemory()
        if memory.db:
            memory.learn_and_update_patterns()
            logger.info("Pattern learning completed")

    except Exception as e:
        logger.error(f"Pattern Learning Error: {e}")
        trading_logger = get_logger()
        trading_logger.error("Pattern learning failed", e, {"task": "learn_patterns"})

    finally:
        if conn:
            conn.close()


@task_locked
def task_compute_technical_indicators():
    """Computes technical indicators for active watchlist symbols. Runs every 2 hours."""
    logger.info("Computing technical indicators...")

    conn = get_db_connection()
    if not conn:
        return

    try:
        import numpy as np
        import pandas as pd

        from src.analysis.technical_indicators import TechnicalAnalyzer
        from src.api.http_client import get_http_client

        # Get active symbols from watchlist
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT symbol FROM watchlist")
            rows = cur.fetchall()

        symbols = [r["symbol"] for r in rows]
        if not symbols:
            logger.info("No watchlist symbols — skipping technical indicators")
            return

        http = get_http_client()
        analyzer = TechnicalAnalyzer()
        now = datetime.utcnow()
        inserted = 0

        for symbol in symbols:
            try:
                # Fetch 1h OHLCV from Binance mainnet (need 200+ candles for SMA200)
                response = http.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": symbol.upper(), "interval": "1h", "limit": 250},
                    timeout=10,
                )
                if not response:
                    continue

                data = np.array(response)
                df = pd.DataFrame(
                    {
                        "open": data[:, 1].astype(float),
                        "high": data[:, 2].astype(float),
                        "low": data[:, 3].astype(float),
                        "close": data[:, 4].astype(float),
                        "volume": data[:, 5].astype(float),
                    }
                )

                signals = analyzer.analyze(df, symbol=symbol)

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO technical_indicators (
                            timestamp, symbol, price,
                            sma_20, sma_50, sma_200,
                            rsi_14, macd_line, macd_signal, macd_histogram,
                            bollinger_upper, bollinger_lower, atr_14,
                            trend, momentum, volatility
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (timestamp, symbol) DO NOTHING
                        """,
                        (
                            now,
                            symbol,
                            signals.price,
                            signals.sma_20,
                            signals.sma_50,
                            signals.sma_200,
                            signals.rsi,
                            signals.macd,
                            signals.macd_signal,
                            signals.macd_histogram,
                            signals.bollinger_upper,
                            signals.bollinger_lower,
                            signals.atr,
                            signals.trend.value,
                            signals.momentum.value,
                            signals.volatility,
                        ),
                    )
                    inserted += 1

            except Exception as e:
                logger.warning(f"Technical indicators failed for {symbol}: {e}")
                continue

        conn.commit()
        logger.info(f"Technical indicators: inserted for {inserted}/{len(symbols)} symbols")

    except Exception as e:
        logger.error(f"Technical Indicators Error: {e}")
    finally:
        conn.close()
