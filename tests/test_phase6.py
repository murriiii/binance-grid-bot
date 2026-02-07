"""Tests for Phase 6: Entry Point, Task Locking, Telegram Validation."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from src.notifications.telegram_service import TELEGRAM_MAX_MESSAGE_LENGTH, TelegramService
from src.utils.task_lock import task_locked

# ═══════════════════════════════════════════════════════════════
# 6.1: main_hybrid.py Entry Point
# ═══════════════════════════════════════════════════════════════


class TestMainHybrid:
    def test_import_main_hybrid(self):
        """main_hybrid module can be imported."""
        import main_hybrid

        assert hasattr(main_hybrid, "main")

    @patch("src.core.cohort_orchestrator.CohortOrchestrator")
    @patch("src.api.binance_client.BinanceClient")
    def test_main_creates_cohort_orchestrator(self, mock_client_cls, mock_co_cls):
        """main() creates a CohortOrchestrator and calls run()."""
        import main_hybrid

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_co = MagicMock()
        mock_co.initialize.return_value = True
        mock_co.initial_allocation.return_value = 4
        mock_co.orchestrators = {"a": MagicMock(), "b": MagicMock()}
        mock_co.cohort_configs = {
            "a": {"current_capital": 100, "grid_range_pct": 5, "risk_tolerance": "medium"},
        }
        mock_co_cls.return_value = mock_co

        with patch("main_hybrid.load_dotenv"):
            main_hybrid.main()

        mock_co.initialize.assert_called_once()
        mock_co.initial_allocation.assert_called_once()
        mock_co.run.assert_called_once()

    @patch("src.core.cohort_orchestrator.CohortOrchestrator")
    @patch("src.api.binance_client.BinanceClient")
    def test_main_exits_when_no_cohorts_initialized(self, mock_client_cls, mock_co_cls):
        """main() exits when no cohorts could be initialized."""
        import main_hybrid

        mock_co = MagicMock()
        mock_co.initialize.return_value = False
        mock_co_cls.return_value = mock_co

        with patch("main_hybrid.load_dotenv"), pytest.raises(SystemExit) as exc_info:
            main_hybrid.main()

        assert exc_info.value.code == 1

    @patch("src.core.cohort_orchestrator.CohortOrchestrator")
    @patch("src.api.binance_client.BinanceClient")
    def test_main_exits_when_no_allocations(self, mock_client_cls, mock_co_cls):
        """main() exits when no cohorts get allocations."""
        import main_hybrid

        mock_co = MagicMock()
        mock_co.initialize.return_value = True
        mock_co.initial_allocation.return_value = 0
        mock_co.orchestrators = {"a": MagicMock()}
        mock_co.cohort_configs = {
            "a": {"current_capital": 100, "grid_range_pct": 5, "risk_tolerance": "medium"},
        }
        mock_co_cls.return_value = mock_co

        with patch("main_hybrid.load_dotenv"), pytest.raises(SystemExit) as exc_info:
            main_hybrid.main()

        assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════
# 6.2: Task Locking (B3)
# ═══════════════════════════════════════════════════════════════


class TestTaskLocking:
    def test_task_locked_prevents_concurrent_execution(self):
        """task_locked prevents a task from running concurrently."""
        call_count = 0
        started = threading.Event()
        proceed = threading.Event()

        @task_locked
        def slow_task():
            nonlocal call_count
            call_count += 1
            started.set()
            proceed.wait(timeout=5)

        # Start first execution in a thread
        t1 = threading.Thread(target=slow_task)
        t1.start()
        started.wait(timeout=5)

        # Try second execution - should be skipped
        slow_task()

        # Let first finish
        proceed.set()
        t1.join(timeout=5)

        assert call_count == 1

    def test_task_locked_allows_sequential_execution(self):
        """task_locked allows the same task to run after the first finishes."""
        call_count = 0

        @task_locked
        def quick_task():
            nonlocal call_count
            call_count += 1

        quick_task()
        quick_task()

        assert call_count == 2

    def test_task_locked_independent_tasks(self):
        """Different tasks have independent locks."""
        results = []

        @task_locked
        def task_a():
            results.append("a")

        @task_locked
        def task_b():
            results.append("b")

        task_a()
        task_b()

        assert results == ["a", "b"]

    def test_task_locked_releases_on_exception(self):
        """Lock is released even when task raises an exception."""
        call_count = 0

        @task_locked
        def failing_task():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("test error")

        with pytest.raises(ValueError):
            failing_task()

        # Should be able to run again after failure
        failing_task()
        assert call_count == 2

    def test_task_locked_preserves_function_name(self):
        """task_locked preserves the original function name."""

        @task_locked
        def my_special_task():
            pass

        assert my_special_task.__name__ == "my_special_task"


# ═══════════════════════════════════════════════════════════════
# 6.3: Telegram Message Length Validation (B4)
# ═══════════════════════════════════════════════════════════════


class TestTelegramMessageLength:
    def test_max_length_constant(self):
        """TELEGRAM_MAX_MESSAGE_LENGTH is 4096."""
        assert TELEGRAM_MAX_MESSAGE_LENGTH == 4096

    @patch("src.notifications.telegram_service.get_http_client")
    def test_short_message_not_truncated(self, mock_http):
        """Short messages are sent as-is."""
        mock_client = MagicMock()
        mock_http.return_value = mock_client

        service = TelegramService()
        service.enabled = True
        service.token = "test"
        service.chat_id = "123"
        service.http = mock_client

        service.send("Hello World")

        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["text"]
        assert sent_text == "Hello World"

    @patch("src.notifications.telegram_service.get_http_client")
    def test_long_message_truncated(self, mock_http):
        """Messages exceeding 4096 chars are truncated."""
        mock_client = MagicMock()
        mock_http.return_value = mock_client

        service = TelegramService()
        service.enabled = True
        service.token = "test"
        service.chat_id = "123"
        service.http = mock_client

        long_message = "x" * 5000
        service.send(long_message)

        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["text"]

        assert len(sent_text) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert sent_text.endswith("<i>...truncated</i>")

    @patch("src.notifications.telegram_service.get_http_client")
    def test_exact_limit_not_truncated(self, mock_http):
        """Message at exactly 4096 chars is not truncated."""
        mock_client = MagicMock()
        mock_http.return_value = mock_client

        service = TelegramService()
        service.enabled = True
        service.token = "test"
        service.chat_id = "123"
        service.http = mock_client

        exact_message = "x" * TELEGRAM_MAX_MESSAGE_LENGTH
        service.send(exact_message)

        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["text"]

        assert len(sent_text) == TELEGRAM_MAX_MESSAGE_LENGTH
        assert "truncated" not in sent_text

    @patch("src.notifications.telegram_service.get_http_client")
    def test_truncated_message_preserves_html(self, mock_http):
        """Truncated messages have proper HTML suffix."""
        mock_client = MagicMock()
        mock_http.return_value = mock_client

        service = TelegramService()
        service.enabled = True
        service.token = "test"
        service.chat_id = "123"
        service.http = mock_client

        long_message = "<b>Header</b>\n" + "data " * 1000
        service.send(long_message)

        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["text"]

        assert len(sent_text) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert "<i>...truncated</i>" in sent_text

    @patch("src.notifications.telegram_service.get_http_client")
    def test_disabled_service_skips_truncation(self, mock_http):
        """Disabled service returns False without truncating."""
        service = TelegramService()
        service.enabled = False

        result = service.send("x" * 5000)
        assert result is False
