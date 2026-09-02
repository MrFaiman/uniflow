from unittest.mock import MagicMock, patch

import pytest

from uniflow.process_pool import (
    WorkerProcessPool,
    WorkerSpec,
    _go_worker_entry,
)


def test_worker_spec_frozen() -> None:
    spec = WorkerSpec(
        binary="/bin/uniflow",
        cwd="/go",
        env={"UDP_PORT": "9000"},
        args=["recv", "/tmp/in"],
    )
    assert spec.args == ["recv", "/tmp/in"]


def test_pool_shutdown_clears_futures() -> None:
    pool = WorkerProcessPool(max_workers=1)
    fake_future = MagicMock()
    fake_future.done.return_value = True
    pool._futures = [fake_future]
    pool.shutdown()
    assert pool._futures == []


def test_pool_wait_for_failure_raises_on_worker_exit() -> None:
    pool = WorkerProcessPool(max_workers=1)
    fake_future = MagicMock()
    fake_future.done.return_value = True
    fake_future.exception.return_value = None
    fake_future.result.return_value = 1
    pool._futures = [fake_future]

    with pytest.raises(RuntimeError, match="worker exited with code 1"):
        pool.wait_for_failure(poll_interval=0.01)


def test_go_worker_entry_terminates_process() -> None:
    with patch("uniflow.process_pool.subprocess.Popen") as popen:
        proc = MagicMock()
        proc.wait.return_value = 0
        proc.poll.return_value = None
        popen.return_value = proc
        spec = WorkerSpec(
            binary="/bin/uniflow",
            cwd="/go",
            env={},
            args=["send"],
        )
        assert _go_worker_entry(spec) == 0
        proc.terminate.assert_called_once()
