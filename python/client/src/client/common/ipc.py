import socket
import struct
from pathlib import Path

MAX_MESSAGE_SIZE = 2 * 1024 * 1024


def create_server(socket_path: Path) -> socket.socket:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen()
    return server


def connect_to_server(socket_path: Path, timeout: float = 2.0) -> socket.socket:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(socket_path))
    client.settimeout(None)
    return client


def send_message(connection: socket.socket, data: bytes) -> None:
    if not data or len(data) > MAX_MESSAGE_SIZE:
        raise ValueError("invalid IPC message size")

    connection.sendall(struct.pack("!I", len(data)))
    connection.sendall(data)
