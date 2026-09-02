import socket
from pathlib import Path

from client.common.ipc import send_message
from client.common.packet_hash import calculate_packet_hash
from client.file_monitor.packet_router import route_packets
from client.file_monitor.raptorq_encoder import encode_file


def transfer_file(
    file: Path,
    connection: socket.socket,
    small_file_sender: int,
    number_of_senders: int = 3,
) -> None:
    packets = encode_file(file)

    routed_packets = route_packets(
        packets,
        file.stat().st_size,
        small_file_sender,
        number_of_senders,
    )

    for sender, packet in routed_packets:
        packet.target_receiver = sender
        packet.packet_hash = calculate_packet_hash(packet)

        data = packet.SerializeToString()

        send_message(connection, data)