from pathlib import Path

from client.cli import create_parser


def test_send_command():
    parser = create_parser()

    args = parser.parse_args(
        [
            "send",
            "/data/out",
        ]
    )

    assert args.command == "send"
    assert args.folder == Path("/data/out")
    assert args.target_ip is None


def test_send_command_with_target_ip():
    parser = create_parser()

    args = parser.parse_args(
        [
            "send",
            "/data/out",
            "127.0.0.1",
        ]
    )

    assert args.command == "send"
    assert args.folder == Path("/data/out")
    assert args.target_ip == "127.0.0.1"


def test_receive_command():
    parser = create_parser()

    args = parser.parse_args(
        [
            "receive",
            "/data/in",
        ]
    )

    assert args.command == "receive"
    assert args.folder == Path("/data/in")