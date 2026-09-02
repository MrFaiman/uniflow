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
        self._pair_pool = PairPool(len(ipc_clients))

    def _next_object_id(self) -> int:
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
        for ipc in self._ipc_clients:
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
            self._send_single_pair(command, data, **path_kwargs)
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
            self._send_single_pair(command, data, **path_kwargs)
        else:
            logger.info(
                "coordinated transfer size=%d object threshold=%d",
                size,
                10 * 1024 * 1024,
            )
            self._send_coordinated(command, data, **path_kwargs)


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

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # הגדרת נתיבים וכתובות יעד מתוך הארגומנטים
    folder_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/out")
    target = sys.argv[2] if len(sys.argv) > 2 else "router"
    
    # שאיבת מספר הוורקרים ממשתני הסביבה (כברירת מחדל 3)
    workers = int(os.environ.get("UNIFLOW_WORKERS", "3"))
    
    logger.info("Initializing %d IPC clients...", workers)
    # יצירת מופעי ה-IPC הדרושים לארכיטקטורת ה-PairPool
    ipc_clients = [Ipc() for _ in range(workers)]
    
    logger.info("Starting watch_folder on %s with target %s", folder_path, target)
    watch_folder(folder_path, target, ipc_clients)