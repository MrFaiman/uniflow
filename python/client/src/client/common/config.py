import math
import os
from pathlib import Path

DEFAULT_SOCKET_PATH = "/tmp/proto_ipc.sock"
DEFAULT_WORKERS = 3
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_PORT = 9000
DEFAULT_MAX_FILE_BYTES = 1024 * 1024 * 1024
DEFAULT_REPAIR_PERCENT = 20
MAX_REPAIR_PERCENT = 500
FEC_SAFETY_FACTOR = 1.15
DEFAULT_NET_BINARY = "/usr/local/bin/uniflow-net"


def get_socket_path() -> Path:
    return Path(os.getenv("IPC_SOCKET_PATH", DEFAULT_SOCKET_PATH))


def get_sender_socket_path(worker_index: int) -> Path:
    return Path(f"{get_socket_path()}.sender.{worker_index}")


def get_worker_count() -> int:
    workers = int(os.getenv("UNIFLOW_WORKERS", str(DEFAULT_WORKERS)))
    if workers != 3:
        raise ValueError("The trio project requires exactly 3 workers")
    return workers


def get_poll_interval() -> float:
    polling = float(os.getenv("UNIFLOW_WATCH_POLLING", str(DEFAULT_POLL_INTERVAL)))
    if polling <= 0:
        raise ValueError("UNIFLOW_WATCH_POLLING must be greater than 0")
    return polling


def get_base_port() -> int:
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    if port < 1 or port > 65533:
        raise ValueError("PORT must leave room for ports PORT, PORT+1 and PORT+2")
    return port


def get_max_file_bytes() -> int:
    value = int(os.getenv("UNIFLOW_MAX_FILE_BYTES", str(DEFAULT_MAX_FILE_BYTES)))
    if value <= 0 or value > DEFAULT_MAX_FILE_BYTES:
        raise ValueError("UNIFLOW_MAX_FILE_BYTES must be between 1 and 1 GiB")
    return value


def _fault_probability(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw in (None, "") else float(raw)

    if value < 0 or value > 1:
        raise ValueError(f"{name} must be between 0 and 1")

    return value


def get_repair_percent() -> int:
    explicit = os.getenv("UNIFLOW_FEC_REPAIR_PERCENT")

    if explicit not in (None, ""):
        value = int(explicit)

        if value < 0 or value > MAX_REPAIR_PERCENT:
            raise ValueError(
                "UNIFLOW_FEC_REPAIR_PERCENT must be between "
                f"0 and {MAX_REPAIR_PERCENT}"
            )

        return value

    # Automatic FEC for the bundled fault-injection router.
    #
    # Misrouting is not treated as packet loss because all three Receivers
    # forward valid packets to the same Session Manager.
    loss = _fault_probability("PACKET_LOSS", 0.03)
    bit_flip = _fault_probability("BIT_FLIP", 0.03)

    # A packet is useful only if it is neither dropped nor corrupted.
    valid_fraction = (1.0 - loss) * (1.0 - bit_flip)

    if valid_fraction <= 0:
        return MAX_REPAIR_PERCENT

    # 15% extra headroom accounts for ordinary LAN / Docker loss and
    # RaptorQ decoding overhead.
    required = math.ceil(
        ((FEC_SAFETY_FACTOR / valid_fraction) - 1.0) * 100.0
    )

    return min(
        MAX_REPAIR_PERCENT,
        max(DEFAULT_REPAIR_PERCENT, required),
    )


def get_net_binary() -> str:
    return os.getenv("UNIFLOW_NET_BINARY", DEFAULT_NET_BINARY)
