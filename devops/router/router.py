import logging
import random
import select
import signal
import socket
import sys
import time
from dataclasses import dataclass, field

from config import (
    LOG_PACKETS,
    RANDOM_SEED,
    ROUTER_IP,
    RX_HOST,
    RX_PORT_LIST,
    STATS_INTERVAL_SEC,
    DisruptionProbabilities,
)


logger = logging.getLogger(__name__)


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

    by_port: dict[int, PortStats] = field(
        default_factory=dict
    )

    def port_stats(
        self,
        port: int,
    ) -> PortStats:
        return self.by_port.setdefault(
            port,
            PortStats(),
        )


def _pct(
    count: int,
    total: int,
) -> str:
    if total == 0:
        return "0.0%"

    return f"{(count / total) * 100:.1f}%"


def log_stats(
    stats: RouterStats,
) -> None:
    logger.info(
        "[stats] received=%d "
        "dropped=%d (%s) "
        "bit_flipped=%d (%s) "
        "misrouted=%d (%s) "
        "forwarded=%d "
        "bytes_in=%d "
        "bytes_out=%d",
        stats.received,
        stats.dropped,
        _pct(
            stats.dropped,
            stats.received,
        ),
        stats.bit_flipped,
        _pct(
            stats.bit_flipped,
            stats.received,
        ),
        stats.misrouted,
        _pct(
            stats.misrouted,
            stats.received,
        ),
        stats.forwarded,
        stats.bytes_in,
        stats.bytes_out,
    )

    for port in sorted(
        stats.by_port
    ):
        port_stats = (
            stats.by_port[port]
        )

        logger.info(
            "[stats] port=%d "
            "recv=%d "
            "drop=%d "
            "fwd=%d "
            "misroute_in=%d "
            "misroute_out=%d",
            port,
            port_stats.received,
            port_stats.dropped,
            port_stats.forwarded,
            port_stats.misroute_in,
            port_stats.misroute_out,
        )


def apply_bit_flip(
    data: bytes,
) -> tuple[bytes, int, int]:

    if not data:
        return data, 0, 0

    changed = bytearray(data)

    byte_index = random.randrange(
        len(changed)
    )

    bit_index = random.randrange(8)

    changed[byte_index] ^= (
        1 << bit_index
    )

    return (
        bytes(changed),
        byte_index,
        bit_index,
    )


def resolve_rx_host(
    host: str,
) -> str:
    while True:
        try:
            address = socket.gethostbyname(
                host
            )

            logger.info(
                "Forwarding packets to "
                "RX host %s (%s)",
                host,
                address,
            )

            return address

        except socket.gaierror:
            logger.info(
                "Waiting for RX host %s "
                "to become resolvable...",
                host,
            )

            time.sleep(0.5)


def start_router() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    random.seed(
        RANDOM_SEED
    )

    listening_sockets: dict[
        socket.socket,
        int,
    ] = {}

    # One UDP socket for every
    # Sender/Receiver pair.
    for port in RX_PORT_LIST:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_RCVBUF,
            16 * 1024 * 1024,
        )

        sock.bind(
            (
                ROUTER_IP,
                port,
            )
        )

        listening_sockets[
            sock
        ] = port

        logger.info(
            "Listening for TX on "
            "%s:%d "
            "(loss=%.1f%% "
            "flip=%.1f%% "
            "misroute=%.1f%%)",
            ROUTER_IP,
            port,
            (
                DisruptionProbabilities
                .PACKET_LOSS
                * 100
            ),
            (
                DisruptionProbabilities
                .BIT_FLIP
                * 100
            ),
            (
                DisruptionProbabilities
                .MISROUTING
                * 100
            ),
        )

    send_sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    send_sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_SNDBUF,
        16 * 1024 * 1024,
    )

    # In one-PC mode:
    #     RX_HOST = rx_machine
    #
    # In two-PC mode:
    #     RX_HOST = physical PC B IP
    rx_addr = resolve_rx_host(
        RX_HOST
    )

    stats = RouterStats()

    last_stats = time.monotonic()

    shutdown = False

    def handle_shutdown(
        signum: int,
        _frame: object,
    ) -> None:
        nonlocal shutdown

        logger.info(
            "Received signal %d, "
            "shutting down",
            signum,
        )

        shutdown = True

    signal.signal(
        signal.SIGINT,
        handle_shutdown,
    )

    signal.signal(
        signal.SIGTERM,
        handle_shutdown,
    )

    while not shutdown:
        readable, _, _ = select.select(
            list(listening_sockets),
            [],
            [],
            0.5,
        )

        for sock in readable:
            data, addr = sock.recvfrom(
                65535
            )

            intended_port = (
                listening_sockets[sock]
            )

            packet_size = len(data)

            stats.received += 1
            stats.bytes_in += packet_size

            stats.port_stats(
                intended_port
            ).received += 1

            # -------------------------
            # Packet loss
            # -------------------------

            if (
                random.random()
                < DisruptionProbabilities
                .PACKET_LOSS
            ):
                stats.dropped += 1

                stats.port_stats(
                    intended_port
                ).dropped += 1

                if LOG_PACKETS:
                    logger.info(
                        "Dropped "
                        "src=%s "
                        "intended_port=%d",
                        addr,
                        intended_port,
                    )

                continue

            # -------------------------
            # Bit corruption
            # -------------------------

            if (
                random.random()
                < DisruptionProbabilities
                .BIT_FLIP
            ):
                (
                    data,
                    byte_index,
                    bit_index,
                ) = apply_bit_flip(
                    data
                )

                stats.bit_flipped += 1

                if LOG_PACKETS:
                    logger.info(
                        "Bit flip "
                        "intended_port=%d "
                        "byte=%d "
                        "bit=%d",
                        intended_port,
                        byte_index,
                        bit_index,
                    )

            # -------------------------
            # Misrouting
            # -------------------------

            target_port = (
                intended_port
            )

            if (
                random.random()
                < DisruptionProbabilities
                .MISROUTING
            ):
                wrong_ports = [
                    port
                    for port
                    in RX_PORT_LIST
                    if port
                    != intended_port
                ]

                target_port = (
                    random.choice(
                        wrong_ports
                    )
                )

                stats.misrouted += 1

                stats.port_stats(
                    intended_port
                ).misroute_out += 1

                stats.port_stats(
                    target_port
                ).misroute_in += 1

                if LOG_PACKETS:
                    logger.info(
                        "Misrouted "
                        "intended_port=%d "
                        "target_port=%d",
                        intended_port,
                        target_port,
                    )

            # -------------------------
            # Forward to RX
            # -------------------------

            send_sock.sendto(
                data,
                (
                    rx_addr,
                    target_port,
                ),
            )

            stats.forwarded += 1
            stats.bytes_out += len(data)

            stats.port_stats(
                target_port
            ).forwarded += 1

        now = time.monotonic()

        if (
            STATS_INTERVAL_SEC > 0
            and now - last_stats
            >= STATS_INTERVAL_SEC
        ):
            log_stats(stats)

            last_stats = now

    log_stats(stats)

    for sock in listening_sockets:
        sock.close()

    send_sock.close()


if __name__ == "__main__":
    start_router()