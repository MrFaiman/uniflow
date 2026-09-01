import pytest

from uniflow.transfer import (
    LARGE_FILE_MAX_BYTES,
    SMALL_FILE_MAX_BYTES,
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
