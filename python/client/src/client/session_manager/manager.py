import os
from pathlib import Path

from google.protobuf.message import DecodeError
from raptorq import Decoder

from client.common.hash_utils import calculate_sha256
from client.common.packet_hash import calculate_packet_hash
from client.transfer_pb2 import FilePacket

MAX_FILE_SIZE = 1024 * 1024 * 1024


class FileSession:
    def __init__(self, packet: FilePacket, output_folder: Path):
        self.file_id = packet.file_id
        self.file_name = Path(packet.file_name).name
        self.file_size = packet.file_size
        self.file_hash = packet.file_hash
        self.total_blocks = packet.total_blocks

        self.decoders = {}
        self.seen_packets = set()
        self.completed_blocks = set()

        self.part_path = output_folder / f".{self.file_id}.part"
        self.final_path = output_folder / self.file_name

        with self.part_path.open("wb") as file:
            file.truncate(self.file_size)


class SessionManager:
    def __init__(self, output_folder: Path):
        self.output_folder = output_folder
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self.sessions = {}
        self.finished_sessions = set()

    def handle_serialized_packet(
        self,
        receiver_id: int,
        data: bytes,
    ) -> None:
        packet = FilePacket()

        try:
            packet.ParseFromString(data)
        except DecodeError:
            print("Invalid Protobuf packet")
            return

        self.handle_packet(receiver_id, packet)

    def handle_packet(
        self,
        receiver_id: int,
        packet: FilePacket,
    ) -> None:
        if not self._packet_is_valid(packet):
            print("Invalid or corrupted packet")
            return

        if packet.file_id in self.finished_sessions:
            return

        if packet.target_receiver != receiver_id:
            print(
                f"Misrouted: expected Receiver "
                f"{packet.target_receiver}, got {receiver_id}"
            )

        session = self.sessions.get(packet.file_id)

        if session is None:
            session = FileSession(packet, self.output_folder)
            self.sessions[packet.file_id] = session

            print(f"Started receiving {session.file_name}")

        block = packet.block_index

        if block in session.completed_blocks:
            return

        packet_key = (
            block,
            packet.packet_index,
        )

        if packet_key in session.seen_packets:
            return

        session.seen_packets.add(packet_key)

        if block not in session.decoders:
            session.decoders[block] = Decoder.with_defaults(
                packet.block_size,
                packet.symbol_size,
            )

        try:
            decoded = session.decoders[block].decode(
                packet.data
            )
        except Exception:
            print("Invalid RaptorQ packet")
            return

        if decoded is None:
            return

        if len(decoded) != packet.block_size:
            print("Invalid decoded block")
            return

        with session.part_path.open("r+b") as file:
            file.seek(packet.block_offset)
            file.write(decoded)

        session.completed_blocks.add(block)
        del session.decoders[block]

        print(
            f"{session.file_name}: "
            f"{len(session.completed_blocks)}"
            f"/{session.total_blocks} blocks"
        )

        if (
            len(session.completed_blocks)
            == session.total_blocks
        ):
            self._finish(session)

    def _packet_is_valid(
        self,
        packet: FilePacket,
    ) -> bool:
        if (
            not packet.file_id
            or not packet.file_name
            or not packet.data
            or packet.file_size <= 0
            or packet.file_size > MAX_FILE_SIZE
            or packet.total_blocks == 0
            or packet.block_index >= packet.total_blocks
            or packet.block_size == 0
            or packet.symbol_size == 0
            or (
                packet.block_offset
                + packet.block_size
                > packet.file_size
            )
        ):
            return False

        return (
            calculate_packet_hash(packet)
            == packet.packet_hash
        )

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
                f"{session.file_name} - HASH OK"
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