import socket
import struct
from pathlib import Path
from queue import Queue
from threading import Event, Thread

from client.common.ipc import MAX_MESSAGE_SIZE, create_server


def receive_exactly(connection: socket.socket, size: int) -> bytes | None:
    data = bytearray()

    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            if not data:
                return None
            raise ConnectionError("connection closed during a message")
        data.extend(chunk)

    return bytes(data)


def receive_message(connection: socket.socket) -> bytes | None:
    size_data = receive_exactly(connection, 4)
    if size_data is None:
        return None

    message_size = struct.unpack("!I", size_data)[0]
    if message_size == 0 or message_size > MAX_MESSAGE_SIZE:
        raise ValueError("invalid message size")

    message = receive_exactly(connection, message_size)
    if message is None:
        raise ConnectionError("connection closed before message data")
    return message


def handle_connection(connection: socket.socket, messages: Queue) -> None:
    with connection:
        try:
            while True:
                message = receive_message(connection)
                if message is None:
                    return
                messages.put(message)
        except (ConnectionError, OSError, ValueError) as error:
            print(f"Receiver IPC error: {error}", flush=True)


def listen_to_receivers(
    socket_path: Path,
    messages: Queue,
    stop_event: Event,
    ready_event: Event,
) -> None:
    server = create_server(socket_path)
    server.settimeout(0.5)
    ready_event.set()

    try:
        while not stop_event.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop_event.is_set():
                    break
                raise

            thread = Thread(
                target=handle_connection,
                args=(connection, messages),
                daemon=True,
            )
            thread.start()
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)
