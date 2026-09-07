import time
from uuid import uuid4


def new_file_id() -> str:
    """Build a versioned transfer id: ``<nanoseconds>:<uuid4>``."""
    return f"{time.time_ns()}:{uuid4()}"
