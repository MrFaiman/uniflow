import os
import socket
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path

import pytest

from client.common.ipc import connect_to_server, receive_message, send_message
from client.supervisor import SenderSupervisor
from client.transfer_pb2 import FilePacket


@pytest.fixture
def net_binary():
    binary = os.environ.get("UNIFLOW_NET_BINARY")
    if not binary:
        pytest.skip("set UNIFLOW_NET_BINARY to run compiled worker integration tests")
    assert Path(binary).is_file()
    return binary


def test_receiver_survives_empty_datagram_and_forwards_misrouted_bytes(net_binary):
    with tempfile.TemporaryDirectory(prefix="uf-", dir="/tmp") as folder:
        path = str(Path(folder) / "manager.sock")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen()
            server.settimeout(5)
            env = dict(
                os.environ,
                IPC_SOCKET_PATH=path,
                UDP_PORT=str(port),
                UNIFLOW_WORKER_INDEX="1",
            )
            process = subprocess.Popen([net_binary, "recv"], env=env)
            try:
                connection, _ = server.accept()
                with connection, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
                    connection.settimeout(5)
                    tx.sendto(b"", ("127.0.0.1", port))
                    # The receiver must preserve bytes for manager hash validation,
                    # regardless of malformed protobuf or intended worker index.
                    payload = b"\x0a\x04test\x38\x00"
                    tx.sendto(payload, ("127.0.0.1", port))
                    assert receive_message(connection) == payload
                    assert process.poll() is None
            finally:
                process.terminate()
                process.wait(timeout=5)


def test_three_senders_route_detect_failure_and_clean_up(net_binary, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="uf-", dir="/tmp") as folder:
        with ExitStack() as stack:
            # Reserve three adjacent UDP ports before starting the workers.
            base = 0
            for _ in range(100):
                listeners = []
                try:
                    for index in range(3):
                        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        listeners.append(listener)
                        listener.bind(("127.0.0.1", 0 if index == 0 else base + index))
                        if index == 0:
                            base = listener.getsockname()[1]
                            if base > 65533:
                                raise OSError("port range exhausted")
                    break
                except OSError:
                    for listener in listeners:
                        listener.close()
            else:
                pytest.fail("could not reserve three UDP ports")
            for listener in listeners:
                stack.enter_context(listener)
                listener.settimeout(5)

            monkeypatch.setenv("PORT", str(base))
            monkeypatch.setenv(
                "IPC_SOCKET_PATH", str(Path(folder) / "nested" / "tx.sock")
            )
            monkeypatch.setenv("UNIFLOW_NET_BINARY", net_binary)
            supervisor = SenderSupervisor("127.0.0.1")
            processes = []
            paths = []
            try:
                paths = supervisor.start()
                processes = list(supervisor.processes)
                assert len(processes) == len(paths) == 3
                for index, path in enumerate(paths):
                    with connect_to_server(path) as connection:
                        packet = FilePacket(file_id="test", target_receiver=index)
                        payload = packet.SerializeToString()
                        send_message(connection, payload)
                        assert listeners[index].recv(65535) == payload
                processes[0].terminate()
                processes[0].wait(timeout=5)
                with pytest.raises(RuntimeError):
                    supervisor.check()
            finally:
                supervisor.stop()
            assert all(process.poll() is not None for process in processes)
            assert all(not path.exists() for path in paths)
