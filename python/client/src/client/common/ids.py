import time
from threading import Lock
from uuid import uuid4

_lock = Lock()
_last_version = 0


def new_file_id() -> str:
    """Build a versioned transfer id: ``<nanoseconds>:<uuid4>``."""
    global _last_version
    with _lock:
        _last_version = max(time.time_ns(), _last_version + 1)
        return f"{_last_version}:{uuid4()}"
