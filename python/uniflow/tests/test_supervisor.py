from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uniflow.process_pool import WorkerProcessPool, WorkerSpec
from uniflow.supervisor import (
    ReceiverSupervisor,
    SenderSupervisor,
    _find_go_dir,
)


def test_find_go_dir() -> None:
    go_dir = _find_go_dir()
    assert (go_dir / "go.mod").is_file()


def test_sender_supervisor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPC_SOCKET_PATH", "/tmp/uniflow-test.sock")
    monkeypatch.setenv("PORT", "9100")
    monkeypatch.setenv("UNIFLOW_WORKERS", "3")

    submitted: list[WorkerSpec] = []
    fake_pool = MagicMock(spec=WorkerProcessPool)

    def capture_submit(spec: WorkerSpec) -> None:
        submitted.append(spec)

    fake_pool.submit = capture_submit
    fake_pool.shutdown = MagicMock()

    monkeypatch.setattr(
        "uniflow.supervisor.WorkerProcessPool",
        lambda max_workers: fake_pool,
    )
    monkeypatch.setattr(
        "uniflow.supervisor._build_binary",
        lambda go_dir: go_dir / ".bin" / "uniflow",
    )
    monkeypatch.setattr(
        "uniflow.supervisor._wait_for_sockets",
        lambda paths: None,
    )

    supervisor = SenderSupervisor()
    paths = supervisor.start()
    assert len(paths) == 3
    assert len(submitted) == 3
    assert submitted[0].args == ["send"]
    assert submitted[0].env["IPC_SOCKET_PATH"] == "/tmp/uniflow-test.sock.0"
    assert submitted[0].env["UDP_PORTS"] == "9100,9101,9102"
    assert submitted[0].env["UNIFLOW_WORKER_INDEX"] == "0"
    assert submitted[0].env["UNIFLOW_WORKER_COUNT"] == "3"
    assert submitted[0].env["UNIFLOW_SESSION_ID"] == submitted[1].env[
        "UNIFLOW_SESSION_ID"
    ]

    supervisor.stop()
    fake_pool.shutdown.assert_called_once()


def test_sender_supervisor_stop_unlinks_sockets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sock0 = tmp_path / "sock.0"
    sock0.touch()
    monkeypatch.setenv("UNIFLOW_WORKERS", "3")

    fake_pool = MagicMock(spec=WorkerProcessPool)
    monkeypatch.setattr(
        "uniflow.supervisor.WorkerProcessPool",
        lambda max_workers: fake_pool,
    )
    monkeypatch.setattr(
        "uniflow.supervisor._build_binary",
        lambda go_dir: go_dir / ".bin" / "uniflow",
    )
    monkeypatch.setattr(
        "uniflow.supervisor._wait_for_sockets",
        lambda paths: None,
    )

    supervisor = SenderSupervisor()
    supervisor.sender_socket_paths = [str(sock0)]
    supervisor.pool = fake_pool
    supervisor.stop()
    assert not sock0.exists()
    fake_pool.shutdown.assert_called_once()


def test_receiver_supervisor_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PORT", "9100")
    monkeypatch.setenv("UNIFLOW_WORKERS", "3")

    submitted: list[WorkerSpec] = []
    fake_pool = MagicMock(spec=WorkerProcessPool)
    fake_pool.submit = lambda spec: submitted.append(spec)
    fake_pool.shutdown = MagicMock()

    monkeypatch.setattr(
        "uniflow.supervisor.WorkerProcessPool",
        lambda max_workers: fake_pool,
    )
    monkeypatch.setattr(
        "uniflow.supervisor._build_binary",
        lambda go_dir: go_dir / ".bin" / "uniflow",
    )

    receive_base = tmp_path / "in"
    supervisor = ReceiverSupervisor(receive_base=receive_base)
    supervisor.start()
    assert len(submitted) == 3
    assert submitted[0].env["UDP_PORT"] == "9100"
    assert submitted[1].env["UDP_PORT"] == "9101"
    assert submitted[2].env["UDP_PORT"] == "9102"
    assert submitted[0].env["RECEIVE_DIR"] == str(receive_base)
    assert submitted[0].env["UNIFLOW_WORKER_INDEX"] == "0"
    assert submitted[0].env["UNIFLOW_WORKER_COUNT"] == "3"
    assert submitted[0].args == ["recv", str(receive_base)]

    supervisor.stop()
    fake_pool.shutdown.assert_called_once()
