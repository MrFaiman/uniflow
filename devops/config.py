import os

<<<<<<< HEAD

ROUTER_IP = "0.0.0.0"
ROUTER_PORT = 5000
ROUTER_HOST = "router"

RX_HOST = "rx_machine"

MAX_UDP_PACKET_SIZE = 65535


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


=======
ROUTER_IP = "0.0.0.0"
ROUTER_PORT = 5000
ROUTER_HOST = "router"
RX_HOST = "rx_machine"
MAX_UDP_PACKET_SIZE = 65535

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)

>>>>>>> yair
START_PORT = _env_int("PORT", _env_int("UDP_PORT", 9000))
WORKER_COUNT = max(_env_int("UNIFLOW_WORKERS", 3), 3)
RX_PORT_LIST = [START_PORT + i for i in range(WORKER_COUNT)]

<<<<<<< HEAD

def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)

=======
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)
>>>>>>> yair

class DisruptionProbabilities:
    PACKET_LOSS = _env_float("PACKET_LOSS", 0.03)
    BIT_FLIP = _env_float("BIT_FLIP", 0.03)
    MISROUTING = _env_float("MISROUTING", 0.03)

<<<<<<< HEAD

STATS_INTERVAL_SEC = int(os.environ.get("STATS_INTERVAL_SEC", "10"))
=======
STATS_INTERVAL_SEC = int(os.environ.get("STATS_INTERVAL_SEC", "10"))
>>>>>>> yair
