import os
from pathlib import Path

from google.protobuf.message import DecodeError
from raptorq import Decoder

from client.common.hash_utils import calculate_sha256
from client.common.packet_hash import calculate_packet_hash
from client.transfer_pb2 import FilePacket


MAX_FILE_SIZE = 1024 * 1024 * 1024


class BlockState:
    def __init__(self, packet: FilePacket):
        self.block_size = packet.block_size
        self.block_offset = packet.block_offset
        self.symbol_size = packet.symbol_size
        self.total_packets = packet.total_packets

        self.seen_packets = set()

        self.decoder = Decoder.with_defaults(
            self.block_size,
            self.symbol_size,
        )

    def matches(self, packet: FilePacket) -> bool:
        return (
            self.block_size == packet.block_size
            and self.block_offset == packet.block_offset
            and self.symbol_size == packet.symbol_size
            and self.total_packets == packet.total_packets
        )


class FileSession:
    def __init__(
        self,
        packet: FilePacket,
        output_folder: Path,
    ):
        self.file_id = packet.file_id
        self.file_name = Path(packet.file_name).name
        self.file_size = packet.file_size
        self.file_hash = packet.file_hash
        self.total_blocks = packet.total_blocks

        self.blocks = {}
        self.completed_blocks = set()

        self.part_path = (
            output_folder
            / f".{self.file_id}.part"
        )

        self.final_path = (
            output_folder
            / self.file_name
        )

        with self.part_path.open("wb") as file:
            file.truncate(self.file_size)

    def matches(self, packet: FilePacket) -> bool:
        return (
            self.file_name == Path(packet.file_name).name
            and self.file_size == packet.file_size
            and self.file_hash == packet.file_hash
            and self.total_blocks == packet.total_blocks
        )

    def write_block(
        self,
        offset: int,
        data: bytes,
    ) -> None:
        with self.part_path.open("r+b") as file:
            file.seek(offset)
            file.write(data)


class SessionManager:
    def __init__(self, output_folder: Path):
        self.output_folder = output_folder

        self.output_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

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
            print("Discarded invalid Protobuf packet")
            return

        self.handle_packet(
            receiver_id,
            packet,
        )

    def handle_packet(
        self,
        receiver_id: int,
        packet: FilePacket,
    ) -> None:
        if not self._packet_is_valid(packet):
            print(
                "Discarded invalid or corrupted packet"
            )
            return

        if packet.file_id in self.finished_sessions:
            return

        if packet.target_receiver != receiver_id:
            print(
                "Misrouted packet: expected Receiver "
                f"{packet.target_receiver}, "
                f"got Receiver {receiver_id}"
            )

        session = self.sessions.get(
            packet.file_id
        )

        if session is None:
            session = FileSession(
                packet,
                self.output_folder,
            )

            self.sessions[packet.file_id] = session

            print(
                f"Started receiving "
                f"{session.file_name}"
            )

        elif not session.matches(packet):
            print(
                "Discarded packet with "
                "inconsistent file metadata"
            )
            return

        if packet.block_index in session.completed_blocks:
            return

        block = session.blocks.get(
            packet.block_index
        )

        if block is None:
            block = BlockState(packet)

            session.blocks[
                packet.block_index
            ] = block

        elif not block.matches(packet):
            print(
                "Discarded packet with "
                "inconsistent block metadata"
            )
            return

        if packet.packet_index in block.seen_packets:
            return

        block.seen_packets.add(
            packet.packet_index
        )

        try:
            decoded_data = block.decoder.decode(
                packet.data
            )
        except Exception:
            print(
                "Discarded invalid RaptorQ packet"
            )
            return

        if decoded_data is None:
            return

        if len(decoded_data) != block.block_size:
            print(
                "Discarded incorrectly "
                "decoded block"
            )
            return

        session.write_block(
            block.block_offset,
            decoded_data,
        )

        session.completed_blocks.add(
            packet.block_index
        )

        del session.blocks[
            packet.block_index
        ]

        print(
            f"{session.file_name}: "
            f"{len(session.completed_blocks)}"
            f"/{session.total_blocks} blocks"
        )

        if (
            len(session.completed_blocks)
            == session.total_blocks
        ):
            self._finish_session(session)

    def _packet_is_valid(
        self,
        packet: FilePacket,
    ) -> bool:
        if not packet.file_id:
            return False

        if not packet.file_name:
            return False

        if (
            packet.file_size <= 0
            or packet.file_size > MAX_FILE_SIZE
        ):
            return False

        if len(packet.file_hash) != 64:
            return False

        if len(packet.packet_hash) != 64:
            return False

        if packet.total_blocks == 0:
            return False

        if (
            packet.block_index
            >= packet.total_blocks
        ):
            return False

        if packet.total_packets == 0:
            return False

        if (
            packet.packet_index
            >= packet.total_packets
        ):
            return False

        if packet.block_size == 0:
            return False

        if packet.symbol_size == 0:
            return False

        if (
            packet.block_offset
            + packet.block_size
            > packet.file_size
        ):
            return False

        if not packet.data:
            return False

        expected_hash = calculate_packet_hash(
            packet
        )

        return (
            expected_hash
            == packet.packet_hash
        )

    def _finish_session(
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
                "- HASH OK"
            )

        else:
            session.part_path.unlink(
                missing_ok=True
            )

            print(
                f"FAILED: "
                f"{session.file_name} "
                "- HASH MISMATCH"
            )

        self.finished_sessions.add(
            session.file_id
        )

        del self.sessions[
            session.file_id
        ]