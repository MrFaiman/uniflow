import logging
import os
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from client.ipc import Ipc

logger = logging.getLogger(__name__)

_WATCHED_EVENTS = frozenset({"created", "modified", "deleted", "moved"})


class FolderEventHandler(FileSystemEventHandler):
    def __init__(self, target_ip: str) -> None:
        super().__init__()
        self.target_ip = target_ip

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
            "%s %s target_ip=%s", event.event_type, path, self.target_ip
        )
        Ipc.send(event.event_type, path.encode())


def watch_folder(folder: Path, target_ip: str) -> None:
    handler = FolderEventHandler(target_ip)
    observer = Observer()
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


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    folder_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/out")
    target = sys.argv[2] if len(sys.argv) > 2 else "router"
    
    logger.info("Starting watch_folder on %s with target %s", folder_path, target)
    watch_folder(folder_path, target)