from pathlib import Path

import pytest

from client.cli import create_parser


def test_send_command_requires_router():
    parser = create_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["send"])


def test_send_command_with_router():
    parser = create_parser()
    args = parser.parse_args(["send", "/data/out", "router"])

    assert args.command == "send"
    assert args.folder == Path("/data/out")
    assert args.router == "router"


def test_recv_command():
    parser = create_parser()
    args = parser.parse_args(["recv", "/data/in"])

    assert args.command == "recv"
    assert args.folder == Path("/data/in")


@pytest.mark.parametrize("command", ["send", "recv"])
def test_command_defaults_to_cwd(command, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    argv = [command, "router"] if command == "send" else [command]
    args = create_parser().parse_args(argv)

    assert args.folder == tmp_path
    if command == "send":
        assert args.router == "router"
