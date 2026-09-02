import os
from pathlib import Path
from queue import Queue
from threading import Thread

from client.session_manager.listener import (
    listen_to_receivers,
)
from client.session_manager.manager import (
    SessionManager,
)

DEFAULT_SOCKET_PATH = "/tmp/proto_ipc.sock"
DEFAULT_RECEIVE_DIR = "/data/in"


def get_socket_path() -> Path:
    return Path(
        os.getenv(
            "IPC_SOCKET_PATH",
            DEFAULT_SOCKET_PATH,
        )
    )


def get_output_folder() -> Path:
    return Path(
        os.getenv(
            "RECEIVE_DIR",
            DEFAULT_RECEIVE_DIR,
        )
    )


def run_session_manager(
    output_folder: Path,
    socket_path: Path,
) -> None:
    manager = SessionManager(
        output_folder
    )

    messages = Queue()

    thread = Thread(
        target=listen_to_receivers,
        args=(
            socket_path,
            messages,
        ),
        daemon=True,
    )

    thread.start()

    print(
        f"Session Manager writing to "
        f"{output_folder}"
    )

    while True:
        message = messages.get()

        manager.handle_serialized_packet(
            message
        )


def main() -> None:
    run_session_manager(
        get_output_folder(),
        get_socket_path(),
    )


if __name__ == "__main__":
    main()