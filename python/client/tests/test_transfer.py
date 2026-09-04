import struct

from client.file_monitor.transfer import transfer_file
from client.transfer_pb2 import FilePacket


class CaptureConnection:
    def __init__(self):
        self.data = bytearray()

    def sendall(self, data: bytes) -> None:
        self.data.extend(data)


def decode_messages(connection: CaptureConnection) -> list[FilePacket]:
    data = bytes(connection.data)
    packets = []
    offset = 0

    while offset < len(data):
        size = struct.unpack("!I", data[offset : offset + 4])[0]
        offset += 4
        payload = data[offset : offset + size]
        offset += size
        packet = FilePacket()
        packet.ParseFromString(payload)
        packets.append(packet)

    return packets


def test_small_file_uses_one_sender_and_preserves_nested_path(tmp_path):
    root = tmp_path / "out"
    file = root / "nested" / "hello.txt"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"Hello World")

    connections = [CaptureConnection(), CaptureConnection(), CaptureConnection()]
    transfer_file(file, connections, small_file_sender=1, watch_root=root)

    assert decode_messages(connections[0]) == []
    assert decode_messages(connections[2]) == []

    packets = decode_messages(connections[1])
    assert packets
    assert all(packet.target_receiver == 1 for packet in packets)
    assert all(packet.file_name == "nested/hello.txt" for packet in packets)
    assert all(len(packet.packet_hash) == 64 for packet in packets)


def test_empty_file_produces_one_metadata_packet(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    file = root / "empty.bin"
    file.write_bytes(b"")

    connections = [CaptureConnection(), CaptureConnection(), CaptureConnection()]
    transfer_file(file, connections, small_file_sender=2, watch_root=root)

    packets = decode_messages(connections[2])
    assert len(packets) == 1
    assert packets[0].file_size == 0
    assert packets[0].total_blocks == 0
    assert packets[0].data == b""
