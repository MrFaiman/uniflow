from itertools import zip_longest

from client.common.packet_hash import (
    calculate_packet_hash,
)
from client.file_monitor.raptorq_encoder import (
    BLOCK_SIZE,
    encode_file,
)
from client.session_manager.manager import (
    SessionManager,
)


def prepare_packet(
    packet,
    target_receiver: int,
) -> None:
    packet.target_receiver = target_receiver

    packet.packet_hash = (
        calculate_packet_hash(packet)
    )


def test_corrupted_packet_is_rejected(
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_bytes(
        b"Hello World " * 1000
    )

    packet = next(
        encode_file(source)
    )

    prepare_packet(
        packet,
        0,
    )

    packet.data = (
        bytes(
            [packet.data[0] ^ 1]
        )
        + packet.data[1:]
    )

    output_folder = (
        tmp_path / "received"
    )

    manager = SessionManager(
        output_folder
    )

    manager.handle_packet(
        0,
        packet,
    )

    assert manager.sessions == {}


def test_loss_and_misrouting(
    tmp_path,
):
    source = tmp_path / "large.bin"

    original_data = (
        b"A" * BLOCK_SIZE
        + b"B" * 5000
    )

    source.write_bytes(
        original_data
    )

    packets = list(
        encode_file(source)
    )

    blocks = {}

    for packet in packets:
        blocks.setdefault(
            packet.block_index,
            [],
        ).append(packet)

    output_folder = (
        tmp_path / "received"
    )

    manager = SessionManager(
        output_folder
    )

    file_id = packets[0].file_id

    for block_index in [1, 0]:
        block_packets = (
            blocks[block_index][2:]
        )

        for packet in block_packets:
            prepare_packet(
                packet,
                0,
            )

            manager.handle_serialized_packet(
                2,
                packet.SerializeToString(),
            )

            if (
                file_id
                in manager.finished_sessions
            ):
                break

            session = manager.sessions.get(
                file_id
            )

            if (
                session is not None
                and block_index
                in session.completed_blocks
            ):
                break

    received_file = (
        output_folder / "large.bin"
    )

    assert received_file.exists()

    assert (
        received_file.read_bytes()
        == original_data
    )

    assert (
        file_id
        in manager.finished_sessions
    )


def test_two_files_at_same_time(
    tmp_path,
):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first_data = b"First file " * 1000
    second_data = b"Second file " * 1000

    first.write_bytes(first_data)
    second.write_bytes(second_data)

    first_packets = list(
        encode_file(first)
    )

    second_packets = list(
        encode_file(second)
    )

    output_folder = (
        tmp_path / "received"
    )

    manager = SessionManager(
        output_folder
    )

    for first_packet, second_packet in zip_longest(
        first_packets,
        second_packets,
    ):
        if first_packet is not None:
            prepare_packet(
                first_packet,
                0,
            )

            manager.handle_packet(
                0,
                first_packet,
            )

        if second_packet is not None:
            prepare_packet(
                second_packet,
                1,
            )

            manager.handle_packet(
                1,
                second_packet,
            )

    assert (
        output_folder / "first.txt"
    ).read_bytes() == first_data

    assert (
        output_folder / "second.txt"
    ).read_bytes() == second_data