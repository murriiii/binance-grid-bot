"""
Zentraler HTTP Client mit Retry-Logik, Timeout und Caching.
Ersetzt alle verstreuten requests.get() / requests.post() Aufrufe.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock
from typing import Any

import requests

logger = logging.getLogger("trading_bot")


class HTTPClientError(Exception):
    """Basis-Exception für HTTP Client Fehler"""

    pass


class RateLimitError(HTTPClientError):
    """Rate Limit erreicht"""

    pass


class TimeoutError(HTTPClientError):
    """Request Timeout"""

    pass


def cached(ttl_seconds: int = 300):
    """
    Decorator für Caching von API-Responses.

    Args:
        ttl_seconds: Time-to-live in Sekunden (default: 5 Minuten)
    """
    cache = {}
    lock = Lock()

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Cache-Key aus Funktionsname und Argumenten
            key = f"{func.__name__}:{args!s}:{sorted(kwargs.items())!s}"

            with lock:
                if key in cache:
                    value, timestamp = cache[key]
                    if datetime.now() - timestamp < timedelta(seconds=ttl_seconds):
                        logger.debug(f"Cache hit: {func.__name__}")
                        return value
                    del cache[key]

            # Nicht im Cache - ausführen
            result = func(*args, **kwargs)

            with lock:
                cache[key] = (result, datetime.now())
                # Cache-Größe begrenzen
                if len(cache) > 100:
                    oldest_key = min(cache, key=lambda k: cache[k][1])
                    del cache[oldest_key]

            return result

        wrapper.clear_cache = lambda: cache.clear()
        return wrapper

    return decorator


class HTTPClient:
    """
    Zentraler HTTP Client für alle API-Aufrufe.

    Features:
    - Automatische Retries mit Exponential Backoff
    - Konfigurierbare Timeouts
    - Rate Limit Handling
    - Strukturiertes Logging
    - Response Caching (optional)

    Usage:
        client = HTTPClient()
        data = client.get("https://api.example.com/data", timeout=10)
    """

    # Standard-Timeouts pro API-Typ
    DEFAULT_TIMEOUTS = {
        "default": 10,
        "deepseek": 30,
        "blockchain": 15,
        "telegram": 10,
        "binance": 10,
    }

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        default_timeout: int = 10,
    ):
        """
        Args:
            max_retries: Maximale Anzahl Retries bei Fehlern
            base_delay: Basis-Verzögerung zwischen Retries (Sekunden)
            max_delay: Maximale Verzögerung zwischen Retries (Sekunden)
            default_timeout: Standard-Timeout für Requests (Sekunden)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.default_timeout = default_timeout

        # Session für Connection Pooling
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TradingBot/1.0", "Accept": "application/json"})

        # Statistiken
        self.stats = {"requests": 0, "successes": 0, "retries": 0, "failures": 0}

    def _calculate_delay(self, attempt: int) -> float:
        """Berechnet Exponential Backoff Delay"""
        delay = self.base_delay * (2**attempt)
        return min(delay, self.max_delay)

    def _should_retry(self, exception: Exception, status_code: int | None) -> bool:
        """Entscheidet ob ein Retry sinnvoll ist"""
        # Timeout - immer retry
        if isinstance(exception, requests.Timeout):
            return True

        # Connection Error - retry
        if isinstance(exception, requests.ConnectionError):
            return True

        # HTTP Status Codes
        if status_code:
            # Rate Limit (429) - retry mit längerer Pause
            if status_code == 429:
                return True
            # Server Errors (5xx) - retry
            if 500 <= status_code < 600:
                return True

        # Client Errors (4xx) - kein retry (außer 429)
        return False

    def get(
        self,
        url: str,
        params: dict | None = None,
        timeout: int | None = None,
        headers: dict | None = None,
        api_type: str = "default",
    ) -> dict[str, Any]:
        """
        HTTP GET Request mit Retry-Logik.

        Args:
            url: Ziel-URL
            params: Query-Parameter
            timeout: Timeout in Sekunden (optional, nutzt api_type Default)
            headers: Zusätzliche Header
            api_type: API-Typ für Timeout-Lookup ('default', 'deepseek', etc.)

        Returns:
            Response JSON als Dict

        Raises:
            HTTPClientError: Bei allen Fehlern nach allen Retries
        """
        return self._request(
            "GET", url, params=params, timeout=timeout, headers=headers, api_type=api_type
        )

    def post(
        self,
        url: str,
        json: dict | None = None,
        data: dict | None = None,
        timeout: int | None = None,
        headers: dict | None = None,
        api_type: str = "default",
        files: dict | None = None,
    ) -> dict[str, Any]:
        """
        HTTP POST Request mit Retry-Logik.

        Args:
            url: Ziel-URL
            json: JSON-Body
            data: Form-Data
            timeout: Timeout in Sekunden
            headers: Zusätzliche Header
            api_type: API-Typ für Timeout-Lookup
            files: Dateien für Multipart-Upload

        Returns:
            Response JSON als Dict
        """
        return self._request(
            "POST",
            url,
            json=json,
            data=data,
            timeout=timeout,
            headers=headers,
            api_type=api_type,
            files=files,
        )

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        """Interne Request-Methode mit Retry-Logik"""
        api_type = kwargs.pop("api_type", "default")
        timeout = kwargs.pop("timeout", None) or self.DEFAULT_TIMEOUTS.get(
            api_type, self.default_timeout
        )
        extra_headers = kwargs.pop("headers", None)
        files = kwargs.pop("files", None)

        if extra_headers:
            kwargs["headers"] = {**self.session.headers, **extra_headers}

        kwargs["timeout"] = timeout
        if files:
            kwargs["files"] = files

        last_exception = None
        last_status_code = None

        for attempt in range(self.max_retries):
            self.stats["requests"] += 1

            try:
                if method == "GET":
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)

                last_status_code = response.status_code

                # Erfolg
                if response.status_code == 200:
                    self.stats["successes"] += 1
                    return response.json()

                # Rate Limit
                if response.status_code == 429:
                    delay = self._calculate_delay(attempt) * 3  # Längere Pause bei Rate Limit
                    logger.warning(f"Rate limit hit for {url}, waiting {delay:.1f}s")
                    time.sleep(delay)
                    self.stats["retries"] += 1
                    continue

                # Server Error
                if 500 <= response.status_code < 600:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Server error {response.status_code} for {url}, retry in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    self.stats["retries"] += 1
                    continue

                # Client Error (nicht retry-fähig)
                self.stats["failures"] += 1
                raise HTTPClientError(f"HTTP {response.status_code}: {response.text[:200]}")

            except requests.Timeout as e:
                last_exception = e
                delay = self._calculate_delay(attempt)
                logger.warning(f"Timeout for {url} (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    self.stats["retries"] += 1

            except requests.ConnectionError as e:
                last_exception = e
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"Connection error for {url} (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    self.stats["retries"] += 1

            except requests.RequestException as e:
                last_exception = e
                logger.error(f"Request error for {url}: {e}")
                break

        # Alle Retries fehlgeschlagen
        self.stats["failures"] += 1

        if last_exception:
            raise HTTPClientError(
                f"Request failed after {self.max_retries} attempts: {last_exception}"
            )
        else:
            raise HTTPClientError(f"Request failed with status {last_status_code}")

    def get_stats(self) -> dict[str, int]:
        """Gibt Request-Statistiken zurück"""
        return {
            **self.stats,
            "success_rate": (self.stats["successes"] / max(self.stats["requests"], 1)) * 100,
        }


# Singleton-Instanz für globale Nutzung
_client_instance: HTTPClient | None = None


def get_http_client() -> HTTPClient:
    """Gibt die globale HTTPClient-Instanz zurück"""
    global _client_instance
    if _client_instance is None:
        _client_instance = HTTPClient()
    return _client_instance
