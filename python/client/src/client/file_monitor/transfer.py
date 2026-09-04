import socket
from pathlib import Path

from client.common.ipc import send_message
from client.common.packet_hash import calculate_packet_hash
from client.common.paths import relative_path_from_root
from client.file_monitor.packet_router import route_packets
from client.file_monitor.raptorq_encoder import encode_file


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
