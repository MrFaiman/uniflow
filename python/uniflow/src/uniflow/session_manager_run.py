"""Entrypoint for the Session Manager process (RX machine)."""

import argparse
import logging
from pathlib import Path

from uniflow.session_manager import SessionManager
from uniflow.utils import configure_logging, session_socket_path

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="uniflow-session-manager")
    parser.add_argument(
        "dir_path",
        type=Path,
        help="Directory for reconstructed files",
    )
    args = parser.parse_args(argv)

    receive_dir = args.dir_path.expanduser().resolve()
    receive_dir.mkdir(parents=True, exist_ok=True)

    manager = SessionManager(session_socket_path(), receive_dir)
    manager.start()
    try:
        manager.serve_forever()
    except KeyboardInterrupt:
        logger.info("session manager stopping")
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
