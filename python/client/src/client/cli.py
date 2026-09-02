import argparse
from pathlib import Path

from client.file_monitor.run import run_file_monitor
from client.session_manager.run import run_session_manager


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uniflow",
        description="Uniflow file transfer system",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    send_parser = commands.add_parser(
        "send",
        help="Run the TX File Monitor",
    )

    send_parser.add_argument(
        "folder",
        type=Path,
        help="Folder to monitor for files",
    )

    send_parser.add_argument(
        "router",
        nargs="?",
        help="Router hostname for future Sender integration",
    )

    receive_parser = commands.add_parser(
        "receive",
        help="Run the RX Session Manager",
    )

    receive_parser.add_argument(
        "folder",
        type=Path,
        help="Folder where received files are saved",
    )

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "send":
        run_file_monitor(args.folder)

    elif args.command == "receive":
        run_session_manager(args.folder)


if __name__ == "__main__":
    main()