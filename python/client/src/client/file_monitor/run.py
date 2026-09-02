import socket
import time
from pathlib import Path

from client.common.config import (
    get_poll_interval,
    get_socket_path,
    get_worker_count,
)
from client.common.go_daemon import run_go_daemon
from client.common.ipc import connect_to_server
from client.file_monitor.monitor import FileMonitor
from client.file_monitor.transfer import transfer_file


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
            print("Waiting for Sender...")
            time.sleep(1)


def monitor_files(
    monitor: FileMonitor,
    connection: socket.socket,
    workers: int,
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
                workers,
            )

        time.sleep(poll_interval)


def run_file_monitor(
    watch_folder: Path,
    target_ip: str | None = None,
) -> None:
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
        f"Watching folder: {watch_folder}"
    )

    send_args = ["send", str(watch_folder)]
    if target_ip:
        send_args.append(target_ip)

    with run_go_daemon(*send_args):
        connection = connect_to_sender(
            get_socket_path()
        )

        try:
            monitor_files(
                monitor,
                connection,
                workers,
                get_poll_interval(),
            )

        finally:
            connection.close()