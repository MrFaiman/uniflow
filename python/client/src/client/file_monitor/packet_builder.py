from pathlib import Path
from uuid import uuid4

from client.common.hash_utils import calculate_sha256
from client.transfer_pb2 import FilePacket


def build_file_packet(file: Path, target_sender: int) -> FilePacket:
    packet = FilePacket()

    packet.file_id = str(uuid4())
    packet.file_name = file.name
    packet.file_size = file.stat().st_size
    packet.file_hash = calculate_sha256(file)

    packet.packet_index = 0
    packet.total_packets = 1
    packet.target_receiver = target_sender

    packet.data = file.read_bytes()

    return packet