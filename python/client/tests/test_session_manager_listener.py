import socket
import struct
import time
from queue import Queue
from threading import Thread

from client.session_manager.listener import (
    listen_to_receivers,
    receive_message,
)


def send_message(
    connection: socket.socket,
    data: bytes,
) -> None:
    connection.sendall(
        struct.pack(
            "!I",
            len(data),
        )
        + data
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

    assert (
        receive_message(receiver)
        == message
    )

    assert (
        receive_message(receiver)
        is None
    )

    receiver.close()


def test_multiple_receivers_use_one_socket(
    tmp_path,
):
    socket_path = (
        tmp_path / "proto_ipc.sock"
    )

    messages = Queue()

    thread = Thread(
        target=listen_to_receivers,
        args=(
            socket_path,
            messages,
        ),
        daemon=True,
    )

    thread.start()

    for _ in range(100):
        if socket_path.exists():
            break

        time.sleep(0.01)

    first = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    second = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    first.connect(
        str(socket_path)
    )

    second.connect(
        str(socket_path)
    )

    send_message(
        first,
        b"receiver zero",
    )

    send_message(
        second,
        b"receiver one",
    )

    received = {
        messages.get(timeout=1),
        messages.get(timeout=1),
    }

    first.close()
    second.close()

    assert received == {
        b"receiver zero",
        b"receiver one",
    }