from itertools import zip_longest

from client.common.packet_hash import calculate_packet_hash
from client.file_monitor.raptorq_encoder import BLOCK_SIZE, encode_file
from client.session_manager.manager import SessionManager


def prepare_packet(packet, target_receiver: int) -> None:
    packet.target_receiver = target_receiver
    packet.packet_hash = calculate_packet_hash(packet)


def test_corrupted_packet_is_rejected(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"Hello World " * 1000)

    packet = next(encode_file(source))
    prepare_packet(packet, 0)
    packet.data = bytes([packet.data[0] ^ 1]) + packet.data[1:]

    manager = SessionManager(tmp_path / "received")
    manager.handle_packet(packet)
    assert manager.sessions == {}


def test_loss_out_of_order_and_nested_path(tmp_path):
    source = tmp_path / "source.bin"
    original_data = b"A" * BLOCK_SIZE + b"B" * 5000
    source.write_bytes(original_data)

    packets = list(encode_file(source, relative_path="nested/large.bin"))
    blocks = {}
    for packet in packets:
        blocks.setdefault(packet.block_index, []).append(packet)

    output_folder = tmp_path / "received"
    manager = SessionManager(output_folder)
    file_id = packets[0].file_id

    for block_index in [1, 0]:
        # Drop the first two encoded packets from each block.
        for packet in blocks[block_index][2:]:
            prepare_packet(packet, packet.packet_index % 3)
            manager.handle_serialized_packet(packet.SerializeToString())

            if file_id in manager.finished_sessions:
                break
            session = manager.sessions.get(file_id)
            if session is not None and block_index in session.completed_blocks:
                break

    received_file = output_folder / "nested" / "large.bin"
    assert received_file.read_bytes() == original_data
    assert file_id in manager.finished_sessions


def test_two_files_at_same_time(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first_data = b"First file " * 1000
    second_data = b"Second file " * 1000
    first.write_bytes(first_data)
    second.write_bytes(second_data)

    first_packets = list(encode_file(first))
    second_packets = list(encode_file(second))
    output_folder = tmp_path / "received"
    manager = SessionManager(output_folder)

    for first_packet, second_packet in zip_longest(first_packets, second_packets):
        if first_packet is not None:
            prepare_packet(first_packet, 0)
            manager.handle_packet(first_packet)
        if second_packet is not None:
            prepare_packet(second_packet, 1)
            manager.handle_packet(second_packet)

    assert (output_folder / "first.txt").read_bytes() == first_data
    assert (output_folder / "second.txt").read_bytes() == second_data


def test_empty_file(tmp_path):
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")

    packet = next(encode_file(source))
    prepare_packet(packet, 2)

    output_folder = tmp_path / "received"
    manager = SessionManager(output_folder)
    manager.handle_packet(packet)

    assert (output_folder / "empty.bin").read_bytes() == b""


def test_newer_modification_wins_over_older_transfer(tmp_path):
    older = tmp_path / "older.bin"
    newer = tmp_path / "newer.bin"
    older_data = b"OLD" * 50000
    newer_data = b"NEW" * 50000
    older.write_bytes(older_data)
    newer.write_bytes(newer_data)

    older_packets = list(encode_file(older, relative_path="same/file.bin"))
    newer_packets = list(encode_file(newer, relative_path="same/file.bin"))

    for packet in older_packets:
        prepare_packet(packet, packet.packet_index % 3)
    for packet in newer_packets:
        prepare_packet(packet, packet.packet_index % 3)

    output_folder = tmp_path / "received"
    manager = SessionManager(output_folder)

    manager.handle_packet(older_packets[0])
    for packet in newer_packets:
        manager.handle_packet(packet)
    for packet in older_packets[1:]:
        manager.handle_packet(packet)

    assert (output_folder / "same" / "file.bin").read_bytes() == newer_data
