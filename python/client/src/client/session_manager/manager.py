import os
from pathlib import Path

from google.protobuf.message import DecodeError

from client.common.hash_utils import calculate_sha256
from client.session_manager.decoder import decode_packet
from client.session_manager.file_session import FileSession
from client.session_manager.packet_validator import packet_is_valid
from client.transfer_pb2 import FilePacket


class SessionManager:
    def __init__(self, output_folder: Path) -> None:
        self.output_folder = output_folder.resolve()
        self.output_folder.mkdir(parents=True, exist_ok=True)
        parts_folder = self.output_folder / ".uniflow" / "parts"
        if parts_folder.exists():
            for stale_part in parts_folder.glob("*.part"):
                stale_part.unlink(missing_ok=True)
        self.sessions: dict[str, FileSession] = {}
        self.finished_sessions: set[str] = set()
        self.latest_version_by_path: dict[str, int] = {}
        self.packet_count = 0
        self.rejected_packets = 0

    def handle_serialized_packet(self, data: bytes) -> None:
        packet = FilePacket()
        try:
            packet.ParseFromString(data)
        except DecodeError:
            self.packet_count += 1
            self.rejected_packets += 1
            self._maybe_log_packet_stats()
            return
        self.handle_packet(packet)

    def handle_packet(self, packet: FilePacket) -> None:
        self.packet_count += 1
        if not packet_is_valid(packet):
            self.rejected_packets += 1
            self._maybe_log_packet_stats()
            return

        self._maybe_log_packet_stats()

        if packet.file_id in self.finished_sessions:
            return

        session = self._get_session(packet)
        if session is None:
            return

        if not session.metadata_matches(packet):
            print("Packet metadata does not match the active session", flush=True)
            return

        if packet.file_size == 0:
            self._finish(session)
            return

        block = packet.block_index
        if block in session.completed_blocks:
            return
        if session.packet_was_seen(block, packet.packet_index):
            return

        decoded = decode_packet(session, packet)
        if decoded is None:
            return

        session.write_block(packet.block_offset, decoded)
        session.finish_block(block)

        print(
            f"{session.file_name}: "
            f"{len(session.completed_blocks)}/{session.total_blocks} blocks",
            flush=True,
        )

        if session.is_complete():
            self._finish(session)

    def _maybe_log_packet_stats(self) -> None:
        if self.packet_count % 1000 == 0:
            print(
                f"Session Manager packets={self.packet_count} "
                f"rejected={self.rejected_packets}",
                flush=True,
            )

    @staticmethod
    def _file_version(file_id: str) -> int:
        return int(file_id.split(":", 1)[0])

    def _get_session(self, packet: FilePacket) -> FileSession | None:
        version = self._file_version(packet.file_id)
        latest = self.latest_version_by_path.get(packet.file_name)

        if latest is not None and version < latest:
            return None

        if latest is None or version > latest:
            self.latest_version_by_path[packet.file_name] = version
            self._discard_older_sessions(packet.file_name, version)

        session = self.sessions.get(packet.file_id)
        if session is not None:
            return session

        try:
            session = FileSession(packet, self.output_folder)
        except (OSError, ValueError) as error:
            print(f"Could not start file session: {error}", flush=True)
            return None

        self.sessions[packet.file_id] = session
        print(f"Started receiving {session.file_name}", flush=True)
        return session

    def _discard_older_sessions(self, file_name: str, latest_version: int) -> None:
        stale_ids = [
            file_id
            for file_id, session in self.sessions.items()
            if session.file_name == file_name
            and self._file_version(file_id) < latest_version
        ]

        for file_id in stale_ids:
            stale = self.sessions.pop(file_id)
            stale.part_path.unlink(missing_ok=True)
            self.finished_sessions.add(file_id)
            print(f"Discarded older transfer for {file_name}", flush=True)

    def _finish(self, session: FileSession) -> None:
        version = self._file_version(session.file_id)
        if self.latest_version_by_path.get(session.file_name) != version:
            session.part_path.unlink(missing_ok=True)
            self.finished_sessions.add(session.file_id)
            self.sessions.pop(session.file_id, None)
            return

        received_hash = calculate_sha256(session.part_path)

        if received_hash == session.file_hash:
            session.final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(session.part_path, session.final_path)
            print(f"COMPLETE: {session.file_name} - HASH OK", flush=True)
        else:
            session.part_path.unlink(missing_ok=True)
            print(f"FAILED: {session.file_name} - HASH MISMATCH", flush=True)

        self.finished_sessions.add(session.file_id)
        self.sessions.pop(session.file_id, None)
