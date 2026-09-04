import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SMALL_FILE_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_LARGE_FILE_MAX_BYTES = 1 * 1024 * 1024 * 1024
LARGE_FILE_MAX_BYTES = _DEFAULT_LARGE_FILE_MAX_BYTES


def large_file_max_bytes() -> int:
    return int(
        os.environ.get(
            "UNIFLOW_MAX_FILE_BYTES",
            str(_DEFAULT_LARGE_FILE_MAX_BYTES),
        ),
    )


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


def wait_until_stable(
    path: Path,
    quiet_period: float = 0.6,
    timeout: float = 300.0,
    poll_interval: float = 0.2,
) -> bool:
    """Wait until a file stops changing, so it is not sent mid-write.

    A watcher fires as soon as a file appears, which for a large copy is long
    before the last byte is written. Transferring then sends a truncated
    prefix — and because the sender hashes whatever it read, the receiver
    happily verifies that truncated content as correct. Observed with a 1 GiB
    file: a 326 MiB partial transfer completed with "HASH OK" before the real
    one. Whether the truncated or the complete copy lands last is pure timing.

    Returns True once size and mtime hold steady for quiet_period, False if
    the file is still changing at timeout or disappeared.
    """
    deadline = time.monotonic() + timeout
    last: tuple[int, float] | None = None
    stable_since: float | None = None

    while time.monotonic() < deadline:
        try:
            stat = path.stat()
        except OSError:
            return False
        current = (stat.st_size, stat.st_mtime)
        now = time.monotonic()
        if current == last:
            if stable_since is not None and now - stable_since >= quiet_period:
                return True
        else:
            last = current
            stable_since = now
        time.sleep(poll_interval)

    logger.warning("file %s still changing after %.0fs", path, timeout)
    return False


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
    max_bytes = large_file_max_bytes()
    if size > max_bytes:
        raise ValueError(
            f"file size {size} exceeds maximum {max_bytes} bytes",
        )
    if size < SMALL_FILE_MAX_BYTES:
        return "single_pair"
    return "coordinated"
