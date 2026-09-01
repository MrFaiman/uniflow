import socket
import time
from pathlib import Path

from client.common.ipc import connect_to_server
from client.file_monitor.monitor import FileMonitor
from client.file_monitor.transfer import transfer_file

SOCKET_PATHS = [
    Path("/tmp/uniflow_sender_0.sock"),
    Path("/tmp/uniflow_sender_1.sock"),
    Path("/tmp/uniflow_sender_2.sock"),
]


def run_monitor(
    monitor: FileMonitor,
    connections: list[socket.socket],
) -> None:
    while True:
        changed_files = monitor.get_changed_files()

        for file in changed_files:
            sender = monitor.get_sender()

            transfer_file(
                file,
                connections,
                sender,
            )

        time.sleep(1)


def main() -> None:
    watch_folder = Path("files_to_send")
    watch_folder.mkdir(exist_ok=True)

    connections = []

    for socket_path in SOCKET_PATHS:
        connection = connect_to_server(socket_path)
        connections.append(connection)

    print("File Monitor is running")

    try:
        run_monitor(
            FileMonitor(watch_folder),
            connections,
        )
    finally:
        for connection in connections:
            connection.close()


if __name__ == "__main__":
    main()