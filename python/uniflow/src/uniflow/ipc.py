import logging
import socket

from uniflow.framing import read_proto, write_proto
from uniflow.pb import message_pb2
from uniflow.utils import load_dot_env, socket_path

logger = logging.getLogger(__name__)

load_dot_env()


class Ipc:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or socket_path()

    def send(
        self,
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> message_pb2.IPCResponse:
        request = message_pb2.IPCRequest(
            command=command,
            data=data,
            target_ip=target_ip,
            object_id=object_id,
            coordinated=coordinated,
            relative_path=relative_path,
            dest_relative_path=dest_relative_path,
            is_directory=is_directory,
        )
        logger.info("connecting to %s", self.path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.path)
            logger.info("sending command %s", command)
            write_proto(sock, request)
            response = read_proto(sock, message_pb2.IPCResponse)
            logger.info(
                "received response success=%s message=%s",
                response.success,
                response.message,
            )
            return response


def default_ipc() -> Ipc:
    return Ipc()
