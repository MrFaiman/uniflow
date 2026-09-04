"""RX-side Session Manager.

The three Receiver processes each decode and stage source blocks
independently, but no single Receiver can tell when an object is complete —
only this process sees the block reports from all of them. It therefore owns
completion tracking, reconstruction, and final SHA-256 verification.

It communicates with the Receivers over a Unix Domain Socket using
length-prefixed Protobuf `BlockReport` messages. This is local IPC on the RX
machine only; nothing here ever sends anything back across the network to TX.
"""

import hashlib
import logging
import os
import shutil
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from uniflow.framing import read_proto, write_proto
from uniflow.pb import message_pb2

logger = logging.getLogger(__name__)

_READ_CHUNK_BYTES = 1024 * 1024

# How long an incomplete object may sit without new blocks before it is
# reported as stalled, and how often to check.
STALL_SECONDS = 30.0
STALL_POLL_SECONDS = 10.0


@dataclass
class ObjectState:
    """Reconstruction state for one in-flight object (one file)."""

    file_name: str
    file_size: int
    source_blocks: int
    checksum: bytes
    staged_blocks: dict[int, str] = field(default_factory=dict)
    completed: bool = False
    last_progress: float = field(default_factory=time.monotonic)
    stall_reported: bool = False

    def is_complete(self) -> bool:
        if self.file_size == 0:
            return True
        return len(self.staged_blocks) >= self.source_blocks

    def missing_blocks(self) -> list[int]:
        return [
            index
            for index in range(self.source_blocks)
            if index not in self.staged_blocks
        ]


