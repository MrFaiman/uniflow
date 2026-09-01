import logging
import os
import socket
from pathlib import Path

from dotenv import load_dotenv

from client.framing import read_proto, write_proto
from client.pb import message_pb2

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    start = Path(__file__).resolve().parent
    for directory in (start, *start.parents):
        env_file = directory / ".env"
        example = directory / ".env.example"
        if env_file.is_file():
            load_dotenv(env_file)
            return
        if example.is_file():
            load_dotenv(example)
            return


_load_dotenv()

_socket_path = os.environ.get("IPC_SOCKET_PATH")
if not _socket_path:
    raise RuntimeError("IPC_SOCKET_PATH is not set; add it to .env")
SOCKET_PATH = _socket_path


def send(command: str, data: bytes = b"") -> message_pb2.IPCResponse:
    request = message_pb2.IPCRequest(command=command, data=data)
    logger.info("connecting to %s", SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(SOCKET_PATH)
        logger.info("sending command %s", command)
        write_proto(sock, request)
        response = read_proto(sock, message_pb2.IPCResponse)
        logger.info(
            "received response success=%s message=%s",
            response.success,
            response.message,
        )
        return response
