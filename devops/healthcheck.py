"""Check local Linux socket/process readiness without sending network traffic."""

import os
import sys
from pathlib import Path


def bound_udp_ports() -> set[int]:
    ports = set()
    for line in Path("/proc/net/udp").read_text().splitlines()[1:]:
        ports.add(int(line.split()[1].rsplit(":", 1)[1], 16))
    return ports


def worker_count(mode: str) -> int:
    count = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if len(args) >= 2 and Path(os.fsdecode(args[0])).name == "uniflow-net":
            count += args[1] == mode.encode()
    return count


def healthy(mode: str) -> bool:
    base = int(os.environ.get("PORT", "9000"))
    required = set(range(base, base + 3))
    default_ipc = "/tmp/uniflow/send.sock" if mode == "send" else "/tmp/uniflow/recv.sock"
    ipc = Path(os.environ.get("IPC_SOCKET_PATH") or default_ipc)
    if mode == "router":
        return required <= bound_udp_ports()
    if mode == "receive":
        return (ipc.is_socket() and worker_count("recv") == 3
                and required <= bound_udp_ports())
    if mode == "send":
        return worker_count("send") == 3 and all(
            Path(f"{ipc}.sender.{index}").is_socket() for index in range(3)
        )
    raise ValueError(f"unknown healthcheck mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(0 if healthy(sys.argv[1]) else 1)
