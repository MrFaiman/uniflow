from hashlib import sha256

import pytest

from client.common.packet_hash import calculate_packet_hash
from client.file_monitor.monitor import FileMonitor
from client.session_manager.manager import SessionManager
from client.transfer_pb2 import DELETE, WRITE, FilePacket


def empty_packet(version, name="file.txt", operation=WRITE):
    packet = FilePacket(
        file_id=f"{version}:test",
        file_name=name,
        operation=operation,
        file_hash=sha256(b"").hexdigest() if operation == WRITE else "",
        total_packets=1,
    )
    packet.packet_hash = calculate_packet_hash(packet)
    return packet


def test_delete_blocks_delayed_write_and_old_delete_cannot_erase_recreation(tmp_path):
    manager = SessionManager(tmp_path)
    manager.handle_packet(empty_packet(100))
    manager.handle_packet(empty_packet(200, operation=DELETE))
    manager.handle_packet(empty_packet(150))
    assert not (tmp_path / "file.txt").exists()
    manager.handle_packet(empty_packet(300))
    manager.handle_packet(empty_packet(250, operation=DELETE))
    assert (tmp_path / "file.txt").is_file()


def test_finished_cache_eviction_does_not_replay_completed_write(tmp_path):
    manager = SessionManager(tmp_path)
    packet = empty_packet(100)
    manager.handle_packet(packet)
    manager.finished_sessions.clear()
    (tmp_path / "file.txt").write_bytes(b"local sentinel")
    manager.handle_packet(packet)
    assert (tmp_path / "file.txt").read_bytes() == b"local sentinel"


@pytest.mark.parametrize(
    "name", ["./file.txt", "a/../file.txt", ".uniflow/parts/x.part", "a\\b.txt"]
)
def test_noncanonical_and_reserved_packet_paths_are_rejected(tmp_path, name):
    manager = SessionManager(tmp_path)
    manager.handle_packet(empty_packet(100, name))
    assert manager.rejected_packets == 1
    assert manager.sessions == {}


def test_delete_through_external_symlink_is_rejected_without_crashing(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    (output / "link").symlink_to(outside, target_is_directory=True)
    manager = SessionManager(output)
    manager.handle_packet(empty_packet(100, "link/keep.txt", DELETE))
    assert sentinel.read_text() == "keep"


def test_oversized_version_is_rejected_without_crashing(tmp_path):
    packet = empty_packet("1" * 5000)
    manager = SessionManager(tmp_path)
    manager.handle_packet(packet)
    assert manager.rejected_packets == 1


def test_non_ascii_version_is_rejected_without_crashing(tmp_path):
    manager = SessionManager(tmp_path)
    manager.handle_packet(empty_packet("\u00b2"))
    assert manager.rejected_packets == 1


def test_truncated_fec_symbol_is_rejected_before_native_decoder(tmp_path):
    from client.file_monitor.raptorq_encoder import encode_file
    from client.session_manager.packet_validator import packet_is_valid

    source = tmp_path / "source.bin"
    source.write_bytes(b"some data")
    packet = next(encode_file(source))
    packet.data = packet.data[:1]
    packet.packet_hash = calculate_packet_hash(packet)
    assert not packet_is_valid(packet)


def test_wrong_file_hash_preserves_destination_and_removes_partial_file(tmp_path):
    from client.file_monitor.raptorq_encoder import encode_file

    source = tmp_path / "source.bin"
    source.write_bytes(b"replacement" * 100)
    output = tmp_path / "received"
    output.mkdir()
    (output / "source.bin").write_bytes(b"original")
    manager = SessionManager(output)
    for packet in encode_file(source):
        packet.file_hash = "0" * 64
        packet.packet_hash = calculate_packet_hash(packet)
        manager.handle_packet(packet)
    assert (output / "source.bin").read_bytes() == b"original"
    assert not list((output / ".uniflow" / "parts").glob("*.part"))


def test_watchdog_reconciles_missed_directory_move_events(tmp_path):
    monitor = FileMonitor(tmp_path, use_watchdog=True)
    monitor.stop()  # Simulate missing host/bind-mount notifications.
    old = tmp_path / "old"
    old.mkdir()
    source = old / "file.txt"
    source.write_text("payload")
    monitor.note_changed(source)
    monitor.get_changed_files()
    assert monitor.get_changed_files() == [source]
    old.rename(tmp_path / "new")
    monitor.get_changed_files()
    assert monitor.get_changed_files() == [tmp_path / "new" / "file.txt"]
    assert monitor.get_deleted_files() == [source]


def test_failed_modification_followed_by_delete_still_sends_tombstone(tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("payload")
    monitor = FileMonitor(tmp_path)
    monitor.get_changed_files()
    monitor.get_changed_files()
    monitor.mark_failed(source)
    source.unlink()
    monitor.get_changed_files()
    assert monitor.get_deleted_files() == [source]
