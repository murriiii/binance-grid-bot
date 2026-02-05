"""
Whale Alert Integration
Trackt große Krypto-Transaktionen die den Markt beeinflussen können

Große Transfers können signalisieren:
- Exchange Deposit: Potentieller Verkaufsdruck (BEARISH)
- Exchange Withdrawal: Akkumulation (BULLISH)
- Wallet-to-Wallet: Neutral, aber beobachtenswert

Kostenlose Quellen:
- Whale Alert Twitter (scraping)
- Blockchain Explorer APIs
- CryptoQuant (limitiert)
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.api.http_client import get_http_client, HTTPClientError
from src.core.config import get_config

logger = logging.getLogger('trading_bot')


@dataclass
class WhaleTransaction:
    """Eine große Krypto-Transaktion"""
    timestamp: datetime
    symbol: str
    amount: float
    amount_usd: float
    tx_type: str  # transfer, exchange_deposit, exchange_withdrawal
    from_owner: str  # exchange name or "unknown wallet"
    to_owner: str
    tx_hash: Optional[str] = None

    @property
    def is_exchange_deposit(self) -> bool:
        """Wurde an eine Exchange gesendet?"""
        exchanges = ['binance', 'coinbase', 'kraken', 'okx', 'bybit', 'kucoin', 'bitfinex']
        return any(ex in self.to_owner.lower() for ex in exchanges)

    @property
    def is_exchange_withdrawal(self) -> bool:
        """Wurde von einer Exchange abgezogen?"""
        exchanges = ['binance', 'coinbase', 'kraken', 'okx', 'bybit', 'kucoin', 'bitfinex']
        return any(ex in self.from_owner.lower() for ex in exchanges)

    @property
    def potential_impact(self) -> str:
        """Schätze den Markt-Impact"""
        if self.is_exchange_deposit:
            return "BEARISH"  # Jemand will verkaufen
        elif self.is_exchange_withdrawal:
            return "BULLISH"  # Jemand akkumuliert
        else:
            return "NEUTRAL"

    def to_alert_message(self) -> str:
        """Formatiert für Telegram"""
        emoji = "🐋"
        if self.potential_impact == "BEARISH":
            emoji = "🔴🐋"
        elif self.potential_impact == "BULLISH":
            emoji = "🟢🐋"

        return f"""
{emoji} *WHALE ALERT*

{self.amount:,.0f} {self.symbol} (${self.amount_usd:,.0f})

From: `{self.from_owner}`
To: `{self.to_owner}`

