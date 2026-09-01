import socket
import struct

from google.protobuf.message import Message

_HEADER = struct.Struct("<I")


def write_proto(sock: socket.socket, msg: Message) -> None:
    payload = msg.SerializeToString()
    sock.sendall(_HEADER.pack(len(payload)))
    sock.sendall(payload)


def read_proto[T: Message](sock: socket.socket, msg_type: type[T]) -> T:
    header = _recv_exact(sock, _HEADER.size)
    (length,) = _HEADER.unpack(header)
    payload = _recv_exact(sock, length)
    msg = msg_type()
    msg.ParseFromString(payload)
    return msg


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError(
                "socket closed before message was complete"
            )
        chunks.extend(chunk)
    return bytes(chunks)
