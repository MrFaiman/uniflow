import logging
import os
import random
import select
import signal
import socket
import sys
import time
from dataclasses import dataclass, field

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (  # noqa: E402
    FORWARD_PORT_BY_LISTEN_PORT,
    LISTEN_PORT_LIST,
    ROUTER_IP,
    RX_HOST,
    RX_PORT_LIST,
    STATS_INTERVAL_SEC,
    DisruptionProbabilities,
)

logger = logging.getLogger(__name__)

# Logging one line per packet dominates the router's per-packet cost and makes
# it, not the network, the bottleneck for large transfers. Keep it opt-in and
# rely on the periodic aggregate stats instead.
TRACE_PACKETS = os.environ.get("ROUTER_TRACE_PACKETS") == "1"
RECV_BUFFER_BYTES = int(os.environ.get("ROUTER_RECV_BUFFER", 8 << 20))


@dataclass
class PortStats:
    received: int = 0
    dropped: int = 0
    forwarded: int = 0
    misroute_in: int = 0
    misroute_out: int = 0


@dataclass
class RouterStats:
    received: int = 0
    dropped: int = 0
    bit_flipped: int = 0
    misrouted: int = 0
    forwarded: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    by_port: dict[int, PortStats] = field(default_factory=dict)

    def port_stats(self, port: int) -> PortStats:
        if port not in self.by_port:
            self.by_port[port] = PortStats()
        return self.by_port[port]


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def log_stats(stats: RouterStats) -> None:
    logger.info(
        "[stats] received=%d dropped=%d (%s) bit_flipped=%d (%s) "
        "misrouted=%d (%s) forwarded=%d bytes_in=%d bytes_out=%d",
        stats.received,
        stats.dropped,
        _pct(stats.dropped, stats.received),
        stats.bit_flipped,
        _pct(stats.bit_flipped, stats.received),
        stats.misrouted,
        _pct(stats.misrouted, stats.received),
        stats.forwarded,
        stats.bytes_in,
        stats.bytes_out,
    )
    for port in sorted(stats.by_port):
        port_stats = stats.by_port[port]
        logger.info(
            "[stats] port=%d recv=%d drop=%d fwd=%d "
            "misroute_in=%d misroute_out=%d",
            port,
            port_stats.received,
            port_stats.dropped,
            port_stats.forwarded,
            port_stats.misroute_in,
            port_stats.misroute_out,
        )


def apply_bit_flip(data: bytes) -> tuple[bytes, int, int]:
    if not data:
        return data, 0, 0
    data_bytearray = bytearray(data)
    byte_index = random.randint(0, len(data_bytearray) - 1)
    bit_index = random.randint(0, 7)
    data_bytearray[byte_index] ^= 1 << bit_index
    return bytes(data_bytearray), byte_index, bit_index


def start_router() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    listening_sockets: dict[socket.socket, int] = {}
    for port in LISTEN_PORT_LIST:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # The router is a single-threaded hop carrying every packet of a
        # coordinated transfer. Without a large receive buffer the kernel
        # discards the burst before this loop can drain it, which shows up
        # as loss the fault-injection settings never asked for.
        try:
            recv_sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_RCVBUF,
                RECV_BUFFER_BYTES,
            )
        except OSError as err:
            logger.warning("could not raise receive buffer: %s", err)
        recv_sock.bind((ROUTER_IP, port))
        listening_sockets[recv_sock] = port
        logger.info(
            "listening for TX on %s:%d -> %s:%d "
            "(loss=%.0f%% flip=%.0f%% misroute=%.0f%%)",
            ROUTER_IP,
            port,
            RX_HOST,
            FORWARD_PORT_BY_LISTEN_PORT[port],
            DisruptionProbabilities.PACKET_LOSS * 100,
            DisruptionProbabilities.BIT_FLIP * 100,
            DisruptionProbabilities.MISROUTING * 100,
        )

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_addr = socket.gethostbyname(RX_HOST)
    stats = RouterStats()
    last_stats = time.monotonic()
    shutdown = False

    def handle_shutdown(signum: int, _frame: object) -> None:
        nonlocal shutdown
        logger.info("received signal %d, shutting down", signum)
        shutdown = True

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    while not shutdown:
        timeout = 1.0
        if STATS_INTERVAL_SEC > 0:
            elapsed = time.monotonic() - last_stats
            timeout = max(0.1, STATS_INTERVAL_SEC - elapsed)

        readable, _, _ = select.select(
            list(listening_sockets.keys()),
            [],
            [],
            timeout,
        )

        if not readable and STATS_INTERVAL_SEC > 0:
            now = time.monotonic()
            if now - last_stats >= STATS_INTERVAL_SEC:
                log_stats(stats)
                last_stats = now
            continue

        for sock in readable:
            data, addr = sock.recvfrom(65535)
            listen_port = listening_sockets[sock]
            intended_port = FORWARD_PORT_BY_LISTEN_PORT[listen_port]
            packet_size = len(data)

            stats.received += 1
            stats.bytes_in += packet_size
            port_stats = stats.port_stats(intended_port)
            port_stats.received += 1

            if TRACE_PACKETS:
                logger.info(
                    "received size=%d src=%s intended_port=%d",
                    packet_size,
                    addr,
                    intended_port,
                )

            if random.random() < DisruptionProbabilities.PACKET_LOSS:
                stats.dropped += 1
                port_stats.dropped += 1
                if TRACE_PACKETS:
                    logger.info(
                        "dropped size=%d src=%s intended_port=%d",
                        packet_size,
                        addr,
                        intended_port,
                    )
                continue

            flipped = False
            if random.random() < DisruptionProbabilities.BIT_FLIP:
                data, byte_index, bit_index = apply_bit_flip(data)
                flipped = True
                stats.bit_flipped += 1
                if TRACE_PACKETS:
                    logger.info(
                        "bit_flip size=%d src=%s intended_port=%d "
                        "byte=%d bit=%d",
                        packet_size,
                        addr,
                        intended_port,
                        byte_index,
                        bit_index,
                    )

            target_port = intended_port
            misrouted = False
            if random.random() < DisruptionProbabilities.MISROUTING:
                wrong_ports = [p for p in RX_PORT_LIST if p != intended_port]
                target_port = random.choice(wrong_ports)
                misrouted = True
                stats.misrouted += 1
                stats.port_stats(intended_port).misroute_out += 1
                stats.port_stats(target_port).misroute_in += 1
                if TRACE_PACKETS:
                    logger.info(
                        "misrouted size=%d src=%s intended_port=%d "
                        "target_port=%d",
                        packet_size,
                        addr,
                        intended_port,
                        target_port,
                    )

            send_sock.sendto(data, (rx_addr, target_port))
            stats.forwarded += 1
            stats.bytes_out += len(data)
            stats.port_stats(target_port).forwarded += 1
            if TRACE_PACKETS:
                logger.info(
                    "forwarded size=%d src=%s intended_port=%d "
                    "target_port=%d bit_flipped=%s misrouted=%s",
                    len(data),
                    addr,
                    intended_port,
                    target_port,
                    flipped,
                    misrouted,
                )

    log_stats(stats)


if __name__ == "__main__":
    start_router()