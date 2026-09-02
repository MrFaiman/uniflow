from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from client.common import go_daemon


def test_find_go_binary_from_env(tmp_path: Path):
    binary = tmp_path / "uniflow"
    binary.write_text("", encoding="utf-8")

    with patch.dict(
        "os.environ",
        {"UNIFLOW_GO_BIN": str(binary)},
        clear=False,
    ):
        assert go_daemon.find_go_binary() == binary


def test_find_go_binary_missing_env(tmp_path: Path):
    missing = tmp_path / "missing"

    with patch.dict(
        "os.environ",
        {"UNIFLOW_GO_BIN": str(missing)},
        clear=False,
    ):
        with pytest.raises(FileNotFoundError):
            go_daemon.find_go_binary()


def test_run_go_daemon_skips_when_disabled():
    with patch.dict("os.environ", {"UNIFLOW_SKIP_GO": "1"}, clear=False):
        with go_daemon.run_go_daemon("send", "/tmp/out") as proc:
            assert proc.poll() == 0


def test_run_go_daemon_starts_binary(tmp_path: Path):
    binary = tmp_path / "uniflow"
    binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)

    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 0]

    with patch.dict(
        "os.environ",
        {"UNIFLOW_GO_BIN": str(binary)},
        clear=False,
    ):
        with patch(
            "client.common.go_daemon.subprocess.Popen",
            return_value=mock_proc,
        ) as popen:
            with go_daemon.run_go_daemon("send", "/tmp/out", "router"):
                popen.assert_called_once()

    mock_proc.terminate.assert_called_once()


def test_find_go_binary_from_repo(tmp_path: Path, monkeypatch):
    repo_go = tmp_path / "go" / "uniflow"
    repo_go.parent.mkdir(parents=True)
    repo_go.write_text("", encoding="utf-8")

    module_path = (
        tmp_path
        / "python"
        / "client"
        / "src"
        / "client"
        / "common"
        / "go_daemon.py"
    )
    module_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("UNIFLOW_GO_BIN", raising=False)
    monkeypatch.setenv("PATH", "")

    with patch(
        "client.common.go_daemon.Path.resolve",
        return_value=module_path,
    ):
        assert go_daemon.find_go_binary() == repo_go


def test_wait_for_socket(tmp_path: Path):
    socket_path = tmp_path / "test.sock"
    socket_path.write_text("", encoding="utf-8")

    go_daemon.wait_for_socket(socket_path, timeout_sec=1.0)


def test_wait_for_socket_timeout(tmp_path: Path):
    with pytest.raises(TimeoutError):
        go_daemon.wait_for_socket(
            tmp_path / "missing.sock",
            timeout_sec=0.2,
            poll_interval=0.05,
        )
