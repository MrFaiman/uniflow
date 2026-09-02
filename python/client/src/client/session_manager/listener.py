import socket
import struct
from pathlib import Path
from queue import Queue
from threading import Thread

from client.common.ipc import create_server

MAX_MESSAGE_SIZE = 2 * 1024 * 1024


def receive_exactly(
    connection: socket.socket,
    size: int,
):
    data = bytearray()

    while len(data) < size:
        chunk = connection.recv(
            size - len(data)
        )

        if not chunk:
            if not data:
                return None

            raise ConnectionError(
                "Connection closed during a message"
            )

        data.extend(chunk)

    return bytes(data)


def receive_message(
    connection: socket.socket,
):
    size_data = receive_exactly(
        connection,
        4,
    )

    if size_data is None:
        return None

    message_size = struct.unpack(
        "!I",
        size_data,
    )[0]

    if (
        message_size == 0
        or message_size > MAX_MESSAGE_SIZE
    ):
        raise ValueError(
            "Invalid message size"
        )

    message = receive_exactly(
        connection,
        message_size,
    )

    if message is None:
        raise ConnectionError(
            "Connection closed before message data"
        )

    return message


def handle_connection(
    connection: socket.socket,
    messages: Queue,
) -> None:
    with connection:
        try:
            while True:
                message = receive_message(
                    connection
                )

                if message is None:
                    return

                messages.put(message)

        except (
            ConnectionError,
            ValueError,
        ) as error:
            print(
                f"Receiver IPC error: {error}"
            )


def listen_to_receivers(
    socket_path: Path,
    messages: Queue,
) -> None:
    server = create_server(socket_path)

    while True:
        connection, _ = server.accept()

        thread = Thread(
            target=handle_connection,
            args=(
                connection,
                messages,
            ),
            daemon=True,
        )

        thread.start()