import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from client.common.config import (
    get_max_file_bytes,
    get_poll_interval,
    get_worker_count,
)
from client.common.ipc import connect_to_server
from client.file_monitor.monitor import FileMonitor
from client.file_monitor.packet_router import SMALL_FILE_LIMIT
from client.file_monitor.transfer import transfer_delete, transfer_file
from client.supervisor import SenderSupervisor


def connect_to_sender(socket_path: Path) -> socket.socket:
    while True:
        try:
            return connect_to_server(socket_path)
        except (FileNotFoundError, ConnectionRefusedError, TimeoutError, OSError):
            print(f"Waiting for Sender socket {socket_path}...", flush=True)
            time.sleep(0.2)


def _transfer_small_batch(
    files: list[Path],
    monitor: FileMonitor,
    connections: list[socket.socket],
    watch_folder: Path,
) -> None:
    assignments = [(file, monitor.get_sender()) for file in files]

    with ThreadPoolExecutor(max_workers=len(assignments)) as executor:
        future_to_file = {
            executor.submit(
                transfer_file,
                file,
                connections,
                sender,
                watch_folder,
            ): file
            for file, sender in assignments
        }

        for future in as_completed(future_to_file):
            file = future_to_file[future]
            try:
                packet_count = future.result()
                print(
                    f"Sent small file {file} in {packet_count} packets",
                    flush=True,
                )
            except Exception as error:
                monitor.mark_failed(file)
                print(f"Transfer failed for {file}: {error}", flush=True)


def _transfer_deletes(
    files: list[Path],
    monitor: FileMonitor,
    connections: list[socket.socket],
    watch_folder: Path,
) -> None:
    for file in files:
        try:
            packet_count = transfer_delete(file, connections, watch_folder)
            monitor.mark_delete_sent(file)
            print(
                f"Sent delete for {file} through {packet_count} Sender paths",
                flush=True,
            )
        except Exception as error:
            # Leave the path in monitor.deleted_files so it is retried.
            print(f"Delete transfer failed for {file}: {error}", flush=True)


def monitor_files(
    monitor: FileMonitor,
    connections: list[socket.socket],
    supervisor: SenderSupervisor,
    watch_folder: Path,
) -> None:
    workers = len(connections)
    max_size = get_max_file_bytes()

    while True:
        supervisor.check()
        changed_files = monitor.get_changed_files()
        deleted_files = monitor.get_deleted_files()

        if deleted_files:
            _transfer_deletes(
                deleted_files,
                monitor,
                connections,
                watch_folder,
            )
            supervisor.check()

        small_files: list[Path] = []
        large_files: list[Path] = []

        for file in changed_files:
            try:
                size = file.stat().st_size
            except FileNotFoundError:
                monitor.mark_failed(file)
                continue

            if size > max_size:
                print(f"Skipping {file}: larger than 1 GiB", flush=True)
            elif size < SMALL_FILE_LIMIT:
                small_files.append(file)
            else:
                large_files.append(file)

        for start in range(0, len(small_files), workers):
            _transfer_small_batch(
                small_files[start : start + workers],
                monitor,
                connections,
                watch_folder,
            )
            supervisor.check()

        for file in large_files:
            try:
                packets = transfer_file(file, connections, 0, watch_folder)
                print(f"Sent large file {file} in {packets} packets", flush=True)
            except Exception as error:
                monitor.mark_failed(file)
                print(f"Transfer failed for {file}: {error}", flush=True)
            supervisor.check()

        time.sleep(get_poll_interval())


def run_file_monitor(watch_folder: Path, router_host: str) -> None:
    watch_folder = watch_folder.resolve()
    watch_folder.mkdir(parents=True, exist_ok=True)

    workers = get_worker_count()
    monitor = FileMonitor(watch_folder, workers)
    supervisor = SenderSupervisor(router_host)
    connections: list[socket.socket] = []

    try:
        socket_paths = supervisor.start()
        connections = [connect_to_sender(path) for path in socket_paths]
        print(f"Watching folder: {watch_folder}", flush=True)
        monitor_files(monitor, connections, supervisor, watch_folder)
    except KeyboardInterrupt:
        print("Stopping File Monitor", flush=True)
    finally:
        for connection in connections:
            connection.close()
        supervisor.stop()

