import os
from pathlib import Path

from google.protobuf.message import DecodeError

from client.common.hash_utils import calculate_sha256
from client.session_manager.decoder import decode_packet
from client.session_manager.file_session import FileSession
from client.session_manager.packet_validator import packet_is_valid
from client.transfer_pb2 import FilePacket


class SessionManager:
    def __init__(
        self,
        output_folder: Path,
    ):
        self.output_folder = output_folder

        self.output_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.sessions = {}
        self.finished_sessions = set()

    def handle_serialized_packet(
        self,
        data: bytes,
    ) -> None:
        packet = FilePacket()

        try:
            packet.ParseFromString(data)
        except DecodeError:
            print("Invalid Protobuf packet")
            return

        self.handle_packet(packet)

    def handle_packet(
        self,
        packet: FilePacket,
    ) -> None:
        if not packet_is_valid(packet):
            print(
                "Invalid or corrupted packet"
            )
            return

        if packet.file_id in self.finished_sessions:
            return

        session = self._get_session(packet)
        block = packet.block_index

        if block in session.completed_blocks:
            return

        if session.packet_was_seen(
            block,
            packet.packet_index,
        ):
            return

        decoded = decode_packet(
            session,
            packet,
        )

        if decoded is None:
            return

        session.write_block(
            packet.block_offset,
            decoded,
        )

        session.finish_block(block)

        print(
            f"{session.file_name}: "
            f"{len(session.completed_blocks)}/"
            f"{session.total_blocks} blocks"
        )

        if session.is_complete():
            self._finish(session)

    def _get_session(
        self,
        packet: FilePacket,
    ) -> FileSession:
        session = self.sessions.get(
            packet.file_id
        )

        if session is not None:
            return session

        session = FileSession(
            packet,
            self.output_folder,
        )

        self.sessions[
            packet.file_id
        ] = session

        print(
            f"Started receiving "
            f"{session.file_name}"
        )

        return session

    def _finish(
        self,
        session: FileSession,
    ) -> None:
        received_hash = calculate_sha256(
            session.part_path
        )

        if received_hash == session.file_hash:
            os.replace(
                session.part_path,
                session.final_path,
            )

            print(
                f"COMPLETE: "
                f"{session.file_name} "
                f"- HASH OK"
            )

        else:
            session.part_path.unlink(
                missing_ok=True
            )

            print(
                f"FAILED: "
                f"{session.file_name} "
                f"- HASH MISMATCH"
            )

        self.finished_sessions.add(
            session.file_id
        )

        del self.sessions[
            session.file_id
        ]