class SessionManager:
    def __init__(self, socket_path: str, receive_dir: Path) -> None:
        self.socket_path = socket_path
        self.receive_dir = receive_dir
        self._objects: dict[int, ObjectState] = {}
        # Reports arrive concurrently from three Receiver connections, each
        # handled on its own thread, and they mutate shared per-object state.
        self._lock = threading.Lock()
        self._server: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        server.listen(16)
        self._server = server
        logger.info("session manager listening on %s", self.socket_path)

    def report_stalls(self, stall_after: float = STALL_SECONDS) -> list[int]:
        """Log objects that stopped making progress before completing.

        There is no ACK channel, so a transfer that arrives short cannot be
        retried — it would otherwise sit here silently forever. Surfacing it
        turns an invisible hang into a diagnosable failure.
        """
        now = time.monotonic()
        stalled: list[int] = []
        with self._lock:
            for object_id, state in self._objects.items():
                if state.completed or state.stall_reported:
                    continue
                if now - state.last_progress < stall_after:
                    continue
                state.stall_reported = True
                stalled.append(object_id)
                missing = state.missing_blocks()
                logger.error(
                    "STALLED: %s object=%d has %d/%d blocks after %.0fs idle; "
                    "missing=%s (unrecoverable: no ACK channel to request a "
                    "retransmit)",
                    state.file_name,
                    object_id,
                    len(state.staged_blocks),
                    state.source_blocks,
                    now - state.last_progress,
                    missing[:10],
                )
        return stalled

    def _watchdog(self, interval: float) -> None:
        while not self._stop.wait(interval):
            self.report_stalls()

    def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("start() must be called before serve_forever()")
        watchdog = threading.Thread(
            target=self._watchdog,
            args=(STALL_POLL_SECONDS,),
            daemon=True,
        )
        watchdog.start()
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            thread = threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
            )
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Report anything still outstanding at shutdown, so an interrupted
        # transfer is never silently forgotten.
        self.report_stalls(stall_after=0.0)
        if self._server is not None:
            self._server.close()
            self._server = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                report = read_proto(conn, message_pb2.BlockReport)
            except (OSError, ValueError):
                return
            try:
                self.handle_report(report)
                response = message_pb2.IPCResponse(
                    success=True,
                    message="recorded",
                )
            except Exception as err:  # noqa: BLE001
                logger.error("failed to handle block report: %s", err)
                response = message_pb2.IPCResponse(
                    success=False,
                    message=str(err),
                )
            try:
                write_proto(conn, response)
            except OSError:
                pass

    def handle_report(self, report: message_pb2.BlockReport) -> None:
        with self._lock:
            state = self._objects.get(report.object_id)
            if state is None:
                state = ObjectState(
                    file_name=report.file_name,
                    file_size=report.file_size,
                    source_blocks=max(report.source_blocks, 0),
                    checksum=bytes(report.checksum),
                )
                self._objects[report.object_id] = state

            if state.completed:
                return

            if report.staging_path:
                state.staged_blocks[report.block_index] = report.staging_path
            state.last_progress = time.monotonic()

            logger.info(
                "block report object=%d block=%d worker=%d (%d/%d)",
                report.object_id,
                report.block_index,
                report.worker_index,
                len(state.staged_blocks),
                state.source_blocks,
            )

            if not state.is_complete():
                return
            state.completed = True
            object_id = report.object_id

        # Reconstruction is slow relative to report handling, so it runs
        # outside the lock. `completed` is already latched above, so no other
        # report can start a second reconstruction of the same object.
        self._reconstruct(object_id, state)

    def _reconstruct(self, object_id: int, state: ObjectState) -> None:
        try:
            out_path = self._safe_output_path(state.file_name)
        except ValueError as err:
            logger.error("rejected unsafe path %r: %s", state.file_name, err)
            return

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(out_path.name + ".part")

        # A zero-byte file produces no data packets and therefore stages no
        # blocks; the FDT alone is the completion signal.
        if state.file_size == 0:
            out_path.write_bytes(b"")
            logger.info(
                "COMPLETE: %s - HASH OK (0 bytes, empty file)",
                state.file_name,
            )
            return

        digest = hashlib.sha256()
        written = 0
        try:
            with open(tmp_path, "wb") as out:
                for index in range(state.source_blocks):
                    staging_path = state.staged_blocks.get(index)
                    if staging_path is None:
                        logger.error(
                            "object=%d missing block %d; cannot reconstruct",
                            object_id,
                            index,
                        )
                        tmp_path.unlink(missing_ok=True)
                        return
                    written += self._copy_block(
                        staging_path,
                        out,
                        digest,
                        remaining=state.file_size - written,
                    )
        except OSError as err:
            logger.error("object=%d reconstruction failed: %s", object_id, err)
            tmp_path.unlink(missing_ok=True)
            return

        if written != state.file_size:
            logger.error(
                "object=%d size mismatch: got %d want %d",
                object_id,
                written,
                state.file_size,
            )
            tmp_path.unlink(missing_ok=True)
            return

        actual = digest.digest()
        if state.checksum and actual != state.checksum:
            logger.error(
                "object=%d HASH MISMATCH file=%s expected=%s got=%s",
                object_id,
                state.file_name,
                state.checksum.hex(),
                actual.hex(),
            )
            tmp_path.unlink(missing_ok=True)
            return

        # Only promote the temp file once the hash is verified, so a partial
        # or corrupt transfer never appears at the real filename.
        tmp_path.replace(out_path)
        self._cleanup_staging(state)
        logger.info(
            "COMPLETE: %s - HASH OK (%d bytes, sha256=%s)",
            state.file_name,
            written,
            actual.hex(),
        )

    def _copy_block(
        self,
        staging_path: str,
        out,  # noqa: ANN001 - binary file object
        digest,  # noqa: ANN001 - hashlib object
        remaining: int,
    ) -> int:
        """Stream one staged block into the output, hashing as it goes.

        Streaming (rather than reading whole blocks/files into memory) is what
        keeps peak memory flat regardless of file size, so a 1 GB transfer does
        not need 1 GB of RAM to reconstruct.
        """
        written = 0
        with open(staging_path, "rb") as src:
            while remaining > 0:
                chunk = src.read(min(_READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                remaining -= len(chunk)
        return written

    def _safe_output_path(self, relative_path: str) -> Path:
        if not relative_path:
            raise ValueError("empty relative path")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("path escapes receive directory")
        resolved = (self.receive_dir / candidate).resolve()
        base = self.receive_dir.resolve()
        if resolved != base and base not in resolved.parents:
            raise ValueError("path escapes receive directory")
        return resolved

    def _cleanup_staging(self, state: ObjectState) -> None:
        staging_dirs = {
            str(Path(path).parent)
            for path in state.staged_blocks.values()
            if path
        }
        for directory in staging_dirs:
            shutil.rmtree(directory, ignore_errors=True)
