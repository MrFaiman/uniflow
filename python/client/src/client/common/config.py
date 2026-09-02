import os
from pathlib import Path

DEFAULT_SOCKET_PATH = "/tmp/proto_ipc.sock"
DEFAULT_WORKERS = 3
DEFAULT_POLL_INTERVAL = 1.0


def get_socket_path() -> Path:
    return Path(
        os.getenv(
            "IPC_SOCKET_PATH",
            DEFAULT_SOCKET_PATH,
        )
    )


def get_worker_count() -> int:
    workers = int(
        os.getenv(
            "UNIFLOW_WORKERS",
            str(DEFAULT_WORKERS),
        )
    )

    if workers < 1:
        raise ValueError(
            "UNIFLOW_WORKERS must be at least 1"
        )

    return workers


def get_poll_interval() -> float:
    polling = float(
        os.getenv(
            "UNIFLOW_WATCH_POLLING",
            str(DEFAULT_POLL_INTERVAL),
        )
    )

    if polling <= 0:
        raise ValueError(
            "UNIFLOW_WATCH_POLLING must be greater than 0"
        )

    return polling