"""Singleton mixin to eliminate boilerplate across service classes."""

from __future__ import annotations

import logging
from typing import Any, ClassVar, TypeVar, cast

logger = logging.getLogger("trading_bot")

_T = TypeVar("_T", bound="SingletonMixin")


class SingletonMixin:
    """Mixin providing get_instance() / reset_instance() singleton pattern.

    If the subclass defines a ``close()`` method, ``reset_instance()``
    will call it before clearing the reference.

    Usage::

        class MyService(SingletonMixin):
            def __init__(self): ...

            def close(self):  # optional
                ...


        svc = MyService.get_instance()
        MyService.reset_instance()
    """

    _instance: ClassVar[Any] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._instance = None

    @classmethod
    def get_instance(cls: type[_T], *args: Any, **kwargs: Any) -> _T:
        """Return the singleton instance, creating it if needed."""
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        return cast("_T", cls._instance)

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton. Calls close() if available."""
        if cls._instance is not None:
            close_fn = getattr(cls._instance, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            cls._instance = None
