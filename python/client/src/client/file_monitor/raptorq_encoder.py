import math
import time
from pathlib import Path
from uuid import uuid4

from raptorq import Encoder

from client.common.config import get_max_file_bytes, get_repair_percent
from client.common.hash_utils import calculate_sha256
from client.transfer_pb2 import FilePacket

SYMBOL_SIZE = 1024
BLOCK_SIZE = 1024 * 1024
MIN_REPAIR_PACKETS = 16


def _repair_packet_count(block_size: int, repair_percent: int) -> int:
    if repair_percent == 0:
        return 0
    source_symbols = max(1, math.ceil(block_size / SYMBOL_SIZE))
    proportional = math.ceil(source_symbols * repair_percent / 100)
    return max(MIN_REPAIR_PACKETS, proportional)


def _fill_common_metadata(
    packet: FilePacket,
    *,
    file_id: str,
    relative_path: str,
    file_size: int,
    file_hash: str,
    total_blocks: int,
) -> None:
    packet.file_id = file_id
    packet.file_name = relative_path
    packet.file_size = file_size
    packet.file_hash = file_hash
    packet.total_blocks = total_blocks
    packet.symbol_size = SYMBOL_SIZE


def encode_file(
    file: Path,
    relative_path: str | None = None,
    repair_percent: int | None = None,
):
    file_size = file.stat().st_size
    max_size = get_max_file_bytes()
    if file_size > max_size:
        raise ValueError(f"file is larger than the 1 GiB project limit: {file}")

    if relative_path is None:
        relative_path = file.name
    if repair_percent is None:
        repair_percent = get_repair_percent()

    file_id = f"{time.time_ns()}:{uuid4()}"
    file_hash = calculate_sha256(file)

    if file_size == 0:
        packet = FilePacket()
        _fill_common_metadata(
            packet,
            file_id=file_id,
            relative_path=relative_path,
            file_size=0,
            file_hash=file_hash,
            total_blocks=0,
        )
        packet.packet_index = 0
        packet.total_packets = 1
        packet.block_index = 0
        packet.block_size = 0
        packet.block_offset = 0
        packet.data = b""
        yield packet
        return

    total_blocks = math.ceil(file_size / BLOCK_SIZE)

    with file.open("rb") as opened_file:
        block_index = 0
        while data := opened_file.read(BLOCK_SIZE):
            encoder = Encoder.with_defaults(data, SYMBOL_SIZE)
            repair_packets = _repair_packet_count(len(data), repair_percent)
            encoded_packets = encoder.get_encoded_packets(repair_packets)

            for packet_index, data_packet in enumerate(encoded_packets):
                packet = FilePacket()
                _fill_common_metadata(
                    packet,
                    file_id=file_id,
                    relative_path=relative_path,
                    file_size=file_size,
                    file_hash=file_hash,
                    total_blocks=total_blocks,
                )
                packet.packet_index = packet_index
                packet.total_packets = len(encoded_packets)
                packet.data = data_packet
                packet.block_index = block_index
                packet.block_size = len(data)
                packet.block_offset = block_index * BLOCK_SIZE
                yield packet

            block_index += 1
