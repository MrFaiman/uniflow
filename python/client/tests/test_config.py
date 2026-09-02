from pathlib import Path

from client.common.config import (
    get_poll_interval,
    get_socket_path,
    get_worker_count,
)


def test_default_config(
    monkeypatch,
):
    monkeypatch.delenv(
        "IPC_SOCKET_PATH",
        raising=False,
    )

    monkeypatch.delenv(
        "UNIFLOW_WORKERS",
        raising=False,
    )

    monkeypatch.delenv(
        "UNIFLOW_WATCH_POLLING",
        raising=False,
    )

    assert (
        get_socket_path()
        == Path("/tmp/proto_ipc.sock")
    )

    assert get_worker_count() == 3
    assert get_poll_interval() == 1.0


def test_config_from_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "IPC_SOCKET_PATH",
        "/tmp/test.sock",
    )

    monkeypatch.setenv(
        "UNIFLOW_WORKERS",
        "5",
    )

    monkeypatch.setenv(
        "UNIFLOW_WATCH_POLLING",
        "2",
    )

    assert (
        get_socket_path()
        == Path("/tmp/test.sock")
    )

    assert get_worker_count() == 5
    assert get_poll_interval() == 2.0