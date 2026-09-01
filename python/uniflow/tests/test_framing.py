import socket

from uniflow.framing import read_proto, write_proto
from uniflow.pb import message_pb2


def test_write_read_request_roundtrip() -> None:
    client, server = socket.socketpair()
    with client, server:
        want = message_pb2.IPCRequest(command="ping", data=b"hello")
        write_proto(client, want)
        got = read_proto(server, message_pb2.IPCRequest)
        assert got.command == want.command
        assert got.data == want.data


def test_write_read_response_roundtrip() -> None:
    client, server = socket.socketpair()
    with client, server:
        want = message_pb2.IPCResponse(success=True, message="handled ping")
        write_proto(server, want)
        got = read_proto(client, message_pb2.IPCResponse)
        assert got.success is True
        assert got.message == want.message
