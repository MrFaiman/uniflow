import argparse
import logging
from pathlib import Path

from uniflow.ipc import Ipc
from uniflow.supervisor import ReceiverSupervisor, SenderSupervisor
from uniflow.utils import configure_logging
from uniflow.watch import watch_folder

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uniflow")
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", help="watch a folder and send file changes")
    send.add_argument("dir_path", type=Path, help="Folder to watch")
    send.add_argument("target_ip", help="Destination IP address")

    sub.add_parser(
        "receive",
        help="receive files over UDP into a directory",
    ).add_argument("dir_path", type=Path, help="Directory for received files")

    return parser


def parse_send_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="uniflow send")
    parser.add_argument("dir_path", type=Path, help="Folder to watch")
    parser.add_argument("target_ip", help="Destination IP address")
    return parser.parse_args(argv)


def parse_receive_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="uniflow receive")
    parser.add_argument(
        "dir_path",
        type=Path,
        help="Directory for received files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    args = build_parser().parse_args(argv)

    if args.command == "send":
        run_send(args.dir_path, args.target_ip)
    elif args.command == "receive":
        run_receive(args.dir_path)


def run_send(folder: Path, target_ip: str) -> None:
    folder = folder.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        logger.error("not a directory: %s", folder)
        raise SystemExit(1)

    supervisor = SenderSupervisor()
    try:
        socket_paths = supervisor.start()
        ipc_clients = [Ipc(path) for path in socket_paths]
        watch_folder(folder, target_ip, ipc_clients)
    finally:
        supervisor.stop()


def run_receive(dir_path: Path) -> None:
    receive_base = dir_path.expanduser().resolve()
    receive_base.mkdir(parents=True, exist_ok=True)

    supervisor = ReceiverSupervisor(receive_base=receive_base)
    try:
        supervisor.start()
        supervisor.wait()
    finally:
        supervisor.stop()


if __name__ == "__main__":
    main()
