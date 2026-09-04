from hashlib import sha256
from pathlib import Path

from client.common.paths import safe_join
from client.transfer_pb2 import FilePacket


class FileSession:
    def __init__(self, packet: FilePacket, output_folder: Path) -> None:
        self.file_id = packet.file_id
        self.file_name = packet.file_name
        self.file_size = packet.file_size
        self.file_hash = packet.file_hash
        self.total_blocks = packet.total_blocks

        self.decoders = {}
        self.seen_packets: dict[int, set[int]] = {}
        self.completed_blocks: set[int] = set()

        output_folder = output_folder.resolve()
        self.final_path = safe_join(output_folder, self.file_name)
        self.final_path.parent.mkdir(parents=True, exist_ok=True)

        parts_folder = output_folder / ".uniflow" / "parts"
        parts_folder.mkdir(parents=True, exist_ok=True)
        part_name = sha256(self.file_id.encode()).hexdigest() + ".part"
        self.part_path = parts_folder / part_name

        with self.part_path.open("wb") as file:
            file.truncate(self.file_size)

    def metadata_matches(self, packet: FilePacket) -> bool:
        return (
            packet.file_name == self.file_name
            and packet.file_size == self.file_size
            and packet.file_hash == self.file_hash
            and packet.total_blocks == self.total_blocks
        )

    def packet_was_seen(self, block: int, packet_index: int) -> bool:
        seen = self.seen_packets.setdefault(block, set())
        if packet_index in seen:
            return True
        seen.add(packet_index)
        return False

    def write_block(self, offset: int, data: bytes) -> None:
        with self.part_path.open("r+b") as file:
            file.seek(offset)
            file.write(data)

    def finish_block(self, block: int) -> None:
        self.completed_blocks.add(block)
        self.decoders.pop(block, None)
        self.seen_packets.pop(block, None)

    def is_complete(self) -> bool:
        if self.file_size == 0:
            return True
        return len(self.completed_blocks) == self.total_blocks
