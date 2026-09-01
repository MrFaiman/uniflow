from pathlib import Path

import pytest

from client import parse_args


def test_parse_args() -> None:
    args = parse_args(["/tmp", "127.0.0.1"])
    assert args.folder == Path("/tmp")
    assert args.target_ip == "127.0.0.1"


def test_parse_args_requires_folder_and_target_ip() -> None:
    with pytest.raises(SystemExit):
        parse_args([])
