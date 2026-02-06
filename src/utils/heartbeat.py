"""Docker health-check heartbeat utility."""

from pathlib import Path

_HEARTBEAT_PATH = Path("data/heartbeat")


def touch_heartbeat() -> None:
    """Touch the heartbeat file for Docker health-check."""
    _HEARTBEAT_PATH.parent.mkdir(exist_ok=True)
    _HEARTBEAT_PATH.touch()
