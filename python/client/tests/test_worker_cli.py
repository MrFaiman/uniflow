"""Exercise the compiled worker's command-line and startup error handling."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def net_binary():
    binary = os.environ.get("UNIFLOW_NET_BINARY")
    if not binary:
        pytest.skip("set UNIFLOW_NET_BINARY to run compiled worker integration tests")
    assert Path(binary).is_file()
    return str(Path(binary).resolve())


@pytest.fixture
def run_cli(net_binary, tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UNIFLOW_")
        and key not in {"IPC_SOCKET_PATH", "ROUTER_HOST", "UDP_PORT"}
    }
    env.update(
        IPC_SOCKET_PATH=str(tmp_path / "worker.sock"),
        ROUTER_HOST="127.0.0.1",
    )

    def run(*args, extra_env=None):
        return subprocess.run(
            [net_binary, *args],
            cwd=tmp_path,
            env=env | (extra_env or {}),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    return run


@pytest.mark.parametrize("command", [None, "send", "recv"])
def test_help_describes_command_and_exits_successfully(run_cli, command):
    args = ["--help"] if command is None else [command, "--help"]
    result = run_cli(*args)

    assert result.returncode == 0
    assert result.stderr == ""
    assert "Usage: uniflow-net" in result.stdout
    if command is None:
        assert "--verbose" in result.stdout
        assert "--log-file" in result.stdout
        assert "send" in result.stdout
        assert "recv" in result.stdout
    else:
        assert f"uniflow-net {command}" in result.stdout
        description = "sender worker" if command == "send" else "receiver worker"
        assert description in result.stdout


def test_version_exits_successfully(run_cli):
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == "1.0.0"
    assert result.stderr == ""


@pytest.mark.parametrize("args", [(), ("unknown-command",)])
def test_missing_or_unknown_command_reports_usage(run_cli, args):
    result = run_cli(*args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Usage: uniflow-net" in result.stderr
    assert "send" in result.stderr
    assert "recv" in result.stderr
    if args:
        assert "unknown-command" in result.stderr


@pytest.mark.parametrize(
    ("args", "diagnostic"),
    [
        (("--unknown",), "Unknown argument: --unknown"),
        (("send", "--unknown"), "Unknown argument: --unknown"),
        (("recv", "--unknown"), "Unknown argument: --unknown"),
        (("--log-file",), "Too few arguments for '--log-file'"),
    ],
)
def test_malformed_flags_report_argument_error(run_cli, args, diagnostic):
    result = run_cli(*args)

    assert result.returncode == 2
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert "Usage: uniflow-net" in result.stderr


@pytest.mark.parametrize("command", ["send", "recv"])
@pytest.mark.parametrize(
    ("name", "value", "diagnostic"),
    [
        ("UDP_PORT", "0", "UDP_PORT must be in range [1, 65535]"),
        ("UDP_PORT", "65536", "UDP_PORT must be in range [1, 65535]"),
        ("UDP_PORT", "9000junk", "invalid integer environment variable: UDP_PORT"),
        ("UNIFLOW_WORKER_INDEX", "3", "UNIFLOW_WORKER_INDEX must be in range [0, 2]"),
    ],
)
def test_invalid_worker_configuration_is_fatal(
    run_cli, command, name, value, diagnostic
):
    result = run_cli(command, extra_env={name: value})

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"[ERROR] fatal: {diagnostic}" in result.stderr


@pytest.mark.parametrize(
    ("value", "diagnostic"),
    [
        ("-1", "UNIFLOW_SEND_RATE_MBPS must be finite and non-negative"),
        ("nan", "invalid numeric environment variable: UNIFLOW_SEND_RATE_MBPS"),
        ("1junk", "invalid numeric environment variable: UNIFLOW_SEND_RATE_MBPS"),
    ],
)
def test_invalid_sender_rate_is_fatal(run_cli, value, diagnostic):
    result = run_cli("send", extra_env={"UNIFLOW_SEND_RATE_MBPS": value})

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"[ERROR] fatal: {diagnostic}" in result.stderr


@pytest.mark.parametrize("command", ["send", "recv"])
def test_verbose_accepts_worker_command_and_preserves_fatal_diagnostic(
    run_cli, command
):
    result = run_cli("--verbose", command, extra_env={"UDP_PORT": "0"})

    assert result.returncode == 1
    assert result.stdout == ""
    assert "[ERROR] fatal: UDP_PORT must be in range [1, 65535]" in result.stderr


@pytest.mark.parametrize("source", ["environment", "argument", "override"])
def test_log_file_records_startup_failure_and_appends(run_cli, tmp_path, source):
    log_file = tmp_path / "nested" / "worker.log"
    env_log_file = tmp_path / "unused.log"
    args = []
    env = {"UDP_PORT": "0"}
    if source == "environment":
        env["UNIFLOW_LOG_FILE"] = str(log_file)
    else:
        args.extend(["--log-file", str(log_file)])
        if source == "override":
            env["UNIFLOW_LOG_FILE"] = str(env_log_file)

    first = run_cli(*args, "send", extra_env=env)
    assert first.returncode == 1
    assert first.stdout == ""
    assert log_file.is_file()
    initial_logs = log_file.read_text()
    assert initial_logs == first.stderr
    assert f"[INFO] logging to file {log_file}" in initial_logs
    assert "[ERROR] fatal: UDP_PORT must be in range [1, 65535]" in initial_logs

    second = run_cli(*args, "recv", extra_env=env)
    assert second.returncode == 1
    assert second.stdout == ""
    assert log_file.read_text() == initial_logs + second.stderr
    assert not env_log_file.exists()


def test_empty_log_file_argument_disables_environment_log_file(run_cli, tmp_path):
    env_log_file = tmp_path / "unused.log"
    result = run_cli(
        "--log-file",
        "",
        "send",
        extra_env={"UNIFLOW_LOG_FILE": str(env_log_file), "UDP_PORT": "0"},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "[ERROR] fatal: UDP_PORT must be in range [1, 65535]" in result.stderr
    assert "logging to file" not in result.stderr
    assert not env_log_file.exists()


@pytest.mark.parametrize("source", ["environment", "argument"])
def test_log_file_open_failure_is_fatal_before_worker_startup(
    run_cli, tmp_path, source
):
    log_directory = tmp_path / "directory"
    log_directory.mkdir()
    args = []
    env = {"UDP_PORT": "0"}
    if source == "environment":
        env["UNIFLOW_LOG_FILE"] = str(log_directory)
    else:
        args.extend(["--log-file", str(log_directory)])

    result = run_cli(*args, "send", extra_env=env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"[ERROR] fatal: failed to open log file: {log_directory}" in result.stderr
    assert "UDP_PORT" not in result.stderr
    assert log_directory.is_dir()
    assert list(log_directory.iterdir()) == []
