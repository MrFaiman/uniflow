from string import ascii_letters, digits, hexdigits

from client.common.config import get_max_file_bytes, get_worker_count
from client.common.packet_hash import calculate_packet_hash
from client.common.paths import normalize_relative_path
from client.transfer_pb2 import DELETE, WRITE, FilePacket

MAX_BLOCK_SIZE = 2 * 1024 * 1024


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in hexdigits for character in value)


def packet_is_valid(packet: FilePacket) -> bool:
    if not packet.file_id or not packet.file_name:
        return False

    version_text, separator, unique_id = packet.file_id.partition(":")
    safe_id_chars = set(ascii_letters + digits + "-")
    if (
        not separator
        or not version_text.isdigit()
        or not unique_id
        or any(character not in safe_id_chars for character in unique_id)
    ):
        return False

    try:
        normalize_relative_path(packet.file_name)
    except ValueError:
        return False

    if packet.target_receiver >= get_worker_count():
        return False

    if not _is_sha256(packet.packet_hash):
        return False

    if packet.operation == DELETE:
        if packet.file_size != 0 or packet.file_hash or packet.data:
            return False
        if packet.packet_index != 0 or packet.total_packets != 1:
            return False
        if (
            packet.block_index != 0
            or packet.total_blocks != 0
            or packet.block_size != 0
            or packet.symbol_size != 0
            or packet.block_offset != 0
        ):
            return False
        return calculate_packet_hash(packet) == packet.packet_hash

    if packet.operation != WRITE:
        return False

    if packet.file_size > get_max_file_bytes():
        return False

    if not _is_sha256(packet.file_hash):
        return False

    if packet.file_size == 0:
        if packet.total_blocks != 0 or packet.block_size != 0 or packet.data:
            return False
        if packet.packet_index != 0 or packet.total_packets != 1:
            return False
        return calculate_packet_hash(packet) == packet.packet_hash

    if not packet.data:
        return False
    if packet.total_blocks == 0 or packet.block_index >= packet.total_blocks:
        return False
    if packet.total_packets == 0 or packet.packet_index >= packet.total_packets:
        return False
    if packet.block_size == 0 or packet.block_size > MAX_BLOCK_SIZE:
        return False
    if packet.symbol_size == 0 or packet.symbol_size > 1400:
        return False
    if packet.block_offset + packet.block_size > packet.file_size:
        return False

    return calculate_packet_hash(packet) == packet.packet_hash
