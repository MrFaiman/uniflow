import socket
import struct
from pathlib import Path


def create_server(socket_path: Path) -> socket.socket:
    if socket_path.exists():
        socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen()

    return server


def connect_to_server(socket_path: Path) -> socket.socket:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    return client


def send_message(connection: socket.socket, data: bytes) -> None:
    message_size = struct.pack("!I", len(data))

    connection.sendall(message_size)
    connection.sendall(data)