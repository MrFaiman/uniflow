import errno
import os
import signal
import socket
import subprocess
import tempfile
import time
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
                    connection.shutdown(socket.SHUT_RDWR)
                # The next datagram must survive the failed write and reconnect.
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
                    tx.sendto(b"after reconnect", ("127.0.0.1", port))
                reconnected, _ = server.accept()
                with reconnected:
                    reconnected.settimeout(5)
                    assert receive_message(reconnected) == b"after reconnect"
            finally:
                process.terminate()
                assert process.wait(timeout=5) == 0


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
                    # A truncated client frame must not stop future connections.
                    with connect_to_server(path) as connection:
                        connection.sendall(b"\x00\x00\x00\x08abc")
                    with connect_to_server(path) as connection:
                        send_message(connection, b"\xff")
                        wrong_worker = FilePacket(
                            file_id="wrong", target_receiver=(index + 1) % 3
                        )
                        send_message(connection, wrong_worker.SerializeToString())
                        packet = FilePacket(file_id="test", target_receiver=index)
                        payload = packet.SerializeToString()
                        send_message(connection, payload)
                        assert listeners[index].recv(65535) == payload
                processes[0].terminate()
                assert processes[0].wait(timeout=5) == 0
                with pytest.raises(RuntimeError):
                    supervisor.check()
            finally:
                supervisor.stop()
            assert all(process.poll() is not None for process in processes)
            assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("partial_frame", [b"", b"\x00\x00", b"\x00\x00\x00\x08abc"])
def test_sender_stops_with_idle_or_incomplete_client(
    net_binary, monkeypatch, partial_frame
):
    with tempfile.TemporaryDirectory(prefix="uf-", dir="/tmp") as folder:
        monkeypatch.setenv("IPC_SOCKET_PATH", str(Path(folder) / "tx.sock"))
        monkeypatch.setenv("UNIFLOW_NET_BINARY", net_binary)
        monkeypatch.setenv("UNIFLOW_WORKERS", "3")
        supervisor = SenderSupervisor("127.0.0.1")
        try:
            paths = supervisor.start()
            process = supervisor.processes[0]
            with connect_to_server(paths[0]) as connection:
                connection.sendall(partial_frame)
                process.terminate()
                assert process.wait(timeout=5) == 0
        finally:
            supervisor.stop()


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_receiver_stops_while_waiting_for_session_manager(net_binary, stop_signal):
    with tempfile.TemporaryDirectory(prefix="uf-", dir="/tmp") as folder:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = dict(
            os.environ,
            IPC_SOCKET_PATH=str(Path(folder) / "missing-manager.sock"),
            UDP_PORT=str(port),
            UNIFLOW_WORKER_INDEX="0",
        )
        process = subprocess.Popen([net_binary, "recv"], env=env)
        try:
            deadline = time.monotonic() + 5
            # Binding UDP happens before attempting the missing manager socket.
            while time.monotonic() < deadline:
                assert process.poll() is None
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    try:
                        probe.bind(("127.0.0.1", port))
                    except OSError as error:
                        if error.errno == errno.EADDRINUSE:
                            break
                        raise
                time.sleep(0.01)
            else:
                pytest.fail("receiver did not bind UDP")
            process.send_signal(stop_signal)
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def test_sender_stops_during_rate_limit_wait(net_binary, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="uf-", dir="/tmp") as folder:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.settimeout(5)
            monkeypatch.setenv("PORT", str(listener.getsockname()[1] - 2))
            monkeypatch.setenv("IPC_SOCKET_PATH", str(Path(folder) / "tx.sock"))
            monkeypatch.setenv("UNIFLOW_NET_BINARY", net_binary)
            monkeypatch.setenv("UNIFLOW_WORKERS", "3")
            monkeypatch.setenv("UNIFLOW_SEND_RATE_MBPS", "0.000001")
            supervisor = SenderSupervisor("127.0.0.1")
            try:
                paths = supervisor.start()
                process = supervisor.processes[2]
                with connect_to_server(paths[2]) as connection:
                    packet = FilePacket(file_id="paced", target_receiver=2)
                    payload = packet.SerializeToString()
                    send_message(connection, payload)
                    assert listener.recv(65535) == payload
                    process.terminate()
                    assert process.wait(timeout=5) == 0
            finally:
                supervisor.stop()
