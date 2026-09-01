import os
import socket
import tempfile
import threading

import pytest

from uniflow.framing import read_proto, write_proto
from uniflow.ipc import Ipc
from uniflow.pb import message_pb2


def test_send_talks_to_unix_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fd, path = tempfile.mkstemp(prefix="uniflow-", suffix=".sock", dir="/tmp")
    os.close(fd)
    os.unlink(path)
    ipc = Ipc(path)

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
                received["target_ip"] = req.target_ip
                received["object_id"] = req.object_id
                received["coordinated"] = req.coordinated
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
        response = ipc.send(
            "echo",
            b"payload",
            target_ip="10.0.0.1",
            object_id=7,
            coordinated=False,
        )
        thread.join(timeout=2)
    finally:
        if os.path.exists(path):
            os.unlink(path)

    assert received["command"] == "echo"
    assert received["data"] == b"payload"
    assert received["target_ip"] == "10.0.0.1"
    assert received["object_id"] == 7
    assert received["coordinated"] is False
    assert response.success is True
    assert response.message == "handled echo"
