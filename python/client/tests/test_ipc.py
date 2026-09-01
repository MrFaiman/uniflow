import threading

from client.common.ipc import connect_to_server, create_server


def test_unix_socket(tmp_path):
    socket_path = tmp_path / "test.sock"

    server = create_server(socket_path)

    def receive_message():
        connection, _ = server.accept()
        message = connection.recv(1024)

        assert message == b"Hello"

        connection.close()

    thread = threading.Thread(target=receive_message)
    thread.start()

    client = connect_to_server(socket_path)
    client.sendall(b"Hello")
    client.close()

    thread.join()
    server.close()