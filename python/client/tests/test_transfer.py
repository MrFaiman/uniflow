import socket
import struct

from client.file_monitor.transfer import transfer_file


def receive_message(connection):
    size_data = connection.recv(4)
    message_size = struct.unpack("!I", size_data)[0]

    data = b""

    while len(data) < message_size:
        data += connection.recv(message_size - len(data))

    return data


def test_small_file_goes_to_one_sender(tmp_path):
    file = tmp_path / "hello.txt"
    file.write_bytes(b"Hello World")

    connections = []
    receivers = []

    for _ in range(3):
        sender_socket, receiver_socket = socket.socketpair()

        connections.append(sender_socket)
        receivers.append(receiver_socket)

    transfer_file(
        file,
        connections,
        small_file_sender=1,
    )

    connections[0].close()
    connections[1].close()
    connections[2].close()

    assert receivers[0].recv(1) == b""
    assert receive_message(receivers[1]) != b""
    assert receivers[2].recv(1) == b""

    for receiver in receivers:
        receiver.close()