"""
Tests für src/api/http_client.py
"""

from unittest.mock import MagicMock, patch

import pytest
import requests


class TestCachedDecorator:
    """Tests für den @cached Decorator"""

    def test_caches_result(self, reset_new_singletons):
        """Testet dass Ergebnisse gecached werden"""
        from src.api.http_client import cached

        call_count = 0

        @cached(ttl_seconds=60)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Erster Aufruf
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Zweiter Aufruf - sollte aus Cache kommen
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Kein neuer Aufruf

    def test_different_args_not_cached(self, reset_new_singletons):
        """Testet dass verschiedene Argumente unterschiedlich gecached werden"""
        from src.api.http_client import cached

        call_count = 0

        @cached(ttl_seconds=60)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x

        func(1)
        func(2)
        func(1)  # Sollte aus Cache kommen

        assert call_count == 2

    def test_clear_cache(self, reset_new_singletons):
        """Testet clear_cache Funktion"""
        from src.api.http_client import cached

        call_count = 0

        @cached(ttl_seconds=60)
        def func():
            nonlocal call_count
            call_count += 1
            return "result"

        func()
        func()
        assert call_count == 1

        func.clear_cache()
        func()
        assert call_count == 2


class TestHTTPClient:
    """Tests für HTTPClient"""

    def test_singleton_pattern(self, reset_new_singletons):
        """Testet Singleton-Pattern"""
        from src.api.http_client import get_http_client

        client1 = get_http_client()
        client2 = get_http_client()

        assert client1 is client2

    def test_default_timeouts(self, reset_new_singletons):
        """Testet Standard-Timeouts"""
        from src.api.http_client import HTTPClient

        client = HTTPClient()

        assert client.DEFAULT_TIMEOUTS["default"] == 10
        assert client.DEFAULT_TIMEOUTS["deepseek"] == 30
        assert client.DEFAULT_TIMEOUTS["binance"] == 10
        assert client.DEFAULT_TIMEOUTS["telegram"] == 10

    def test_initial_stats(self, reset_new_singletons):
        """Testet initiale Statistiken"""
        from src.api.http_client import HTTPClient

        client = HTTPClient()

        assert client.stats["requests"] == 0
        assert client.stats["successes"] == 0
        assert client.stats["retries"] == 0
        assert client.stats["failures"] == 0

    @patch("requests.Session.get")
    def test_successful_get_request(self, mock_get, reset_new_singletons):
        """Testet erfolgreichen GET Request"""
        from src.api.http_client import HTTPClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response

        client = HTTPClient()
        result = client.get("https://api.example.com/test")

        assert result == {"data": "test"}
        assert client.stats["successes"] == 1

    @patch("requests.Session.post")
    def test_successful_post_request(self, mock_post, reset_new_singletons):
        """Testet erfolgreichen POST Request"""
        from src.api.http_client import HTTPClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        client = HTTPClient()
        result = client.post("https://api.example.com/test", json={"key": "value"})

        assert result == {"status": "ok"}
        assert client.stats["successes"] == 1

    @patch("requests.Session.get")
    def test_retry_on_timeout(self, mock_get, reset_new_singletons):
        """Testet Retry bei Timeout"""
        from src.api.http_client import HTTPClient, HTTPClientError

        mock_get.side_effect = requests.Timeout()

        client = HTTPClient(max_retries=2, base_delay=0.01)

        with pytest.raises(HTTPClientError) as exc_info:
            client.get("https://api.example.com/test")

        assert "failed after" in str(exc_info.value)
        assert client.stats["retries"] >= 1

    @patch("requests.Session.get")
    def test_retry_on_server_error(self, mock_get, reset_new_singletons):
        """Testet Retry bei Server Error"""
        from src.api.http_client import HTTPClient, HTTPClientError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        client = HTTPClient(max_retries=2, base_delay=0.01)

        with pytest.raises(HTTPClientError):
            client.get("https://api.example.com/test")

        assert client.stats["retries"] >= 1

    @patch("requests.Session.get")
    def test_no_retry_on_client_error(self, mock_get, reset_new_singletons):
        """Testet kein Retry bei Client Error (4xx außer 429)"""
        from src.api.http_client import HTTPClient, HTTPClientError

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response

        client = HTTPClient(max_retries=3, base_delay=0.01)

        with pytest.raises(HTTPClientError) as exc_info:
            client.get("https://api.example.com/test")

        assert "404" in str(exc_info.value)
        # Sollte sofort fehlschlagen ohne Retries
        assert client.stats["retries"] == 0

    @patch("requests.Session.get")
    def test_rate_limit_handling(self, mock_get, reset_new_singletons):
        """Testet Rate Limit (429) Handling"""
        from src.api.http_client import HTTPClient, HTTPClientError

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate Limited"
        mock_get.return_value = mock_response

        client = HTTPClient(max_retries=2, base_delay=0.01, max_delay=0.05)

        with pytest.raises(HTTPClientError):
            client.get("https://api.example.com/test")

        # Rate Limit sollte Retries auslösen
        assert client.stats["retries"] >= 1

    @patch("requests.Session.get")
    def test_api_type_timeout(self, mock_get, reset_new_singletons):
        """Testet API-spezifische Timeouts"""
        from src.api.http_client import HTTPClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        client = HTTPClient()
        client.get("https://api.example.com/test", api_type="deepseek")

        # Prüfe dass der richtige Timeout verwendet wurde
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 30  # deepseek timeout

    def test_calculate_delay(self, reset_new_singletons):
        """Testet Exponential Backoff Berechnung"""
        from src.api.http_client import HTTPClient

        client = HTTPClient(base_delay=1.0, max_delay=30.0)

        assert client._calculate_delay(0) == 1.0  # 1 * 2^0 = 1
        assert client._calculate_delay(1) == 2.0  # 1 * 2^1 = 2
        assert client._calculate_delay(2) == 4.0  # 1 * 2^2 = 4
        assert client._calculate_delay(5) == 30.0  # Max capped at 30

    def test_get_stats(self, reset_new_singletons):
        """Testet Statistik-Abruf"""
        from src.api.http_client import HTTPClient

        client = HTTPClient()
        client.stats["requests"] = 100
        client.stats["successes"] = 95
        client.stats["failures"] = 5

        stats = client.get_stats()

        assert stats["requests"] == 100
        assert stats["successes"] == 95
        assert stats["success_rate"] == 95.0


class TestHTTPClientExceptions:
    """Tests für HTTP Client Exceptions"""

    def test_http_client_error(self, reset_new_singletons):
        """Testet HTTPClientError"""
        from src.api.http_client import HTTPClientError

        error = HTTPClientError("Test error")
        assert str(error) == "Test error"

    def test_rate_limit_error(self, reset_new_singletons):
        """Testet RateLimitError"""
        from src.api.http_client import RateLimitError

        error = RateLimitError("Rate limited")
        assert str(error) == "Rate limited"

    def test_timeout_error(self, reset_new_singletons):
        """Testet TimeoutError"""
        from src.api.http_client import TimeoutError

        error = TimeoutError("Request timed out")
        assert str(error) == "Request timed out"
