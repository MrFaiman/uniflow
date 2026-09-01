from client.transfer_pb2 import FilePacket


def test_file_packet():
    packet = FilePacket(
        file_id="123",
        file_name="hello.txt",
        file_size=100,
        file_hash="abc123",
        packet_index=0,
        total_packets=1,
        target_receiver=1,
        data=b"Hello World",
    )

    serialized_packet = packet.SerializeToString()

    received_packet = FilePacket()
    received_packet.ParseFromString(serialized_packet)

    assert received_packet.file_id == "123"
    assert received_packet.file_name == "hello.txt"
    assert received_packet.file_size == 100
    assert received_packet.file_hash == "abc123"
    assert received_packet.packet_index == 0
    assert received_packet.total_packets == 1
    assert received_packet.target_receiver == 1
    assert received_packet.data == b"Hello World"