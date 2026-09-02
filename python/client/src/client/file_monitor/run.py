import os
import socket
import time
from pathlib import Path

from client.common.ipc import connect_to_server
from client.file_monitor.monitor import FileMonitor
from client.file_monitor.transfer import transfer_file

DEFAULT_SOCKET_PATH = "/tmp/proto_ipc.sock"
DEFAULT_WATCH_DIR = "/data/out"


def get_socket_path() -> Path:
    return Path(
        os.getenv(
            "IPC_SOCKET_PATH",
            DEFAULT_SOCKET_PATH,
        )
    )


def get_watch_folder() -> Path:
    return Path(
        os.getenv(
            "UNIFLOW_WATCH_DIR",
            DEFAULT_WATCH_DIR,
        )
    )


def get_worker_count() -> int:
    workers = int(
        os.getenv(
            "UNIFLOW_WORKERS",
            "3",
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
            "1",
        )
    )

    if polling <= 0:
        raise ValueError(
            "UNIFLOW_WATCH_POLLING must be greater than 0"
        )

    return polling


def connect_to_sender(
    socket_path: Path,
) -> socket.socket:
    while True:
        try:
            return connect_to_server(socket_path)
        except (
            FileNotFoundError,
            ConnectionRefusedError,
        ):
            time.sleep(0.5)


def run_monitor(
    monitor: FileMonitor,
    connection: socket.socket,
    number_of_senders: int,
    poll_interval: float,
) -> None:
    while True:
        changed_files = monitor.get_changed_files()

        for file in changed_files:
            sender = monitor.get_sender()

            transfer_file(
                file,
                connection,
                sender,
                number_of_senders,
            )

        time.sleep(poll_interval)


def main() -> None:
    watch_folder = get_watch_folder()
    watch_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    workers = get_worker_count()

    monitor = FileMonitor(
        watch_folder,
        workers,
    )

    print(
        f"File Monitor watching {watch_folder}"
    )

    connection = connect_to_sender(
        get_socket_path()
    )

    try:
        run_monitor(
            monitor,
            connection,
            workers,
            get_poll_interval(),
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()