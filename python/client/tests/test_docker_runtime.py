from pathlib import Path

from client.file_monitor import run as monitor_run
from client.session_manager import run as manager_run


def test_monitor_uses_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "IPC_SOCKET_PATH",
        "/tmp/custom.sock",
    )

    monkeypatch.setenv(
        "UNIFLOW_WATCH_DIR",
        "/data/custom-out",
    )

    monkeypatch.setenv(
        "UNIFLOW_WORKERS",
        "5",
    )

    monkeypatch.setenv(
        "UNIFLOW_WATCH_POLLING",
        "2.5",
    )

    assert (
        monitor_run.get_socket_path()
        == Path("/tmp/custom.sock")
    )

    assert (
        monitor_run.get_watch_folder()
        == Path("/data/custom-out")
    )

    assert (
        monitor_run.get_worker_count()
        == 5
    )

    assert (
        monitor_run.get_poll_interval()
        == 2.5
    )


def test_session_manager_uses_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "IPC_SOCKET_PATH",
        "/tmp/rx.sock",
    )

    monkeypatch.setenv(
        "RECEIVE_DIR",
        "/data/custom-in",
    )

    assert (
        manager_run.get_socket_path()
        == Path("/tmp/rx.sock")
    )

    assert (
        manager_run.get_output_folder()
        == Path("/data/custom-in")
    )