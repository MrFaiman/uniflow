import struct
import threading

from client.common.ipc import (
    connect_to_server,
    create_server,
    send_message,
)


def test_unix_socket(tmp_path):
    socket_path = tmp_path / "test.sock"

    server = create_server(socket_path)

    def receive_message():
        connection, _ = server.accept()

        size_data = connection.recv(4)
        message_size = struct.unpack("!I", size_data)[0]

        message = connection.recv(message_size)

        assert message == b"Hello"

        connection.close()

    thread = threading.Thread(target=receive_message)
    thread.start()

    client = connect_to_server(socket_path)

    send_message(client, b"Hello")

    client.close()

    thread.join()
    server.close()