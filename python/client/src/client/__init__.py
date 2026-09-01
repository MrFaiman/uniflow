import argparse
import logging
from pathlib import Path

from client.ipc import send

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Folder path")
    parser.add_argument("target_ip", help="Target IP address")
    return parser.parse_args(argv)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    args = parse_args()
    payload = f"{args.folder} {args.target_ip}".encode()
    logger.info(
        "sending ping folder=%s target_ip=%s", args.folder, args.target_ip
    )
    response = send("ping", payload)
    if response.success:
        logger.info("response: %s", response.message)
    else:
        logger.error("response: %s", response.message)
