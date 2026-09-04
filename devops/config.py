import os

ROUTER_IP = "0.0.0.0"
ROUTER_PORT = 5000
ROUTER_HOST = "router"
MAX_UDP_PACKET_SIZE = 65535

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)

START_PORT = _env_int("PORT", _env_int("UDP_PORT", 9000))
WORKER_COUNT = max(_env_int("UNIFLOW_WORKERS", 3), 3)

# Where the router forwards to. In Docker the RX machine is a separate
# container, so it can reuse the same port numbers the router listens on.
RX_HOST = os.environ.get("RX_HOST", "rx_machine")
RX_PORT_LIST = [START_PORT + i for i in range(WORKER_COUNT)]

# Where the router listens. Defaults to the same ports it forwards to, which
# only works when RX is a different host. Running router and receivers on one
# machine (local testing) needs a distinct listen range.
ROUTER_LISTEN_BASE = _env_int("UNIFLOW_ROUTER_LISTEN_PORT", START_PORT)
LISTEN_PORT_LIST = [ROUTER_LISTEN_BASE + i for i in range(WORKER_COUNT)]

# Maps each listen port to the RX port it normally forwards to, so a
# misroute can pick a genuinely different receiver.
FORWARD_PORT_BY_LISTEN_PORT = dict(zip(LISTEN_PORT_LIST, RX_PORT_LIST))

def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)

class DisruptionProbabilities:
    PACKET_LOSS = _env_float("PACKET_LOSS", 0.03)
    BIT_FLIP = _env_float("BIT_FLIP", 0.03)
    MISROUTING = _env_float("MISROUTING", 0.03)

STATS_INTERVAL_SEC = int(os.environ.get("STATS_INTERVAL_SEC", "10"))