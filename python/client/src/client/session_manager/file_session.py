from pathlib import Path

from client.transfer_pb2 import FilePacket


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

        self.decoders = {}
        self.seen_packets = {}
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

    def packet_was_seen(
        self,
        block: int,
        packet_index: int,
    ) -> bool:
        if block not in self.seen_packets:
            self.seen_packets[block] = set()

        if packet_index in self.seen_packets[block]:
            return True

        self.seen_packets[block].add(packet_index)

        return False

    def write_block(
        self,
        offset: int,
        data: bytes,
    ) -> None:
        with self.part_path.open("r+b") as file:
            file.seek(offset)
            file.write(data)

    def finish_block(
        self,
        block: int,
    ) -> None:
        self.completed_blocks.add(block)

        if block in self.decoders:
            del self.decoders[block]

        if block in self.seen_packets:
            del self.seen_packets[block]

    def is_complete(self) -> bool:
        return (
            len(self.completed_blocks)
            == self.total_blocks
        )