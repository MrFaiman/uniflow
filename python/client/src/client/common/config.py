import os
from pathlib import Path

DEFAULT_SOCKET_PATH = "/tmp/proto_ipc.sock"
DEFAULT_WORKERS = 3
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_PORT = 9000
DEFAULT_MAX_FILE_BYTES = 1024 * 1024 * 1024
DEFAULT_REPAIR_PERCENT = 20
DEFAULT_NET_BINARY = "/usr/local/bin/uniflow-net"


def get_socket_path() -> Path:
    return Path(os.getenv("IPC_SOCKET_PATH", DEFAULT_SOCKET_PATH))


def get_sender_socket_path(worker_index: int) -> Path:
    return Path(f"{get_socket_path()}.sender.{worker_index}")


def get_worker_count() -> int:
    workers = int(os.getenv("UNIFLOW_WORKERS", str(DEFAULT_WORKERS)))
    if workers != 3:
        raise ValueError("The trio project requires exactly 3 workers")
    return workers


def get_poll_interval() -> float:
    polling = float(os.getenv("UNIFLOW_WATCH_POLLING", str(DEFAULT_POLL_INTERVAL)))
    if polling <= 0:
        raise ValueError("UNIFLOW_WATCH_POLLING must be greater than 0")
    return polling


def get_base_port() -> int:
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    if port < 1 or port > 65533:
        raise ValueError("PORT must leave room for ports PORT, PORT+1 and PORT+2")
    return port


def get_max_file_bytes() -> int:
    value = int(os.getenv("UNIFLOW_MAX_FILE_BYTES", str(DEFAULT_MAX_FILE_BYTES)))
    if value <= 0 or value > DEFAULT_MAX_FILE_BYTES:
        raise ValueError("UNIFLOW_MAX_FILE_BYTES must be between 1 and 1 GiB")
    return value


def get_repair_percent() -> int:
    value = int(os.getenv("UNIFLOW_FEC_REPAIR_PERCENT", str(DEFAULT_REPAIR_PERCENT)))
    if value < 0 or value > 200:
        raise ValueError("UNIFLOW_FEC_REPAIR_PERCENT must be between 0 and 200")
    return value


def get_net_binary() -> str:
    return os.getenv("UNIFLOW_NET_BINARY", DEFAULT_NET_BINARY)
