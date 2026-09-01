import logging
import os
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from uniflow.ipc import Ipc
from uniflow.transfer import (
    PairPool,
    file_size_for_event,
    transfer_mode_for_size,
)

logger = logging.getLogger(__name__)

_WATCHED_EVENTS = frozenset({"created", "modified", "deleted", "moved"})


class FolderEventHandler(FileSystemEventHandler):
    def __init__(self, target_ip: str, ipc_clients: list[Ipc]) -> None:
        super().__init__()
        self.target_ip = target_ip
        self._ipc_clients = ipc_clients
        self._object_id = 0
        self._pair_pool = PairPool(len(ipc_clients))

    def _next_object_id(self) -> int:
        self._object_id += 1
        return self._object_id

    def _send_coordinated(self, command: str, data: bytes) -> None:
        object_id = self._next_object_id()
        for ipc in self._ipc_clients:
            ipc.send(
                command,
                data,
                target_ip=self.target_ip,
                object_id=object_id,
                coordinated=True,
            )

    def _send_single_pair(self, command: str, data: bytes) -> None:
        pair = self._pair_pool.acquire()
        object_id = self._next_object_id()
        try:
            logger.info(
                "single-pair transfer pair=%d object_id=%d",
                pair,
                object_id,
            )
            self._ipc_clients[pair].send(
                command,
                data,
                target_ip=self.target_ip,
                object_id=object_id,
                coordinated=False,
            )
        finally:
            self._pair_pool.release(pair)

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in _WATCHED_EVENTS:
            return
        src = os.fsdecode(event.src_path)
        if event.event_type == "moved":
            dest = os.fsdecode(event.dest_path)
            path = f"{src}\n{dest}"
        else:
            path = src
        logger.info(
            "%s %s target_ip=%s",
            event.event_type,
            path,
            self.target_ip,
        )
        data = path.encode()
        command = event.event_type

        if command == "deleted":
            self._send_single_pair(command, data)
            return

        size = file_size_for_event(path, command)
        if size is None:
            logger.warning("could not determine file size for %s", path)
            return

        try:
            mode = transfer_mode_for_size(size)
        except ValueError as err:
            logger.error("%s", err)
            return

        if mode == "single_pair":
            self._send_single_pair(command, data)
        else:
            logger.info(
                "coordinated transfer size=%d object threshold=%d",
                size,
                10 * 1024 * 1024,
            )
            self._send_coordinated(command, data)


def _make_observer() -> Observer:
    if os.environ.get("UNIFLOW_WATCH_POLLING") == "1":
        logger.info("using polling observer for file watch")
        return PollingObserver()
    return Observer()


def watch_folder(
    folder: Path,
    target_ip: str,
    ipc_clients: list[Ipc],
) -> None:
    handler = FolderEventHandler(target_ip, ipc_clients)
    observer = _make_observer()
    observer.schedule(handler, str(folder), recursive=True)
    observer.start()
    logger.info("watching %s target_ip=%s", folder, target_ip)
    try:
        while observer.is_alive():
            observer.join(timeout=0.5)
    except KeyboardInterrupt:
        logger.info("stopping watcher")
    finally:
        observer.stop()
        observer.join()
