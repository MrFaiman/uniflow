import threading
import time
from pathlib import Path

import pytest

from uniflow.transfer import (
    LARGE_FILE_MAX_BYTES,
    SMALL_FILE_MAX_BYTES,
    PairPool,
    transfer_mode_for_size,
    wait_until_stable,
)


def test_small_file_uses_single_pair() -> None:
    assert transfer_mode_for_size(0) == "single_pair"
    assert transfer_mode_for_size(SMALL_FILE_MAX_BYTES - 1) == "single_pair"


def test_large_file_uses_coordinated() -> None:
    assert transfer_mode_for_size(SMALL_FILE_MAX_BYTES) == "coordinated"
    assert transfer_mode_for_size(SMALL_FILE_MAX_BYTES + 1) == "coordinated"
    assert transfer_mode_for_size(LARGE_FILE_MAX_BYTES) == "coordinated"


def test_file_over_limit_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds maximum"):
        transfer_mode_for_size(LARGE_FILE_MAX_BYTES + 1)


def test_max_file_bytes_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIFLOW_MAX_FILE_BYTES", str(2 * 1024 * 1024 * 1024))
    assert transfer_mode_for_size(LARGE_FILE_MAX_BYTES + 1) == "coordinated"
    with pytest.raises(ValueError, match="exceeds maximum"):
        transfer_mode_for_size(2 * 1024 * 1024 * 1024 + 1)


def test_pair_pool_cycles_released_pairs() -> None:
    pool = PairPool(2)
    first = pool.acquire()
    pool.release(first)
    second = pool.acquire()
    assert (first, second) == (0, 1)


def test_wait_until_stable_returns_true_for_settled_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settled.bin"
    path.write_bytes(b"x" * 128)
    assert wait_until_stable(path, quiet_period=0.05, poll_interval=0.01)


def test_wait_until_stable_waits_for_a_growing_file(tmp_path: Path) -> None:
    """A file still being written must not be reported as ready.

    Sending mid-write transfers a truncated prefix, and because the sender
    hashes whatever it read, the receiver verifies that truncated content as
    correct — a silently wrong file rather than a detected failure.
    """
    path = tmp_path / "growing.bin"
    path.write_bytes(b"start")

    stop = threading.Event()

    def grow() -> None:
        for _ in range(6):
            if stop.is_set():
                return
            with open(path, "ab") as handle:
                handle.write(b"y" * 4096)
            time.sleep(0.05)

    writer = threading.Thread(target=grow)
    writer.start()
    try:
        assert wait_until_stable(path, quiet_period=0.15, poll_interval=0.02)
        # It may only report ready once writing has actually finished.
        assert not writer.is_alive()
        size_when_ready = path.stat().st_size
        assert size_when_ready == 5 + 6 * 4096
    finally:
        stop.set()
        writer.join()


def test_wait_until_stable_returns_false_for_missing_file(
    tmp_path: Path,
) -> None:
    assert not wait_until_stable(
        tmp_path / "nope.bin",
        quiet_period=0.05,
        poll_interval=0.01,
    )
