import socket
import struct

from client.session_manager.listener import (
    receive_message,
)


def test_receive_message_handles_parts():
    sender, receiver = socket.socketpair()

    message = b"Hello Protobuf"

    header = struct.pack(
        "!I",
        len(message),
    )

    sender.sendall(
        header[:2]
    )

    sender.sendall(
        header[2:] + message[:3]
    )

    sender.sendall(
        message[3:]
    )

    sender.close()

    received = receive_message(
        receiver
    )

    assert received == message

    assert (
        receive_message(receiver)
        is None
    )

    receiver.close()