import socket
from pathlib import Path
from queue import Queue
from threading import Event, Thread

from client.common.ipc import create_server, receive_message


def handle_connection(connection: socket.socket, messages: Queue) -> None:
    with connection:
        try:
            while True:
                message = receive_message(connection)
                if message is None:
                    return
                messages.put(message)
        except (ConnectionError, OSError, ValueError) as error:
            print(f"Receiver IPC error: {error}", flush=True)


def listen_to_receivers(
    socket_path: Path,
    messages: Queue,
    stop_event: Event,
    ready_event: Event,
) -> None:
    server = create_server(socket_path)
    server.settimeout(0.5)
    ready_event.set()

    try:
        while not stop_event.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                if stop_event.is_set():
                    break
                raise

            thread = Thread(
                target=handle_connection,
                args=(connection, messages),
                daemon=True,
            )
            thread.start()
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)