Impact: *{self.potential_impact}*
_{self._get_impact_explanation()}_
"""

    def _get_impact_explanation(self) -> str:
        if self.is_exchange_deposit:
            return "Coins an Exchange gesendet - möglicher Verkauf"
        elif self.is_exchange_withdrawal:
            return "Coins von Exchange abgezogen - Akkumulation"
        return "Transfer zwischen Wallets"


class WhaleAlertTracker:
    """
    Trackt Whale-Transaktionen aus verschiedenen Quellen.

    Strategie:
    - Große Deposits auf Exchanges = Vorsicht, Verkaufsdruck möglich
    - Große Withdrawals = Bullish, Smart Money akkumuliert
    - Threshold: > $1M für Altcoins, > $10M für BTC
    """

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.http = get_http_client()
        self.config = get_config()
        self.recent_alerts: List[WhaleTransaction] = []

    def get_threshold(self, symbol: str) -> float:
        thresholds = {
            'BTC': self.config.whale.btc_threshold,
            'ETH': self.config.whale.eth_threshold,
            'DEFAULT': self.config.whale.default_threshold
        }
        return thresholds.get(symbol, thresholds['DEFAULT'])

    def fetch_recent_whales(self, hours: int = 24) -> List[WhaleTransaction]:
        """
        Holt Whale-Transaktionen der letzten X Stunden.
        Verwendet kostenlose APIs:
        - Blockchain.com für BTC
        - Blockchair für aggregierte Daten
        """
        whales = []

        # BTC Whale Tracking via Blockchain.com
        btc_whales = self._fetch_btc_whales(hours)
        whales.extend(btc_whales)

        # Update recent_alerts Cache
        self.recent_alerts = whales

        return whales

    def _fetch_btc_whales(self, hours: int = 24) -> List[WhaleTransaction]:
        """
        Holt große BTC-Transaktionen von Blockchain.com.
        Kostenlos, kein API-Key benötigt.
        """
        whales = []
        threshold_btc = self.config.whale.min_btc_amount

        try:
            # Hole aktuelle unbestätigte Transaktionen
            data = self.http.get(
                self.config.api.blockchain_url,
                api_type='blockchain'
            )

            btc_price = self._get_btc_price()

            for tx in data.get('txs', [])[:50]:  # Maximal 50 prüfen
                # Berechne Gesamtoutput
                total_output_satoshi = sum(
                    out.get('value', 0) for out in tx.get('out', [])
                )
                total_btc = total_output_satoshi / 1e8

                if total_btc < threshold_btc:
                    continue

                # Identifiziere Sender/Empfänger
                from_addr = "Unknown Wallet"
                to_addr = "Unknown Wallet"

                if tx.get('inputs') and tx['inputs'][0].get('prev_out'):
                    prev_out = tx['inputs'][0]['prev_out']
                    from_addr = self._identify_address(prev_out.get('addr', ''))

                if tx.get('out') and tx['out'][0].get('addr'):
                    to_addr = self._identify_address(tx['out'][0]['addr'])

                whale = WhaleTransaction(
                    timestamp=datetime.fromtimestamp(tx.get('time', datetime.now().timestamp())),
                    symbol='BTC',
                    amount=total_btc,
                    amount_usd=total_btc * btc_price,
                    tx_type=self._determine_tx_type(from_addr, to_addr),
                    from_owner=from_addr,
                    to_owner=to_addr,
                    tx_hash=tx.get('hash')
                )

                whales.append(whale)

        except HTTPClientError as e:
            logger.warning(f"Whale Alert Error: {e}")

        return whales

    def _get_btc_price(self) -> float:
        """Holt aktuellen BTC Preis"""
        try:
            data = self.http.get(
                f"{self.config.api.coingecko_url}/simple/price",
                params={'ids': 'bitcoin', 'vs_currencies': 'usd'},
                api_type='default'
            )
            return data['bitcoin']['usd']
        except HTTPClientError as e:
            logger.warning(f"BTC Price API Error: {e}")
            return 100000  # Fallback

    def _identify_address(self, address: str) -> str:
        """
        Identifiziert bekannte Exchange-Adressen.
        In Produktion: Größere Datenbank verwenden.
        """
        if not address:
            return "Unknown Wallet"

        # Bekannte Exchange Cold Wallets (Beispiele)
        known_addresses = {
            'bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h': 'Binance',
            '3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6': 'Binance',
            'bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97': 'Bitfinex',
            '1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g': 'Bitfinex',
            'bc1q4c8n5t00jmj8temxdgcc3t32nkg2wjwz24lywv': 'Kraken',
            '3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B': 'Coinbase',
        }

        for known_addr, name in known_addresses.items():
            if address.startswith(known_addr[:10]):  # Prefix-Match
                return name

        # Heuristic: Wenn die Adresse sehr aktiv ist, könnte es eine Exchange sein
        return "Unknown Wallet"

    def _determine_tx_type(self, from_owner: str, to_owner: str) -> str:
        """Bestimmt den Transaktionstyp"""
        exchanges = ['binance', 'coinbase', 'kraken', 'okx', 'bybit', 'kucoin', 'bitfinex']

        from_is_exchange = any(ex in from_owner.lower() for ex in exchanges)
        to_is_exchange = any(ex in to_owner.lower() for ex in exchanges)

        if to_is_exchange and not from_is_exchange:
            return "exchange_deposit"
        elif from_is_exchange and not to_is_exchange:
            return "exchange_withdrawal"
        else:
            return "transfer"

    def analyze_whale_activity(
        self,
        symbol: str,
        hours: int = 24
    ) -> Dict:
        """
        Analysiert Whale-Aktivität für ein Symbol.

        Returns:
            {
                'net_flow': float,  # Positiv = mehr Withdrawals (bullish)
                'total_deposits': float,
                'total_withdrawals': float,
                'signal': str,  # BULLISH, BEARISH, NEUTRAL
                'confidence': float,
                'reasoning': str
            }
        """
        whales = [w for w in self.recent_alerts
                  if w.symbol == symbol
                  and w.timestamp > datetime.now() - timedelta(hours=hours)]

        if not whales:
            return {
                'net_flow': 0,
                'total_deposits': 0,
                'total_withdrawals': 0,
                'signal': 'NEUTRAL',
                'confidence': 0.0,
                'reasoning': 'Keine signifikanten Whale-Bewegungen'
            }

        deposits = sum(w.amount_usd for w in whales if w.is_exchange_deposit)
        withdrawals = sum(w.amount_usd for w in whales if w.is_exchange_withdrawal)
        net_flow = withdrawals - deposits

        # Bestimme Signal
        if net_flow > self.get_threshold(symbol) * 2:
            signal = 'BULLISH'
            confidence = min(0.8, net_flow / (self.get_threshold(symbol) * 5))
            reasoning = f"Starke Akkumulation: ${net_flow:,.0f} netto von Exchanges abgezogen"
        elif net_flow < -self.get_threshold(symbol) * 2:
            signal = 'BEARISH'
            confidence = min(0.8, abs(net_flow) / (self.get_threshold(symbol) * 5))
            reasoning = f"Verkaufsdruck: ${abs(net_flow):,.0f} netto auf Exchanges eingezahlt"
        else:
            signal = 'NEUTRAL'
            confidence = 0.3
            reasoning = "Keine eindeutige Richtung bei Whale-Flows"

        return {
            'net_flow': net_flow,
            'total_deposits': deposits,
            'total_withdrawals': withdrawals,
            'signal': signal,
            'confidence': confidence,
            'reasoning': reasoning,
            'whale_count': len(whales)
        }

    def get_trading_signal(self, symbols: List[str]) -> Dict:
        """
        Aggregiertes Signal für mehrere Symbole.
        """
        signals = {}
        for symbol in symbols:
            signals[symbol] = self.analyze_whale_activity(symbol)

        # Gesamt-Signal
        bullish_count = sum(1 for s in signals.values() if s['signal'] == 'BULLISH')
        bearish_count = sum(1 for s in signals.values() if s['signal'] == 'BEARISH')

        if bullish_count > bearish_count + 1:
            overall = 'BULLISH'
        elif bearish_count > bullish_count + 1:
            overall = 'BEARISH'
        else:
            overall = 'NEUTRAL'

        return {
            'overall_signal': overall,
            'by_symbol': signals,
            'summary': f"Bullish: {bullish_count}, Bearish: {bearish_count}, Neutral: {len(symbols) - bullish_count - bearish_count}"
        }

    def save_to_db(self, whale: WhaleTransaction) -> bool:
        """Speichert Whale-Alert in Datenbank"""
        if not self.db:
            return False

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    INSERT INTO whale_alerts
                    (timestamp, symbol, amount, amount_usd, transaction_type,
                     from_owner, to_owner, is_significant, potential_impact)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    whale.timestamp, whale.symbol, whale.amount,
                    whale.amount_usd, whale.tx_type, whale.from_owner,
                    whale.to_owner, True, whale.potential_impact
                ))
                self.db.commit()
                return True
        except Exception as e:
            logger.error(f"DB Error: {e}")
            return False


# Für Echtzeit-Tracking (später implementieren)
class WhaleAlertWebSocket:
    """
    WebSocket-Verbindung für Echtzeit Whale Alerts.

    TODO: Implementieren wenn kostenpflichtiger API-Zugang vorhanden
    """
    pass
