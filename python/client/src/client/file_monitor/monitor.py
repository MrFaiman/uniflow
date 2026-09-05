from pathlib import Path

from client.common.round_robin import round_robin

FileSignature = tuple[int, int]


class FileMonitor:
    def __init__(
        self,
        watch_folder: Path,
        number_of_senders: int = 3,
        stable_scans: int = 3,
    ) -> None:
        self.watch_folder = watch_folder.resolve()
        self.stable_scans = stable_scans

        self.known_files: dict[
            Path,
            FileSignature,
        ] = {}

        self.pending: dict[
            Path,
            tuple[FileSignature, int],
        ] = {}

        self.deleted_files: set[
            Path
        ] = set()

        self.round_robin = round_robin(
            number_of_senders
        )

    def get_files(
        self,
    ) -> list[Path]:
        return sorted(
            item
            for item
            in self.watch_folder.rglob("*")
            if item.is_file()
        )

    @staticmethod
    def _signature(
        file: Path,
    ) -> FileSignature:
        stat = file.stat()

        return (
            stat.st_size,
            stat.st_mtime_ns,
        )

    def get_changed_files(
        self,
    ) -> list[Path]:
        changed_files: list[Path] = []

        current_files = set(
            self.get_files()
        )

        # If a deleted path appeared again before
        # its DELETE was transmitted, do not delete
        # the recreated file.
        for file in current_files:
            self.deleted_files.discard(
                file
            )

        for file in current_files:
            try:
                signature = (
                    self._signature(file)
                )

            except FileNotFoundError:
                continue

            if (
                self.known_files.get(file)
                == signature
            ):
                self.pending.pop(
                    file,
                    None,
                )

                continue

            (
                previous_signature,
                count,
            ) = self.pending.get(
                file,
                (
                    signature,
                    0,
                ),
            )

            if (
                previous_signature
                == signature
            ):
                count += 1

            else:
                count = 1

            # Do not transfer a new/modified file
            # immediately.
            #
            # Large files may exist in the folder
            # long before the copy finishes.
            if count >= self.stable_scans:
                changed_files.append(
                    file
                )

                self.known_files[
                    file
                ] = signature

                self.pending.pop(
                    file,
                    None,
                )

            else:
                self.pending[
                    file
                ] = (
                    signature,
                    count,
                )

        missing = (
            set(self.known_files)
            - current_files
        )

        for file in missing:
            self.known_files.pop(
                file,
                None,
            )

            self.pending.pop(
                file,
                None,
            )

            self.deleted_files.add(
                file
            )

        return sorted(
            changed_files
        )

    def get_deleted_files(
        self,
    ) -> list[Path]:
        return sorted(
            self.deleted_files
        )

    def mark_delete_sent(
        self,
        file: Path,
    ) -> None:
        self.deleted_files.discard(
            file
        )

    def mark_failed(
        self,
        file: Path,
    ) -> None:
        self.known_files.pop(
            file,
            None,
        )

        self.pending.pop(
            file,
            None,
        )

    def get_sender(
        self,
    ) -> int:
        return next(
            self.round_robin
        )