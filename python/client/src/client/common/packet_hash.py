from hashlib import sha256

from client.transfer_pb2 import FilePacket


def calculate_packet_hash(packet: FilePacket) -> str:
    packet_copy = FilePacket()
    packet_copy.CopyFrom(packet)

    packet_copy.packet_hash = ""

    packet_bytes = packet_copy.SerializeToString(
        deterministic=True,
    )

    return sha256(packet_bytes).hexdigest()