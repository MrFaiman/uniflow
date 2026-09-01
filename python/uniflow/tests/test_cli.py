from pathlib import Path

import pytest

from uniflow.cli import build_parser, parse_receive_args, parse_send_args


def test_parse_send_args() -> None:
    args = parse_send_args(["/tmp", "127.0.0.1"])
    assert args.dir_path == Path("/tmp")
    assert args.target_ip == "127.0.0.1"


def test_parse_send_args_requires_arguments() -> None:
    with pytest.raises(SystemExit):
        parse_send_args([])


def test_parse_receive_args() -> None:
    args = parse_receive_args(["/tmp/in"])
    assert args.dir_path == Path("/tmp/in")


def test_parse_receive_args_requires_arguments() -> None:
    with pytest.raises(SystemExit):
        parse_receive_args([])


def test_build_parser_send() -> None:
    args = build_parser().parse_args(["send", "/tmp", "10.0.0.2"])
    assert args.command == "send"
    assert args.dir_path == Path("/tmp")
    assert args.target_ip == "10.0.0.2"


def test_build_parser_receive() -> None:
    args = build_parser().parse_args(["receive", "/tmp/in"])
    assert args.command == "receive"
    assert args.dir_path == Path("/tmp/in")
