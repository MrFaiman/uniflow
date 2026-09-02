import logging
import os
import secrets
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from uniflow.process_pool import WorkerProcessPool, WorkerSpec
from uniflow.utils import (
    load_dot_env,
    socket_path,
    udp_port,
    worker_count,
)

logger = logging.getLogger(__name__)


@dataclass
class SenderSupervisor:
    pool: WorkerProcessPool | None = None
    sender_socket_paths: list[str] = field(default_factory=list)

    def start(self) -> list[str]:
        load_dot_env()
        go_dir = _find_go_dir()
        binary = _build_binary(go_dir)
        workers = worker_count()
        base_socket = socket_path()
        base_port = udp_port()
        port_list = ",".join(str(base_port + i) for i in range(workers))
        session_id = secrets.randbits(63)

        specs: list[WorkerSpec] = []
        for i in range(workers):
            sock_path = f"{base_socket}.{i}"
            env = os.environ.copy()
            env["IPC_SOCKET_PATH"] = sock_path
            env["UDP_PORTS"] = port_list
            env["UNIFLOW_SESSION_ID"] = str(session_id)
            env["UNIFLOW_WORKER_INDEX"] = str(i)
            env["UNIFLOW_WORKER_COUNT"] = str(workers)
            specs.append(
                WorkerSpec(
                    binary=str(binary),
                    cwd=str(go_dir),
                    env=env,
                    args=["send"],
                ),
            )
            self.sender_socket_paths.append(sock_path)
            logger.info(
                "queued sender %d socket=%s ports=%s session=%d",
                i,
                sock_path,
                port_list,
                session_id,
            )

        self.pool = WorkerProcessPool(max_workers=workers)
        for spec in specs:
            self.pool.submit(spec)

        _wait_for_sockets(self.sender_socket_paths)
        return list(self.sender_socket_paths)

    def stop(self) -> None:
        if self.pool is not None:
            self.pool.shutdown()
            self.pool = None
        for path in self.sender_socket_paths:
            if os.path.exists(path):
                os.unlink(path)
        self.sender_socket_paths.clear()


@dataclass
class ReceiverSupervisor:
    receive_base: Path
    pool: WorkerProcessPool | None = None

    def start(self) -> None:
        load_dot_env()
        go_dir = _find_go_dir()
        binary = _build_binary(go_dir)
        workers = worker_count()
        base_port = udp_port()
        receive_dir = self.receive_base.expanduser().resolve()
        receive_dir.mkdir(parents=True, exist_ok=True)

        specs: list[WorkerSpec] = []
        for i in range(workers):
            env = os.environ.copy()
            env["UDP_PORT"] = str(base_port + i)
            env["RECEIVE_DIR"] = str(receive_dir)
            env["UNIFLOW_WORKER_INDEX"] = str(i)
            env["UNIFLOW_WORKER_COUNT"] = str(workers)
            specs.append(
                WorkerSpec(
                    binary=str(binary),
                    cwd=str(go_dir),
                    env=env,
                    args=["recv", str(receive_dir)],
                ),
            )
            logger.info(
                "queued receiver %d port=%d dir=%s",
                i,
                base_port + i,
                receive_dir,
            )

        self.pool = WorkerProcessPool(max_workers=workers)
        for spec in specs:
            self.pool.submit(spec)

    def wait(self) -> None:
        if self.pool is None:
            return
        self.pool.wait_for_failure()

    def stop(self) -> None:
        if self.pool is not None:
            self.pool.shutdown()
            self.pool = None


def _find_go_dir() -> Path:
    start = Path(__file__).resolve().parent
    for directory in (start, *start.parents):
        candidate = directory / "go"
        if (candidate / "go.mod").is_file():
            return candidate
    raise RuntimeError("could not find go module directory")


def _build_binary(go_dir: Path) -> Path:
    out = go_dir / ".bin" / "uniflow"
    if os.environ.get("UNIFLOW_SKIP_BUILD") == "1" and out.is_file():
        logger.info("using prebuilt binary %s", out)
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    logger.info("building %s", out)
    subprocess.run(
        ["go", "build", "-o", str(out), "."],
        cwd=str(go_dir),
        check=True,
    )
    return out


def _wait_for_sockets(paths: list[str], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    for path in paths:
        while time.monotonic() < deadline:
            if os.path.exists(path):
                try:
                    with socket.socket(
                        socket.AF_UNIX,
                        socket.SOCK_STREAM,
                    ) as sock:
                        sock.connect(path)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                time.sleep(0.05)
        else:
            raise RuntimeError(f"sender socket not ready: {path}")
