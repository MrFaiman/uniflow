import socket
import time
from pathlib import Path
from uuid import uuid4

from client.common.ipc import send_message
from client.common.packet_hash import calculate_packet_hash
from client.common.paths import relative_path_from_root
from client.file_monitor.packet_router import route_packets
from client.file_monitor.raptorq_encoder import encode_file
from client.transfer_pb2 import DELETE, FilePacket


def transfer_file(
    file: Path,
    connections: list[socket.socket],
    small_file_sender: int,
    watch_root: Path,
) -> int:
    if not connections:
        raise ValueError("at least one Sender connection is required")

    relative_path = relative_path_from_root(file, watch_root)
    packets = encode_file(file, relative_path=relative_path)
    routed_packets = route_packets(
        packets,
        file.stat().st_size,
        small_file_sender,
        len(connections),
    )

    sent = 0
    for sender, packet in routed_packets:
        packet.target_receiver = sender
        packet.packet_hash = calculate_packet_hash(packet)
        send_message(connections[sender], packet.SerializeToString(deterministic=True))
        sent += 1

    return sent


def transfer_delete(
    file: Path,
    connections: list[socket.socket],
    watch_root: Path,
) -> int:
    if not connections:
        raise ValueError("at least one Sender connection is required")

    relative_path = relative_path_from_root(file, watch_root)

    # One logical DELETE version is sent through every Sender path.
    # This gives a tiny control message redundancy without requiring ACKs.
    file_id = f"{time.time_ns()}:{uuid4()}"

    for sender, connection in enumerate(connections):
        packet = FilePacket()
        packet.file_id = file_id
        packet.file_name = relative_path
        packet.operation = DELETE
        packet.packet_index = 0
        packet.total_packets = 1
        packet.target_receiver = sender
        packet.packet_hash = calculate_packet_hash(packet)

        send_message(connection, packet.SerializeToString(deterministic=True))

    return len(connections)
