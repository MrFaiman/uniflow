from raptorq import Decoder

from client.session_manager.file_session import FileSession
from client.transfer_pb2 import FilePacket


def decode_packet(session: FileSession, packet: FilePacket) -> bytes | None:
    block = packet.block_index

    if block not in session.decoders:
        session.decoders[block] = Decoder.with_defaults(
            packet.block_size,
            packet.symbol_size,
        )

    try:
        decoded = session.decoders[block].decode(packet.data)
    except Exception:
        print("Invalid RaptorQ packet", flush=True)
        return None

    if decoded is None:
        return None

    if len(decoded) != packet.block_size:
        print("Invalid decoded block", flush=True)
        return None

    return decoded
