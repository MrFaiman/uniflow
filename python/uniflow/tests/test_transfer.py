import pytest

from uniflow.transfer import (
    LARGE_FILE_MAX_BYTES,
    SMALL_FILE_MAX_BYTES,
    PairPool,
    transfer_mode_for_size,
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
