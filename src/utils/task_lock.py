"""Task locking utility to prevent concurrent execution of scheduled tasks (B3)."""

import functools
import logging
import threading

logger = logging.getLogger("trading_bot")

_task_locks: dict[str, threading.Lock] = {}


def task_locked(func):
    """Prevent concurrent execution of the same task.

    If a task is already running when called again, the second
    invocation is skipped with a warning log.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        lock_key = func.__name__
        if lock_key not in _task_locks:
            _task_locks[lock_key] = threading.Lock()
        lock = _task_locks[lock_key]
        if not lock.acquire(blocking=False):
            logger.warning(f"Task {lock_key} already running, skipping")
            return
        try:
            return func(*args, **kwargs)
        finally:
            lock.release()

    return wrapper
