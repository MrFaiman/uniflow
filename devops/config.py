from __future__ import annotations

import os
from dataclasses import dataclass


ROUTER_IP = "0.0.0.0"

# Local all-in-one:
#     RX_HOST defaults to "rx_machine"
#
# Two physical PCs:
#     RX_HOST can be something like "192.168.1.50"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw == "1"


@dataclass(frozen=True)
class RouterConfig:
    bind: str = ROUTER_IP
    rx_host: str = "rx_machine"
    start_port: int = 9000
    worker_count: int = 3
    packet_loss: float = 0.03
    bit_flip: float = 0.03
    misrouting: float = 0.03
    stats_interval_sec: int = 10
    log_packets: bool = False
    random_seed: int = 1337

    @property
    def ports(self) -> list[int]:
        return [self.start_port + index for index in range(self.worker_count)]

    def validate(self) -> None:
        if self.worker_count != 3:
            raise ValueError("The trio project requires exactly 3 workers")
        for value in (self.packet_loss, self.bit_flip, self.misrouting):
            if value < 0 or value > 1:
                raise ValueError(
                    "router fault probabilities must be between 0 and 1"
                )

    @classmethod
    def from_env(cls) -> RouterConfig:
        config = cls(
            bind=os.environ.get("ROUTER_IP", ROUTER_IP),
            rx_host=os.environ.get("RX_HOST", "rx_machine"),
            start_port=_env_int("PORT", 9000),
            worker_count=_env_int("UNIFLOW_WORKERS", 3),
            packet_loss=_env_float("PACKET_LOSS", 0.03),
            bit_flip=_env_float("BIT_FLIP", 0.03),
            misrouting=_env_float("MISROUTING", 0.03),
            stats_interval_sec=_env_int("STATS_INTERVAL_SEC", 10),
            log_packets=_env_flag("LOG_PACKETS"),
            random_seed=_env_int("RANDOM_SEED", 1337),
        )
        config.validate()
        return config


_ENV = RouterConfig.from_env()

RX_HOST = _ENV.rx_host
START_PORT = _ENV.start_port
WORKER_COUNT = _ENV.worker_count
RX_PORT_LIST = _ENV.ports


class DisruptionProbabilities:
    PACKET_LOSS = _ENV.packet_loss
    BIT_FLIP = _ENV.bit_flip
    MISROUTING = _ENV.misrouting


STATS_INTERVAL_SEC = _ENV.stats_interval_sec
LOG_PACKETS = _ENV.log_packets
RANDOM_SEED = _ENV.random_seed
