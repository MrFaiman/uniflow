import threading
from pathlib import Path
from uuid import uuid4

import pytest

from client.common.ipc import (
    connect_to_server,
    create_server,
    receive_message,
    send_message,
)


def test_unix_socket():
    socket_path = Path(f"/tmp/uniflow-test-{uuid4().hex}.sock")
    server = create_server(socket_path)
    received: list[bytes | None] = []

    try:

        def server_loop() -> None:
            connection, _ = server.accept()
            with connection:
                received.append(receive_message(connection))
                received.append(receive_message(connection))

        thread = threading.Thread(target=server_loop)
        thread.start()

        client = connect_to_server(socket_path)
        send_message(client, b"Hello")
        client.close()

        thread.join()
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)

    assert received == [b"Hello", None]


def test_server_does_not_remove_regular_file(tmp_path):
    path = tmp_path / "keep"
    path.write_text("keep")
    with pytest.raises(ValueError):
        create_server(path)
    assert path.read_text() == "keep"
