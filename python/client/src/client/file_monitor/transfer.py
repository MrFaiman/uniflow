import socket
from pathlib import Path

from client.common.ipc import send_message
from client.file_monitor.packet_router import route_packets
from client.file_monitor.raptorq_encoder import encode_file


def transfer_file(
    file: Path,
    connections: list[socket.socket],
    small_file_sender: int,
) -> None:
    packets = encode_file(file)

    routed_packets = route_packets(
        packets,
        file.stat().st_size,
        small_file_sender,
    )

    for sender, packet in routed_packets:
        packet.target_receiver = sender

        data = packet.SerializeToString()

        send_message(connections[sender], data)