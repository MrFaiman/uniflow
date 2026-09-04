import argparse
import signal
from pathlib import Path

from client.file_monitor.run import run_file_monitor
from client.session_manager.run import run_session_manager


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uniflow",
        description="Reliable one-way file transfer",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    send = commands.add_parser("send", help="Run the TX File Monitor")
    send.add_argument("folder", type=Path, help="Folder to monitor")
    send.add_argument("router", help="Router hostname or IP")

    receive = commands.add_parser("receive", help="Run the RX Session Manager")
    receive.add_argument("folder", type=Path, help="Folder for reconstructed files")

    return parser


def _handle_sigterm(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    args = create_parser().parse_args()

    if args.command == "send":
        run_file_monitor(args.folder, args.router)
    else:
        run_session_manager(args.folder)


if __name__ == "__main__":
    main()
