from __future__ import annotations

import os
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from client.common.round_robin import round_robin

FileSignature = tuple[int, int]

_WATCHED_EVENTS = frozenset({"created", "modified", "deleted", "moved"})


class _FolderEventHandler(FileSystemEventHandler):
    def __init__(self, monitor: FileMonitor) -> None:
        super().__init__()
        self._monitor = monitor

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in _WATCHED_EVENTS:
            return

        src = Path(os.fsdecode(event.src_path)).resolve()

        if event.event_type == "deleted":
            self._monitor.note_deleted(src)
            return

        if event.event_type == "moved":
            dest = Path(os.fsdecode(event.dest_path)).resolve()
            self._monitor.note_deleted(src)
            self._monitor.note_changed(dest)
            return

        self._monitor.note_changed(src)


class FileMonitor:
    def __init__(
        self,
        watch_folder: Path,
        number_of_senders: int = 3,
        stable_scans: int = 2,
        *,
        use_watchdog: bool = False,
    ) -> None:
        self.watch_folder = watch_folder.resolve()
        self.stable_scans = stable_scans
        self.use_watchdog = use_watchdog
        self.known_files: dict[Path, FileSignature] = {}
        self.pending: dict[Path, tuple[FileSignature, int]] = {}
        self.deleted_files: set[Path] = set()
        self.round_robin = round_robin(number_of_senders)

        self._lock = threading.Lock()
        self._dirty: set[Path] = set()
        self._wake = threading.Event()
        self._observer: Observer | None = None

        if use_watchdog:
            self._start_observer()
            self._bootstrap_existing_files()

    def _bootstrap_existing_files(self) -> None:
        for file in self.get_files():
            self.note_changed(file)

    def _start_observer(self) -> None:
        handler = _FolderEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.watch_folder), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        observer = self._observer
        self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)

    def wait(self, timeout: float) -> None:
        """Block until a filesystem event arrives or ``timeout`` elapses."""
        self._wake.wait(timeout=timeout)
        self._wake.clear()

    def note_changed(self, file: Path) -> None:
        file = file.resolve()
        if not self._is_under_watch_folder(file):
            return

        with self._lock:
            self.deleted_files.discard(file)
            self._dirty.add(file)
        self._wake.set()

    def note_deleted(self, file: Path) -> None:
        file = file.resolve()
        if not self._is_under_watch_folder(file):
            return

        with self._lock:
            self._dirty.discard(file)
            self.pending.pop(file, None)
            if file in self.known_files:
                self.known_files.pop(file, None)
                self.deleted_files.add(file)
            elif file in self.deleted_files:
                pass
            # Unknown paths that were never transferred do not need a DELETE.
        self._wake.set()

    def _is_under_watch_folder(self, file: Path) -> bool:
        try:
            file.relative_to(self.watch_folder)
            return True
        except ValueError:
            return False

    def get_files(self) -> list[Path]:
        return sorted(item for item in self.watch_folder.rglob("*") if item.is_file())

    @staticmethod
    def _signature(file: Path) -> FileSignature:
        stat = file.stat()
        return stat.st_size, stat.st_mtime_ns

    def get_changed_files(self) -> list[Path]:
        # Events wake processing; reconciliation also catches dropped notifications
        # and directory moves on Docker bind mounts and network filesystems.
        with self._lock:
            self._dirty.clear()
            return self._get_changed_files_from_scan()

    def _get_changed_files_from_scan(self) -> list[Path]:
        changed_files: list[Path] = []
        current_files = set(self.get_files())

        # If a path was recreated before a pending DELETE was sent,
        # the final desired state is "file exists", so cancel that delete.
        for file in current_files:
            self.deleted_files.discard(file)

        for file in current_files:
            try:
                signature = self._signature(file)
            except FileNotFoundError:
                continue

            if self.known_files.get(file) == signature:
                self.pending.pop(file, None)
                continue

            previous_signature, count = self.pending.get(file, (signature, 0))
            if previous_signature == signature:
                count += 1
            else:
                count = 1

            if count >= self.stable_scans:
                changed_files.append(file)
                self.known_files[file] = signature
                self.pending.pop(file, None)
            else:
                self.pending[file] = (signature, count)

        missing = set(self.known_files) - current_files
        for file in missing:
            self.known_files.pop(file, None)
            self.pending.pop(file, None)
            self.deleted_files.add(file)

        for file in set(self.pending) - current_files:
            self.pending.pop(file, None)

        return sorted(changed_files)

    def get_deleted_files(self) -> list[Path]:
        # Do not clear here. A failed DELETE transmission must be retried.
        with self._lock:
            return sorted(self.deleted_files)

    def mark_delete_sent(self, file: Path) -> None:
        with self._lock:
            self.deleted_files.discard(file.resolve())

    def mark_failed(self, file: Path) -> None:
        file = file.resolve()
        with self._lock:
            # The receiver may already have an earlier version or a partial write.
            self.known_files[file] = (-1, -1)
            self.pending.pop(file, None)
            self._dirty.add(file)
        self._wake.set()

    def get_sender(self) -> int:
        return next(self.round_robin)
