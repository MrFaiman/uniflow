import socket
import struct
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from uuid import uuid4

from client.common.ipc import receive_message
from client.session_manager.listener import listen_to_receivers


def send_message(connection: socket.socket, data: bytes) -> None:
    connection.sendall(struct.pack("!I", len(data)) + data)


def test_receive_message_handles_parts():
    sender, receiver = socket.socketpair()
    message = b"Hello Protobuf"
    header = struct.pack("!I", len(message))

    sender.sendall(header[:2])
    sender.sendall(header[2:] + message[:3])
    sender.sendall(message[3:])
    sender.close()

    assert receive_message(receiver) == message
    assert receive_message(receiver) is None
    receiver.close()


def test_multiple_receivers_use_one_socket():
    socket_path = Path(f"/tmp/uniflow-test-{uuid4().hex}.sock")
    messages = Queue()
    stop_event = Event()
    ready_event = Event()

    thread = Thread(
        target=listen_to_receivers,
        args=(socket_path, messages, stop_event, ready_event),
        daemon=True,
    )
    thread.start()
    assert ready_event.wait(timeout=1)

    first = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        first.connect(str(socket_path))
        second.connect(str(socket_path))

        send_message(first, b"receiver zero")
        send_message(second, b"receiver one")

        received = {messages.get(timeout=1), messages.get(timeout=1)}
    finally:
        first.close()
        second.close()
        stop_event.set()
        thread.join(timeout=2)
        socket_path.unlink(missing_ok=True)

    assert received == {b"receiver zero", b"receiver one"}
