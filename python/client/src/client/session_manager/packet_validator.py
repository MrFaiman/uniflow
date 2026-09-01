from client.common.packet_hash import calculate_packet_hash
from client.transfer_pb2 import FilePacket

MAX_FILE_SIZE = 1024 * 1024 * 1024


def packet_is_valid(packet: FilePacket) -> bool:
    if not packet.file_id:
        return False

    if not packet.file_name:
        return False

    if not packet.data:
        return False

    if packet.file_size <= 0 or packet.file_size > MAX_FILE_SIZE:
        return False

    if packet.total_blocks == 0:
        return False

    if packet.block_index >= packet.total_blocks:
        return False

    if packet.total_packets == 0:
        return False

    if packet.packet_index >= packet.total_packets:
        return False

    if packet.block_size == 0:
        return False

    if packet.symbol_size == 0:
        return False

    if packet.block_offset + packet.block_size > packet.file_size:
        return False

    if len(packet.file_hash) != 64:
        return False

    if len(packet.packet_hash) != 64:
        return False

    return calculate_packet_hash(packet) == packet.packet_hash