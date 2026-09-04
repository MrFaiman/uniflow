import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from uniflow.ipc import Ipc
from uniflow.transfer import (
    SMALL_FILE_MAX_BYTES,
    PairPool,
    file_size_for_event,
    transfer_mode_for_size,
    wait_until_stable,
)

logger = logging.getLogger(__name__)

_WATCHED_EVENTS = frozenset({"created", "modified", "deleted", "moved"})
_METADATA_EVENTS = frozenset({"deleted", "moved"})


class FolderEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        watch_root: Path,
        target_ip: str,
        ipc_clients: list[Ipc],
    ) -> None:
        super().__init__()
        self.watch_root = watch_root.resolve()
        self.target_ip = target_ip
        self._ipc_clients = ipc_clients
        self._object_id = 0
        self._object_id_lock = threading.Lock()
        self._pair_pool = PairPool(len(ipc_clients))
        # watchdog delivers every event on one observer thread. Transferring
        # inline there would serialize separate small files behind each other,
        # defeating the PairPool's whole purpose of letting distinct
        # Sender/Receiver pairs carry different files at the same time.
        self._transfers = ThreadPoolExecutor(
            max_workers=len(ipc_clients),
            thread_name_prefix="uniflow-transfer",
        )
        self._pending: list[Future] = []
        self._pending_lock = threading.Lock()

    def _next_object_id(self) -> int:
        with self._object_id_lock:
            self._object_id += 1
            return self._object_id

    def _relative_path(self, abs_path: str) -> str:
        return Path(abs_path).resolve().relative_to(self.watch_root).as_posix()

    def _send_coordinated(
        self,
        command: str,
        data: bytes,
        *,
        relative_path: str,
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        object_id = self._next_object_id()

        # Ipc.send blocks until its Sender has transmitted that worker's whole
        # share of the file, so dispatching these in a plain loop would make
        # the three Senders run strictly one after another. Fan out instead so
        # all three transmit over the same wall-clock window, which is the
        # point of splitting a large file across workers.
        def dispatch(ipc: Ipc) -> None:
            ipc.send(
                command,
                data,
                target_ip=self.target_ip,
                object_id=object_id,
                coordinated=True,
                relative_path=relative_path,
                dest_relative_path=dest_relative_path,
                is_directory=is_directory,
            )

        with ThreadPoolExecutor(
            max_workers=len(self._ipc_clients),
        ) as executor:
            futures = [
                executor.submit(dispatch, ipc) for ipc in self._ipc_clients
            ]
            for future in futures:
                future.result()

    def _send_single_pair(
        self,
        command: str,
        data: bytes,
        *,
        relative_path: str,
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
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
                relative_path=relative_path,
                dest_relative_path=dest_relative_path,
                is_directory=is_directory,
            )
        finally:
            self._pair_pool.release(pair)

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type not in _WATCHED_EVENTS:
            return
        if event.is_directory and event.event_type == "modified":
            return

        src = os.fsdecode(event.src_path)
        relative_path = self._relative_path(src)
        dest_relative_path = ""
        if event.event_type == "moved":
            dest = os.fsdecode(event.dest_path)
            path = f"{src}\n{dest}"
            dest_relative_path = self._relative_path(dest)
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
        is_directory = event.is_directory
        path_kwargs = {
            "relative_path": relative_path,
            "dest_relative_path": dest_relative_path,
            "is_directory": is_directory,
        }

        if command in _METADATA_EVENTS or is_directory:
            self._submit(self._send_single_pair, command, data, path_kwargs)
            return

        # Size is measured inside the transfer thread, after the file has
        # settled, so a still-being-written file is not sized (or sent) as a
        # truncated prefix. Deciding small-vs-large out here would use the
        # partial size and could route a large file down the single-pair path.
        self._submit(self._send_file, command, data, path_kwargs)

    def _send_file(
        self,
        command: str,
        data: bytes,
        *,
        relative_path: str,
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        path = data.decode()
        # A move carries "src\ndest"; the destination is what settles.
        target = path.split("\n", 1)[1] if command == "moved" else path
        settle_path = Path(target)
        if not wait_until_stable(settle_path):
            logger.warning("skipping unstable or vanished file %s", settle_path)
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

        path_kwargs = {
            "relative_path": relative_path,
            "dest_relative_path": dest_relative_path,
            "is_directory": is_directory,
        }

        # Called directly rather than re-submitted: this already runs on a
        # transfer thread, and one future per file keeps flush() meaningful.
        if mode == "single_pair":
            self._send_single_pair(command, data, **path_kwargs)
        else:
            logger.info(
                "coordinated transfer size=%d object threshold=%d",
                size,
                SMALL_FILE_MAX_BYTES,
            )
            self._send_coordinated(command, data, **path_kwargs)

    def _submit(
        self,
        func,  # noqa: ANN001 - bound method taking (command, data, **kwargs)
        command: str,
        data: bytes,
        path_kwargs: dict,
    ) -> None:
        def run() -> None:
            try:
                func(command, data, **path_kwargs)
            except Exception:
                logger.exception("transfer failed for %s", path_kwargs)

        future = self._transfers.submit(run)
        with self._pending_lock:
            self._pending = [f for f in self._pending if not f.done()]
            self._pending.append(future)

    def flush(self) -> None:
        """Block until every dispatched transfer has finished."""
        with self._pending_lock:
            pending = list(self._pending)
        for future in pending:
            future.result()

    def shutdown(self) -> None:
        self._transfers.shutdown(wait=True)


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
    watch_root = folder.expanduser().resolve()
    handler = FolderEventHandler(watch_root, target_ip, ipc_clients)
    observer = _make_observer()
    observer.schedule(handler, str(watch_root), recursive=True)
    observer.start()
    logger.info("watching %s target_ip=%s", watch_root, target_ip)
    try:
        while observer.is_alive():
            observer.join(timeout=0.5)
    except KeyboardInterrupt:
        logger.info("stopping watcher")
    finally:
        observer.stop()
        observer.join()
        handler.shutdown()