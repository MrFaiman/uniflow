from pathlib import Path

import pytest

from client.common.config import (
    get_base_port,
    get_poll_interval,
    get_repair_percent,
    get_sender_socket_path,
    get_socket_path,
    get_worker_count,
)


def test_default_config(monkeypatch):
    for name in (
        "IPC_SOCKET_PATH",
        "UNIFLOW_WORKERS",
        "UNIFLOW_WATCH_POLLING",
        "PORT",
        "UNIFLOW_FEC_REPAIR_PERCENT",
    ):
        monkeypatch.delenv(name, raising=False)

    assert get_socket_path() == Path("/tmp/proto_ipc.sock")
    assert get_sender_socket_path(2) == Path("/tmp/proto_ipc.sock.sender.2")
    assert get_worker_count() == 3
    assert get_poll_interval() == 1.0
    assert get_base_port() == 9000
    assert get_repair_percent() == 20


def test_trio_requires_exactly_three_workers(monkeypatch):
    monkeypatch.setenv("UNIFLOW_WORKERS", "2")
    with pytest.raises(ValueError):
        get_worker_count()
