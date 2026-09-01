import socket
import time

from client.file_monitor.monitor import FileMonitor
from client.file_monitor.transfer import transfer_file


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