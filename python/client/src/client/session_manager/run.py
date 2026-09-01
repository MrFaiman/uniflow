from pathlib import Path
from queue import Queue
from threading import Thread

from client.session_manager.listener import (
    listen_to_receiver,
)
from client.session_manager.manager import (
    SessionManager,
)


SOCKET_PATHS = [
    Path("/tmp/uniflow_receiver_0.sock"),
    Path("/tmp/uniflow_receiver_1.sock"),
    Path("/tmp/uniflow_receiver_2.sock"),
]


def run_session_manager(
    output_folder: Path,
) -> None:
    manager = SessionManager(
        output_folder
    )

    messages = Queue()

    for receiver_id, socket_path in enumerate(
        SOCKET_PATHS
    ):
        thread = Thread(
            target=listen_to_receiver,
            args=(
                receiver_id,
                socket_path,
                messages,
            ),
            daemon=True,
        )

        thread.start()

    print(
        "Session Manager is running"
    )

    while True:
        receiver_id, message = (
            messages.get()
        )

        manager.handle_serialized_packet(
            receiver_id,
            message,
        )


def main() -> None:
    run_session_manager(
        Path("received_files")
    )


if __name__ == "__main__":
    main()