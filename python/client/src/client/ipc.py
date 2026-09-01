import logging
import socket

from client.framing import read_proto, write_proto
from client.pb import message_pb2
from client.utils import load_dot_env, socket_path

logger = logging.getLogger(__name__)

load_dot_env()


class Ipc:
    path = socket_path()

    @classmethod
    def send(cls, command: str, data: bytes = b"") -> message_pb2.IPCResponse:
        request = message_pb2.IPCRequest(command=command, data=data)
        logger.info("connecting to %s", cls.path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(cls.path)
            logger.info("sending command %s", command)
            write_proto(sock, request)
            response = read_proto(sock, message_pb2.IPCResponse)
            logger.info(
                "received response success=%s message=%s",
                response.success,
                response.message,
            )
            return response
