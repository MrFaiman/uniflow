from hashlib import sha256

from client.file_monitor.packet_builder import build_file_packet


def test_build_file_packet(tmp_path):
    file = tmp_path / "hello.txt"
    data = b"Hello World"
    file.write_bytes(data)

    packet = build_file_packet(file, 1)

    assert packet.file_name == "hello.txt"
    assert packet.file_size == len(data)
    assert packet.file_hash == sha256(data).hexdigest()
    assert packet.packet_index == 0
    assert packet.total_packets == 1
    assert packet.target_receiver == 1
    assert packet.data == data
    assert packet.file_id != ""