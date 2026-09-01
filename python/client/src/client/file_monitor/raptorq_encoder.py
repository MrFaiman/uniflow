from pathlib import Path
from uuid import uuid4

from raptorq import Encoder

from client.common.hash_utils import calculate_sha256
from client.transfer_pb2 import FilePacket


SYMBOL_SIZE = 1400
BLOCK_SIZE = 1024 * 1024
REPAIR_PACKETS = 10


def encode_file(file: Path):
    file_id = str(uuid4())
    file_size = file.stat().st_size
    file_hash = calculate_sha256(file)

    total_blocks = (
        file_size + BLOCK_SIZE - 1
    ) // BLOCK_SIZE

    with file.open("rb") as opened_file:
        block_index = 0

        while data := opened_file.read(BLOCK_SIZE):
            encoder = Encoder.with_defaults(
                data,
                SYMBOL_SIZE,
            )

            encoded_packets = encoder.get_encoded_packets(
                REPAIR_PACKETS,
            )

            for packet_index, data_packet in enumerate(
                encoded_packets
            ):
                packet = FilePacket()

                packet.file_id = file_id
                packet.file_name = file.name
                packet.file_size = file_size
                packet.file_hash = file_hash

                packet.packet_index = packet_index
                packet.total_packets = len(
                    encoded_packets
                )

                packet.data = data_packet

                packet.block_index = block_index
                packet.total_blocks = total_blocks
                packet.block_size = len(data)

                packet.symbol_size = SYMBOL_SIZE
                packet.block_offset = (
                    block_index * BLOCK_SIZE
                )

                yield packet

            block_index += 1