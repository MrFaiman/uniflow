from pathlib import Path

from client.common.round_robin import round_robin


class FileMonitor:
    def __init__(self, watch_folder: Path):
        self.watch_folder = watch_folder
        self.known_files = {}
        self.round_robin = round_robin(3)

    def get_files(self) -> list[Path]:
        files = []

        for item in self.watch_folder.iterdir():
            if item.is_file():
                files.append(item)

        return files

    def get_changed_files(self) -> list[Path]:
        changed_files = []

        for file in self.get_files():
            modified_time = file.stat().st_mtime_ns

            if (
                file not in self.known_files
                or self.known_files[file] != modified_time
            ):
                changed_files.append(file)

            self.known_files[file] = modified_time

        return changed_files

    def get_sender(self) -> int:
        return next(self.round_robin)