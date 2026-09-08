from pathlib import Path

import pytest

from client.cli import create_parser


def test_send_command_requires_router():
    parser = create_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["send", "/data/out"])


def test_send_command_with_router():
    parser = create_parser()
    args = parser.parse_args(["send", "/data/out", "router"])

    assert args.command == "send"
    assert args.folder == Path("/data/out")
    assert args.router == "router"


def test_receive_command():
    parser = create_parser()
    args = parser.parse_args(["receive", "/data/in"])

    assert args.command == "receive"
    assert args.folder == Path("/data/in")
