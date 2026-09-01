import argparse
import logging
from pathlib import Path

from client.utils import configure_logging
from client.watch import watch_folder

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Folder path")
    parser.add_argument("target_ip", help="Target IP address")
    return parser.parse_args(argv)


def main() -> None:
    configure_logging()
    args = parse_args()
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        logger.error("not a directory: %s", folder)
        raise SystemExit(1)
    watch_folder(folder, args.target_ip)
