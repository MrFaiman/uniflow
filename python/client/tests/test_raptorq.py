from raptorq import Decoder

from client.file_monitor.raptorq_encoder import SYMBOL_SIZE, encode_file


def test_raptorq_with_packet_loss(tmp_path):
    file = tmp_path / "test.txt"
    original_data = b"Hello World " * 1000
    file.write_bytes(original_data)

    packets = list(encode_file(file))

    # Simulate losing two packets
    packets = packets[2:]

    decoder = Decoder.with_defaults(
        packets[0].block_size,
        SYMBOL_SIZE,
    )

    decoded_data = None

    for packet in packets:
        decoded_data = decoder.decode(packet.data)

        if decoded_data is not None:
            break

    assert decoded_data == original_data