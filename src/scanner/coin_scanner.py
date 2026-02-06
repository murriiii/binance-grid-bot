"""
Coin Scanner für Multi-Coin Trading Opportunities.

Scannt alle Coins in der Watchlist nach Trading-Opportunities
basierend auf technischen und fundamentalen Signalen.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.scanner.opportunity import Opportunity, OpportunityDirection, OpportunityRisk
from src.utils.singleton import SingletonMixin

load_dotenv()

logger = logging.getLogger("trading_bot")

# PostgreSQL
try:
    import psycopg2

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class CoinScanner(SingletonMixin):
    """
    Scannt Watchlist nach Trading-Opportunities.

    Analysiert jeden Coin auf:
    1. Technische Signale (RSI, MACD, Divergenz)
    2. Volume Anomalien (Spikes, Ausbrüche)
    3. Sentiment-Shifts (Fear&Greed, Social)
    4. Whale-Aktivität
    5. Momentum

    Usage:
        scanner = CoinScanner.get_instance()
        opportunities = scanner.scan_opportunities()
        top_5 = scanner.get_top_opportunities(5)
    """

    # Default Score-Gewichte
    DEFAULT_WEIGHTS = {
        "technical": 0.30,
        "volume": 0.20,
        "sentiment": 0.15,
        "whale": 0.15,
        "momentum": 0.20,
    }

    # Thresholds für Signale
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    VOLUME_SPIKE_THRESHOLD = 2.0  # 2x Durchschnitt
    FEAR_GREED_EXTREME_FEAR = 25
    FEAR_GREED_EXTREME_GREED = 75

    def __init__(self):
        self.conn = None
        self._last_scan: datetime | None = None
        self._cached_opportunities: list[Opportunity] = []
        self._cache_ttl = timedelta(minutes=30)
        self._weights = self.DEFAULT_WEIGHTS.copy()
        self.connect()

    def close(self):
        """Called by SingletonMixin.reset_instance()."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def connect(self) -> bool:
        """Verbindet zur PostgreSQL Datenbank."""
        if not POSTGRES_AVAILABLE:
            logger.warning("PostgreSQL nicht verfügbar - CoinScanner eingeschränkt")
            return False

        try:
            self.conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", 5432),
                database=os.getenv("POSTGRES_DB", "trading_bot"),
                user=os.getenv("POSTGRES_USER", "trading"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
            )
            logger.info("CoinScanner: PostgreSQL verbunden")
            return True
        except Exception as e:
            logger.error(f"CoinScanner: PostgreSQL Fehler: {e}")
            self.conn = None
            return False

    def set_weights(self, weights: dict[str, float]) -> None:
        """Setzt benutzerdefinierte Score-Gewichte."""
        self._weights.update(weights)
        # Normalisieren
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}

    def scan_opportunities(
        self,
        force_refresh: bool = False,
    ) -> list[Opportunity]:
        """
        Scannt alle aktiven Coins nach Opportunities.

        Args:
            force_refresh: Ignoriert Cache

        Returns:
            Liste von Opportunities, sortiert nach Score
        """
        # Check Cache
        if (
            not force_refresh
            and self._last_scan
            and datetime.now() - self._last_scan < self._cache_ttl
        ):
            return self._cached_opportunities

        from src.data.watchlist import get_watchlist_manager

        watchlist = get_watchlist_manager()
        coins = watchlist.get_tradeable_coins()

        if not coins:
            logger.warning("CoinScanner: Keine tradeable Coins in Watchlist")
            return []

        opportunities = []
        for coin in coins:
            try:
                opp = self._analyze_coin(coin)
                if opp and opp.total_score > 0.3:  # Minimum Score
                    opportunities.append(opp)
            except Exception as e:
                logger.debug(f"CoinScanner: Analyse-Fehler für {coin.symbol}: {e}")

        # Sortieren nach Score (absteigend)
        opportunities.sort(key=lambda x: x.total_score, reverse=True)

        # Cache aktualisieren
        self._cached_opportunities = opportunities
        self._last_scan = datetime.now()

        # In DB speichern
        self._store_opportunities(opportunities)

        logger.info(f"CoinScanner: {len(opportunities)} Opportunities gefunden")
        return opportunities

    def _analyze_coin(self, coin) -> Opportunity | None:
        """
        Analysiert einen einzelnen Coin.

        Args:
            coin: WatchlistCoin Objekt

        Returns:
            Opportunity oder None
        """
        opp = Opportunity(
            symbol=coin.symbol,
            category=coin.category,
            current_price=coin.last_price,
            volume_24h=coin.last_volume_24h,
        )

        # 1. Technische Analyse
        tech_score, tech_signals = self._calculate_technical_score(coin.symbol)
        opp.technical_score = tech_score
        opp.signals.extend(tech_signals)

        # 2. Volume Analyse
        volume_score, volume_signals = self._calculate_volume_score(coin)
        opp.volume_score = volume_score
        opp.signals.extend(volume_signals)

        # 3. Sentiment Analyse
        sentiment_score, sentiment_signals = self._calculate_sentiment_score(coin.base_asset)
        opp.sentiment_score = sentiment_score
        opp.signals.extend(sentiment_signals)

        # 4. Whale Analyse
        whale_score, whale_signals = self._calculate_whale_score(coin.base_asset)
        opp.whale_score = whale_score
        opp.signals.extend(whale_signals)

        # 5. Momentum Analyse
        momentum_score, momentum_signals = self._calculate_momentum_score(coin)
        opp.momentum_score = momentum_score
        opp.signals.extend(momentum_signals)

        # Gesamtscore berechnen
        opp.calculate_total_score(self._weights)

        # Confidence basierend auf Datenqualität
        data_points = sum(
            [
                1 if opp.technical_score > 0 else 0,
                1 if opp.volume_score > 0 else 0,
                1 if opp.sentiment_score > 0 else 0,
                1 if opp.whale_score > 0 else 0,
                1 if opp.momentum_score > 0 else 0,
            ]
        )
        opp.confidence = data_points / 5.0

        # Richtung und Risiko bestimmen
        opp.determine_direction()
        opp.determine_risk()

        return opp

    def _calculate_technical_score(self, symbol: str) -> tuple[float, list[str]]:
        """
        Berechnet technischen Score aus RSI, MACD, etc.

        Returns:
            (score, [signals])
        """
        signals = []
        scores = []

        try:
            from src.analysis.technical_indicators import TechnicalIndicators
            from src.api.binance_client import BinanceClient

            client = BinanceClient()
            indicators = TechnicalIndicators()

            # Hole Klines (4h für mittelfristige Signale)
            klines = client.get_klines(symbol, "4h", limit=100)
            if not klines:
                return 0.0, []

            import pandas as pd

            df = pd.DataFrame(klines)
            closes = df["close"].astype(float)

            # RSI
            rsi_series = indicators.calculate_rsi(closes)
            if not rsi_series.empty:
                rsi = rsi_series.iloc[-1]
                if rsi < self.RSI_OVERSOLD:
                    scores.append(0.8)
                    signals.append(f"RSI Oversold ({rsi:.0f})")
                elif rsi > self.RSI_OVERBOUGHT:
                    scores.append(0.3)  # Bearish Signal
                    signals.append(f"RSI Overbought ({rsi:.0f})")
                else:
                    scores.append(0.5)

            # MACD
            _macd_line, _signal_line, histogram = indicators.calculate_macd(closes)
            if not histogram.empty:
                hist_val = histogram.iloc[-1]
                prev_hist = histogram.iloc[-2] if len(histogram) > 1 else 0

                if hist_val > 0 and prev_hist < 0:
                    scores.append(0.8)
                    signals.append("MACD Bullish Cross")
                elif hist_val < 0 and prev_hist > 0:
                    scores.append(0.2)
                    signals.append("MACD Bearish Cross")
                elif hist_val > 0:
                    scores.append(0.6)
                else:
                    scores.append(0.4)

            # Bollinger Bands
            bb = indicators.calculate_bollinger_bands(closes)
            if bb is not None:
                current_price = closes.iloc[-1]
                lower, _middle, upper = bb
                if current_price < lower.iloc[-1]:
                    scores.append(0.7)
                    signals.append("Price below Bollinger Lower")
                elif current_price > upper.iloc[-1]:
                    scores.append(0.3)
                    signals.append("Price above Bollinger Upper")

        except Exception as e:
            logger.debug(f"CoinScanner: Tech analysis error for {symbol}: {e}")
            return 0.0, []

        if not scores:
            return 0.0, []

        return sum(scores) / len(scores), signals

    def _calculate_volume_score(self, coin) -> tuple[float, list[str]]:
        """
        Berechnet Volume Score basierend auf Spikes und Trends.

        Returns:
            (score, [signals])
        """
        signals = []

        if not coin.last_volume_24h or not coin.min_volume_24h_usd:
            return 0.5, []  # Neutral wenn keine Daten

        volume_ratio = float(coin.last_volume_24h) / float(coin.min_volume_24h_usd)

        if volume_ratio >= self.VOLUME_SPIKE_THRESHOLD:
            signals.append(f"Volume Spike ({volume_ratio:.1f}x)")
            return 0.8, signals
        elif volume_ratio >= 1.5:
            signals.append(f"Volume erhöht ({volume_ratio:.1f}x)")
            return 0.65, signals
        elif volume_ratio < 0.5:
            signals.append("Volume niedrig")
            return 0.3, signals

        return 0.5, signals

    def _calculate_sentiment_score(self, base_asset: str) -> tuple[float, list[str]]:
        """
        Berechnet Sentiment Score aus Fear&Greed und Social.

        Returns:
            (score, [signals])
        """
        signals = []
        scores = []

        try:
            from src.data.sentiment import SentimentAggregator

            aggregator = SentimentAggregator()
            sentiment = aggregator.get_aggregated_sentiment()

            if sentiment and sentiment.value is not None:
                fg = sentiment.value

                if fg <= self.FEAR_GREED_EXTREME_FEAR:
                    scores.append(0.8)
                    signals.append(f"Extreme Fear ({fg})")
                elif fg >= self.FEAR_GREED_EXTREME_GREED:
                    scores.append(0.3)
                    signals.append(f"Extreme Greed ({fg})")
                elif fg < 40:
                    scores.append(0.65)
                    signals.append(f"Fear ({fg})")
                elif fg > 60:
                    scores.append(0.4)
                    signals.append(f"Greed ({fg})")
                else:
                    scores.append(0.5)

        except Exception as e:
            logger.debug(f"CoinScanner: Sentiment error: {e}")

        # Social Sentiment (wenn verfügbar)
        try:
            from src.data.social_sentiment import get_social_sentiment

            social = get_social_sentiment()
            composite = social.get_composite_sentiment(base_asset)

            if composite is not None:
                # composite ist -1 bis +1, normalisieren auf 0-1
                normalized = (composite + 1) / 2
                scores.append(normalized)

                if composite > 0.5:
                    signals.append(f"Social Bullish ({composite:.2f})")
                elif composite < -0.5:
                    signals.append(f"Social Bearish ({composite:.2f})")

        except Exception as e:
            logger.debug(f"CoinScanner: Social sentiment error: {e}")

        if not scores:
            return 0.5, []

        return sum(scores) / len(scores), signals

    def _calculate_whale_score(self, base_asset: str) -> tuple[float, list[str]]:
        """
        Berechnet Whale Score basierend auf großen Transaktionen.

        Returns:
            (score, [signals])
        """
        signals = []

        try:
            from src.data.whale_alert import WhaleAlertTracker

            tracker = WhaleAlertTracker()
            recent = tracker.get_recent_transactions(base_asset, hours=24)

            if not recent:
                return 0.5, []

            # Analysiere Whale-Aktivität
            total_value = sum(t.amount_usd for t in recent)
            if total_value == 0:
                return 0.5, []
            exchange_inflows = sum(
                t.amount_usd for t in recent if t.to_owner and "exchange" in t.to_owner.lower()
            )
            exchange_outflows = sum(
                t.amount_usd for t in recent if t.from_owner and "exchange" in t.from_owner.lower()
            )

            net_flow = exchange_outflows - exchange_inflows

            if net_flow > 0:
                # Outflow = bullish (Accumulation)
                score = min(0.8, 0.5 + (net_flow / total_value) * 0.3)
                signals.append(f"Whale Accumulation (${net_flow / 1e6:.1f}M)")
            elif net_flow < 0:
                # Inflow = bearish (Distribution)
                score = max(0.2, 0.5 - (abs(net_flow) / total_value) * 0.3)
                signals.append(f"Whale Distribution (${abs(net_flow) / 1e6:.1f}M)")
            else:
                score = 0.5

            return score, signals

        except Exception as e:
            logger.debug(f"CoinScanner: Whale error: {e}")
            return 0.5, []

    def _calculate_momentum_score(self, coin) -> tuple[float, list[str]]:
        """
        Berechnet Momentum Score aus Preistrends.

        Returns:
            (score, [signals])
        """
        signals = []

        try:
            from src.api.binance_client import BinanceClient

            client = BinanceClient()
            ticker = client.get_24h_ticker(coin.symbol)

            if not ticker:
                return 0.5, []

            change_24h = ticker.get("price_change_percent", 0)

            if change_24h > 10:
                score = 0.3  # Überkauft nach starkem Anstieg
                signals.append(f"Strong Rally +{change_24h:.1f}% (Caution)")
            elif change_24h > 5:
                score = 0.6
                signals.append(f"Positive Momentum +{change_24h:.1f}%")
            elif change_24h < -10:
                score = 0.7  # Potential Recovery nach starkem Fall
                signals.append(f"Oversold -{abs(change_24h):.1f}% (Bounce?)")
            elif change_24h < -5:
                score = 0.4
                signals.append(f"Negative Momentum {change_24h:.1f}%")
            else:
                score = 0.5

            return score, signals

        except Exception as e:
            logger.debug(f"CoinScanner: Momentum error: {e}")
            return 0.5, []

    def get_top_opportunities(
        self,
        n: int = 5,
        category: str | None = None,
        direction: OpportunityDirection | None = None,
    ) -> list[Opportunity]:
        """
        Gibt die Top N Opportunities zurück.

        Args:
            n: Anzahl der Opportunities
            category: Optionaler Kategorie-Filter
            direction: Optionaler Richtungs-Filter

        Returns:
            Liste der besten Opportunities
        """
        opportunities = self.scan_opportunities()

        if category:
            opportunities = [o for o in opportunities if o.category == category]

        if direction:
            opportunities = [o for o in opportunities if o.direction == direction]

        return opportunities[:n]

    def get_opportunities_by_risk(
        self,
        risk_level: OpportunityRisk,
    ) -> list[Opportunity]:
        """Filtert Opportunities nach Risiko-Level."""
        opportunities = self.scan_opportunities()
        return [o for o in opportunities if o.risk_level == risk_level]

    def _store_opportunities(self, opportunities: list[Opportunity]) -> None:
        """Speichert Opportunities in der Datenbank."""
        if not self.conn or not opportunities:
            return

        try:
            with self.conn.cursor() as cur:
                for opp in opportunities[:20]:  # Max 20 speichern
                    cur.execute(
                        """
                        INSERT INTO opportunities (
                            symbol, category, direction, total_score, confidence,
                            technical_score, volume_score, sentiment_score,
                            whale_score, momentum_score, signals, risk_level,
                            current_price, volume_24h
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            opp.symbol,
                            opp.category,
                            opp.direction.value,
                            opp.total_score,
                            opp.confidence,
                            opp.technical_score,
                            opp.volume_score,
                            opp.sentiment_score,
                            opp.whale_score,
                            opp.momentum_score,
                            opp.signals,
                            opp.risk_level.value,
                            float(opp.current_price) if opp.current_price else None,
                            float(opp.volume_24h) if opp.volume_24h else None,
                        ),
                    )
                self.conn.commit()
        except Exception as e:
            logger.error(f"CoinScanner: DB store error: {e}")
            self.conn.rollback()

    def get_scan_stats(self) -> dict:
        """Gibt Statistiken über den letzten Scan zurück."""
        if not self._cached_opportunities:
            return {"last_scan": None, "total_opportunities": 0}

        by_direction = {}
        by_risk = {}
        by_category = {}

        for opp in self._cached_opportunities:
            by_direction[opp.direction.value] = by_direction.get(opp.direction.value, 0) + 1
            by_risk[opp.risk_level.value] = by_risk.get(opp.risk_level.value, 0) + 1
            by_category[opp.category] = by_category.get(opp.category, 0) + 1

        return {
            "last_scan": self._last_scan,
            "total_opportunities": len(self._cached_opportunities),
            "by_direction": by_direction,
            "by_risk": by_risk,
            "by_category": by_category,
            "average_score": sum(o.total_score for o in self._cached_opportunities)
            / len(self._cached_opportunities),
            "top_symbol": self._cached_opportunities[0].symbol
            if self._cached_opportunities
            else None,
        }


# Convenience-Funktion
def get_coin_scanner() -> CoinScanner:
    """Gibt die globale CoinScanner-Instanz zurück."""
    return CoinScanner.get_instance()
