import socket
import time
from pathlib import Path
from uuid import uuid4

from client.common.ipc import send_message
from client.common.packet_hash import (
    calculate_packet_hash,
)
from client.common.paths import (
    relative_path_from_root,
)
from client.file_monitor.packet_router import (
    route_packets,
)
from client.file_monitor.raptorq_encoder import (
    encode_file,
)
from client.transfer_pb2 import (
    DELETE,
    FilePacket,
)


def _file_signature(
    file: Path,
) -> tuple[int, int]:
    stat = file.stat()

    return (
        stat.st_size,
        stat.st_mtime_ns,
    )


def transfer_file(
    file: Path,
    connections: list[socket.socket],
    small_file_sender: int,
    watch_root: Path,
) -> int:
    if not connections:
        raise ValueError(
            "at least one Sender connection "
            "is required"
        )

    # Remember exactly which version of the
    # file we are about to send.
    start_signature = _file_signature(
        file
    )

    relative_path = (
        relative_path_from_root(
            file,
            watch_root,
        )
    )

    packets = encode_file(
        file,
        relative_path=relative_path,
    )

    routed_packets = route_packets(
        packets,
        start_signature[0],
        small_file_sender,
        len(connections),
    )

    sent = 0

    for sender, packet in routed_packets:
        packet.target_receiver = sender

        packet.packet_hash = (
            calculate_packet_hash(
                packet
            )
        )

        send_message(
            connections[sender],
            packet.SerializeToString(
                deterministic=True
            ),
        )

        sent += 1

    # This is particularly important for
    # large files because they take much
    # longer to hash/read/transmit.
    try:
        end_signature = _file_signature(
            file
        )

    except FileNotFoundError as error:
        raise RuntimeError(
            f"file disappeared during transfer: "
            f"{file}"
        ) from error

    if (
        start_signature
        != end_signature
    ):
        raise RuntimeError(
            "file changed while it was being "
            f"transferred: {file}"
        )

    return sent


def transfer_delete(
    file: Path,
    connections: list[socket.socket],
    watch_root: Path,
) -> int:
    if not connections:
        raise ValueError(
            "at least one Sender connection "
            "is required"
        )

    relative_path = (
        relative_path_from_root(
            file,
            watch_root,
        )
    )

    file_id = (
        f"{time.time_ns()}:"
        f"{uuid4()}"
    )

    for (
        sender,
        connection,
    ) in enumerate(connections):
        packet = FilePacket()

        packet.file_id = file_id
        packet.file_name = relative_path
        packet.operation = DELETE
        packet.packet_index = 0
        packet.total_packets = 1
        packet.target_receiver = sender

        packet.packet_hash = (
            calculate_packet_hash(
                packet
            )
        )

        send_message(
            connection,
            packet.SerializeToString(
                deterministic=True
            ),
        )

    return len(
        connections
    )