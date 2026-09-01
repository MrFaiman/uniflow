import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SMALL_FILE_MAX_BYTES = 10 * 1024 * 1024
LARGE_FILE_MAX_BYTES = 1 * 1024 * 1024 * 1024


class PairPool:
    def __init__(self, size: int) -> None:
        self._lock = threading.Lock()
        self._available = list(range(size))

    def acquire(self, timeout: float = 300.0) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                if self._available:
                    return self._available.pop(0)
            time.sleep(0.05)
        raise RuntimeError("no worker pair available")

    def release(self, index: int) -> None:
        with self._lock:
            if index not in self._available:
                self._available.append(index)


def file_size_for_event(path_text: str, event_type: str) -> int | None:
    if event_type == "deleted":
        return None
    if event_type == "moved":
        path_text = path_text.split("\n", 1)[1]
    path = Path(path_text)
    if not path.is_file():
        return None
    return path.stat().st_size


def transfer_mode_for_size(size: int) -> str:
    if size > LARGE_FILE_MAX_BYTES:
        raise ValueError(
            f"file size {size} exceeds maximum {LARGE_FILE_MAX_BYTES} bytes",
        )
    if size < SMALL_FILE_MAX_BYTES:
        return "single_pair"
    return "coordinated"
