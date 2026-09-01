import os
import socket
import tempfile
import threading

import pytest

from client import ipc
from client.framing import read_proto, write_proto
from client.pb import message_pb2


def test_send_talks_to_unix_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fd, path = tempfile.mkstemp(prefix="uniflow-", suffix=".sock", dir="/tmp")
    os.close(fd)
    os.unlink(path)
    monkeypatch.setattr(ipc, "SOCKET_PATH", path)

    ready = threading.Event()
    received: dict[str, object] = {}

    def serve() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(path)
            listener.listen(1)
            ready.set()
            conn, _ = listener.accept()
            with conn:
                req = read_proto(conn, message_pb2.IPCRequest)
                received["command"] = req.command
                received["data"] = req.data
                write_proto(
                    conn,
                    message_pb2.IPCResponse(
                        success=True,
                        message=f"handled {req.command}",
                    ),
                )

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert ready.wait(timeout=2)
        response = ipc.send("echo", b"payload")
        thread.join(timeout=2)
    finally:
        if os.path.exists(path):
            os.unlink(path)

    assert received["command"] == "echo"
    assert received["data"] == b"payload"
    assert response.success is True
    assert response.message == "handled echo"
