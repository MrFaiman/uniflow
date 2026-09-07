from __future__ import annotations

import argparse
import logging
import os
import random
import select
import signal
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    from config import RouterConfig
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import RouterConfig

logger = logging.getLogger("router")


class _LevelFormatter(logging.Formatter):
    _NAMES = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARN",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "ERROR",
    }

    def format(self, record: logging.LogRecord) -> str:
        record.levelname = self._NAMES.get(record.levelno, record.levelname)
        return super().format(record)


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
        return self.by_port.setdefault(port, PortStats())


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def _probability(value: str) -> float:
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def configure_logging(*, verbose: bool, log_file: str | None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = _LevelFormatter("[%(levelname)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(formatter)
    root.addHandler(stderr)

    if log_file:
        path = Path(log_file)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        logger.info("logging to file %s", path)


def create_parser() -> argparse.ArgumentParser:
    defaults = RouterConfig.from_env()
    parser = argparse.ArgumentParser(
        prog="router",
        description=(
            "UniFlow UDP fault-injection router. "
            "CLI flags override matching environment variables."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )
    parser.add_argument(
        "--log-file",
        help="also write logs to this file (overrides UNIFLOW_LOG_FILE)",
    )
    parser.add_argument(
        "--bind",
        default=defaults.bind,
        help="local address to listen on (default: %(default)s)",
    )
    parser.add_argument(
        "--rx-host",
        default=defaults.rx_host,
        help="RX hostname or IP to forward packets to (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=defaults.start_port,
        help="base UDP port; workers use PORT, PORT+1, PORT+2 (default: %(default)s)",
    )
    parser.add_argument(
        "--packet-loss",
        type=_probability,
        default=defaults.packet_loss,
        help="drop probability in [0, 1] (default: %(default)s)",
    )
    parser.add_argument(
        "--bit-flip",
        type=_probability,
        default=defaults.bit_flip,
        help="bit-corruption probability in [0, 1] (default: %(default)s)",
    )
    parser.add_argument(
        "--misrouting",
        type=_probability,
        default=defaults.misrouting,
        help="wrong-port probability in [0, 1] (default: %(default)s)",
    )
    parser.add_argument(
        "--stats-interval",
        type=int,
        default=defaults.stats_interval_sec,
        metavar="SEC",
        help="seconds between stats logs; 0 disables periodic stats (default: %(default)s)",
    )
    parser.add_argument(
        "--log-packets",
        action=argparse.BooleanOptionalAction,
        default=defaults.log_packets,
        help="log every dropped, flipped, or misrouted packet",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=defaults.random_seed,
        help="deterministic RNG seed (default: %(default)s)",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> RouterConfig:
    config = RouterConfig(
        bind=args.bind,
        rx_host=args.rx_host,
        start_port=args.port,
        packet_loss=args.packet_loss,
        bit_flip=args.bit_flip,
        misrouting=args.misrouting,
        stats_interval_sec=args.stats_interval,
        log_packets=args.log_packets,
        random_seed=args.seed,
    )
    config.validate()
    return config


def resolve_log_file(args: argparse.Namespace) -> str | None:
    if args.log_file:
        return args.log_file
    return os.environ.get("UNIFLOW_LOG_FILE") or None


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
            "[stats] port=%d recv=%d drop=%d fwd=%d misroute_in=%d misroute_out=%d",
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

    changed = bytearray(data)
    byte_index = random.randrange(len(changed))
    bit_index = random.randrange(8)
    changed[byte_index] ^= 1 << bit_index
    return bytes(changed), byte_index, bit_index


def resolve_rx_host(host: str) -> str:
    while True:
        try:
            address = socket.gethostbyname(host)
            logger.info("Forwarding packets to RX host %s (%s)", host, address)
            return address
        except socket.gaierror:
            logger.info("Waiting for RX host %s to become resolvable...", host)
            time.sleep(0.5)


def start_router(config: RouterConfig) -> None:
    random.seed(config.random_seed)
    packet_log = logger.info if config.log_packets else logger.debug

    listening_sockets: dict[socket.socket, int] = {}

    # One UDP socket for every Sender/Receiver pair.
    for port in config.ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 * 1024 * 1024)
        sock.bind((config.bind, port))
        listening_sockets[sock] = port
        logger.info(
            "Listening for TX on %s:%d (loss=%.1f%% flip=%.1f%% misroute=%.1f%%)",
            config.bind,
            port,
            config.packet_loss * 100,
            config.bit_flip * 100,
            config.misrouting * 100,
        )

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16 * 1024 * 1024)

    # In one-PC mode: RX_HOST = rx_machine
    # In two-PC mode: RX_HOST = physical PC B IP
    rx_addr = resolve_rx_host(config.rx_host)

    stats = RouterStats()
    last_stats = time.monotonic()
    shutdown = False

    def handle_shutdown(signum: int, _frame: object) -> None:
        nonlocal shutdown
        logger.info("Received signal %d, shutting down", signum)
        shutdown = True

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    while not shutdown:
        readable, _, _ = select.select(list(listening_sockets), [], [], 0.5)

        for sock in readable:
            data, addr = sock.recvfrom(65535)
            intended_port = listening_sockets[sock]
            packet_size = len(data)

            stats.received += 1
            stats.bytes_in += packet_size
            stats.port_stats(intended_port).received += 1

            if random.random() < config.packet_loss:
                stats.dropped += 1
                stats.port_stats(intended_port).dropped += 1
                packet_log("Dropped src=%s intended_port=%d", addr, intended_port)
                continue

            if random.random() < config.bit_flip:
                data, byte_index, bit_index = apply_bit_flip(data)
                stats.bit_flipped += 1
                packet_log(
                    "Bit flip intended_port=%d byte=%d bit=%d",
                    intended_port,
                    byte_index,
                    bit_index,
                )

            target_port = intended_port
            if random.random() < config.misrouting:
                wrong_ports = [
                    port for port in config.ports if port != intended_port
                ]
                target_port = random.choice(wrong_ports)
                stats.misrouted += 1
                stats.port_stats(intended_port).misroute_out += 1
                stats.port_stats(target_port).misroute_in += 1
                packet_log(
                    "Misrouted intended_port=%d target_port=%d",
                    intended_port,
                    target_port,
                )

            send_sock.sendto(data, (rx_addr, target_port))
            stats.forwarded += 1
            stats.bytes_out += len(data)
            stats.port_stats(target_port).forwarded += 1

        now = time.monotonic()
        if (
            config.stats_interval_sec > 0
            and now - last_stats >= config.stats_interval_sec
        ):
            log_stats(stats)
            last_stats = now

    log_stats(stats)

    for sock in listening_sockets:
        sock.close()
    send_sock.close()


def main() -> int:
    args = create_parser().parse_args()
    configure_logging(verbose=args.verbose, log_file=resolve_log_file(args))
    try:
        start_router(config_from_args(args))
    except Exception as error:
        logger.error("fatal: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
