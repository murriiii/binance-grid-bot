"""
Opportunity Dataclass für Trading-Signale.

Repräsentiert eine erkannte Trading-Opportunity mit allen
relevanten Scores und Signalen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class OpportunityDirection(str, Enum):
    """Richtung der Trading-Opportunity."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class OpportunityRisk(str, Enum):
    """Risiko-Level der Opportunity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class Opportunity:
    """
    Erkannte Trading-Opportunity.

    Kombiniert verschiedene Signal-Scores zu einem Gesamtscore.
    Wird vom CoinScanner generiert und vom PortfolioAllocator verwendet.
    """

    # Identifikation
    symbol: str
    category: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Einzelne Scores (0.0 - 1.0)
    technical_score: float = 0.0  # RSI, MACD, Divergenz
    volume_score: float = 0.0  # Volume Spike
    sentiment_score: float = 0.0  # Fear&Greed, Social
    whale_score: float = 0.0  # Whale Activity
    momentum_score: float = 0.0  # Price Momentum

    # Kombinierte Scores
    total_score: float = 0.0
    confidence: float = 0.0

    # Richtung
    direction: OpportunityDirection = OpportunityDirection.NEUTRAL

    # Kontext
    signals: list[str] = field(default_factory=list)
    risk_level: OpportunityRisk = OpportunityRisk.MEDIUM

    # Marktdaten zum Zeitpunkt
    current_price: Decimal | None = None
    volume_24h: Decimal | None = None
    price_change_24h: float | None = None

    # Technische Daten
    rsi: float | None = None
    macd_histogram: float | None = None
    atr: float | None = None

    def calculate_total_score(
        self,
        weights: dict[str, float] | None = None,
    ) -> float:
        """
        Berechnet den gewichteten Gesamtscore.

        Args:
            weights: Optionale Gewichte für jeden Score-Typ.
                     Default: Gleichgewichtet.

        Returns:
            Gewichteter Gesamtscore (0.0 - 1.0)
        """
        if weights is None:
            weights = {
                "technical": 0.30,
                "volume": 0.20,
                "sentiment": 0.15,
                "whale": 0.15,
                "momentum": 0.20,
            }

        weighted_sum = (
            self.technical_score * weights.get("technical", 0.20)
            + self.volume_score * weights.get("volume", 0.20)
            + self.sentiment_score * weights.get("sentiment", 0.20)
            + self.whale_score * weights.get("whale", 0.20)
            + self.momentum_score * weights.get("momentum", 0.20)
        )

        self.total_score = min(1.0, max(0.0, weighted_sum))
        return self.total_score

    def determine_direction(self) -> OpportunityDirection:
        """
        Bestimmt die Trading-Richtung basierend auf den Signalen.

        Returns:
            LONG, SHORT oder NEUTRAL
        """
        long_signals = sum(
            1
            for s in self.signals
            if any(
                x in s.lower() for x in ["oversold", "bullish", "accumulation", "buy", "support"]
            )
        )

        short_signals = sum(
            1
            for s in self.signals
            if any(
                x in s.lower()
                for x in ["overbought", "bearish", "distribution", "sell", "resistance"]
            )
        )

        if long_signals > short_signals and self.total_score > 0.5:
            self.direction = OpportunityDirection.LONG
        elif short_signals > long_signals and self.total_score > 0.5:
            self.direction = OpportunityDirection.SHORT
        else:
            self.direction = OpportunityDirection.NEUTRAL

        return self.direction

    def determine_risk(self) -> OpportunityRisk:
        """
        Bestimmt das Risiko-Level basierend auf Confidence und Volatilität.

        Returns:
            LOW, MEDIUM oder HIGH
        """
        if self.confidence >= 0.7 and self.total_score >= 0.6:
            self.risk_level = OpportunityRisk.LOW
        elif self.confidence < 0.4 or self.total_score < 0.3:
            self.risk_level = OpportunityRisk.HIGH
        else:
            self.risk_level = OpportunityRisk.MEDIUM

        return self.risk_level

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary für DB-Storage."""
        return {
            "symbol": self.symbol,
            "category": self.category,
            "timestamp": self.timestamp.isoformat(),
            "technical_score": self.technical_score,
            "volume_score": self.volume_score,
            "sentiment_score": self.sentiment_score,
            "whale_score": self.whale_score,
            "momentum_score": self.momentum_score,
            "total_score": self.total_score,
            "confidence": self.confidence,
            "direction": self.direction.value,
            "signals": self.signals,
            "risk_level": self.risk_level.value,
            "current_price": float(self.current_price) if self.current_price else None,
            "volume_24h": float(self.volume_24h) if self.volume_24h else None,
            "price_change_24h": self.price_change_24h,
            "rsi": self.rsi,
            "macd_histogram": self.macd_histogram,
            "atr": self.atr,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Opportunity:
        """Erstellt eine Opportunity aus einem Dictionary."""
        return cls(
            symbol=data["symbol"],
            category=data["category"],
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data["timestamp"], str)
            else data["timestamp"],
            technical_score=data.get("technical_score", 0.0),
            volume_score=data.get("volume_score", 0.0),
            sentiment_score=data.get("sentiment_score", 0.0),
            whale_score=data.get("whale_score", 0.0),
            momentum_score=data.get("momentum_score", 0.0),
            total_score=data.get("total_score", 0.0),
            confidence=data.get("confidence", 0.0),
            direction=OpportunityDirection(data.get("direction", "NEUTRAL")),
            signals=data.get("signals", []),
            risk_level=OpportunityRisk(data.get("risk_level", "MEDIUM")),
            current_price=Decimal(str(data["current_price"]))
            if data.get("current_price")
            else None,
            volume_24h=Decimal(str(data["volume_24h"])) if data.get("volume_24h") else None,
            price_change_24h=data.get("price_change_24h"),
            rsi=data.get("rsi"),
            macd_histogram=data.get("macd_histogram"),
            atr=data.get("atr"),
        )

    def __repr__(self) -> str:
        return (
            f"Opportunity({self.symbol}, score={self.total_score:.2f}, "
            f"dir={self.direction.value}, risk={self.risk_level.value})"
        )
