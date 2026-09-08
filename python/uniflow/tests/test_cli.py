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


def test_parse_receive_args_defaults_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert parse_receive_args([]).dir_path == tmp_path


def test_parse_send_args_defaults_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    args = parse_send_args(["127.0.0.1"])
    assert args.dir_path == tmp_path
    assert args.target_ip == "127.0.0.1"


@pytest.mark.parametrize("command", ["send", "recv"])
def test_build_parser_defaults_to_cwd(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    argv = [command, "127.0.0.1"] if command == "send" else [command]
    args = build_parser().parse_args(argv)
    assert args.dir_path == tmp_path
    if command == "send":
        assert args.target_ip == "127.0.0.1"


def test_build_parser_send_requires_target_ip() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["send"])


def test_build_parser_send() -> None:
    args = build_parser().parse_args(["send", "/tmp", "10.0.0.2"])
    assert args.command == "send"
    assert args.dir_path == Path("/tmp")
    assert args.target_ip == "10.0.0.2"


def test_build_parser_recv() -> None:
    args = build_parser().parse_args(["recv", "/tmp/in"])
    assert args.command == "recv"
    assert args.dir_path == Path("/tmp/in")
