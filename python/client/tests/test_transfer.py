import socket
import struct

from client.file_monitor.transfer import transfer_file
from client.transfer_pb2 import FilePacket


def receive_message(
    connection: socket.socket,
):
    size_data = connection.recv(4)

    if not size_data:
        return None

    message_size = struct.unpack(
        "!I",
        size_data,
    )[0]

    data = b""

    while len(data) < message_size:
        data += connection.recv(
            message_size - len(data)
        )

    packet = FilePacket()
    packet.ParseFromString(data)

    return packet


def test_small_file_uses_one_route(
    tmp_path,
):
    file = tmp_path / "hello.txt"
    file.write_bytes(
        b"Hello World"
    )

    sender, receiver = socket.socketpair()

    transfer_file(
        file,
        sender,
        small_file_sender=1,
        number_of_senders=3,
    )

    sender.close()

    packets = []

    while True:
        packet = receive_message(receiver)

        if packet is None:
            break

        packets.append(packet)

    receiver.close()

    assert len(packets) > 0

    for packet in packets:
        assert packet.target_receiver == 1