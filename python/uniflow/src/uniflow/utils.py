import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def load_dot_env() -> None:
    start = Path(__file__).resolve().parent
    for directory in (start, *start.parents):
        env_file = directory / ".env"
        example = directory / ".env.example"
        if env_file.is_file():
            load_dotenv(env_file)
            return
        if example.is_file():
            load_dotenv(example)
            return


def socket_path() -> str:
    path = os.environ.get("IPC_SOCKET_PATH")
    if not path:
        raise RuntimeError("IPC_SOCKET_PATH is not set; add it to .env")
    return path


def udp_port() -> int:
    raw = os.environ.get("PORT") or os.environ.get("UDP_PORT", "9000")
    return int(raw)


def receive_dir() -> str:
    return os.environ.get("RECEIVE_DIR", "/tmp/uniflow-in")


def worker_count() -> int:
    raw = os.environ.get("UNIFLOW_WORKERS", "3")
    count = int(raw)
    if count < 3:
        raise RuntimeError("UNIFLOW_WORKERS must be at least 3")
    return count


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
