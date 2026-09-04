import os

ROUTER_IP = "0.0.0.0"
RX_HOST = os.environ.get("RX_HOST", "rx_machine")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)


START_PORT = _env_int("PORT", 9000)
WORKER_COUNT = _env_int("UNIFLOW_WORKERS", 3)
if WORKER_COUNT != 3:
    raise ValueError("The trio project requires exactly 3 workers")

RX_PORT_LIST = [START_PORT + i for i in range(WORKER_COUNT)]


class DisruptionProbabilities:
    PACKET_LOSS = _env_float("PACKET_LOSS", 0.03)
    BIT_FLIP = _env_float("BIT_FLIP", 0.03)
    MISROUTING = _env_float("MISROUTING", 0.03)


for value in (
    DisruptionProbabilities.PACKET_LOSS,
    DisruptionProbabilities.BIT_FLIP,
    DisruptionProbabilities.MISROUTING,
):
    if value < 0 or value > 1:
        raise ValueError("router fault probabilities must be between 0 and 1")

STATS_INTERVAL_SEC = _env_int("STATS_INTERVAL_SEC", 10)
LOG_PACKETS = os.environ.get("LOG_PACKETS", "0") == "1"
RANDOM_SEED = _env_int("RANDOM_SEED", 1337)
