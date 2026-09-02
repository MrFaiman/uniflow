from pathlib import Path
from queue import Queue
from threading import Thread

from client.common.config import get_socket_path
from client.common.go_daemon import run_go_daemon, wait_for_socket
from client.session_manager.listener import (
    listen_to_receivers,
)
from client.session_manager.manager import (
    SessionManager,
)


def process_messages(
    manager: SessionManager,
    messages: Queue,
) -> None:
    while True:
        message = messages.get()
        manager.handle_serialized_packet(message)


def run_session_manager(
    output_folder: Path,
) -> None:
    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    manager = SessionManager(
        output_folder
    )

    messages = Queue()

    listener_thread = Thread(
        target=listen_to_receivers,
        args=(
            get_socket_path(),
            messages,
        ),
        daemon=True,
    )

    listener_thread.start()

    socket_path = get_socket_path()
    wait_for_socket(socket_path)

    print(
        f"Receiving files into: "
        f"{output_folder}"
    )

    recv_args = ["receive", str(output_folder)]

    with run_go_daemon(*recv_args):
        process_messages(
            manager,
            messages,
        )