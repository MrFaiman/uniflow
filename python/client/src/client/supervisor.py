import os
import socket
import subprocess
import time
from pathlib import Path

from client.common.config import (
    get_base_port,
    get_net_binary,
    get_sender_socket_path,
    get_socket_path,
    get_worker_count,
)


class _BaseSupervisor:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen] = []

    def _start_worker(self, mode: str, worker: int, env: dict[str, str]) -> None:
        process = subprocess.Popen([get_net_binary(), mode], env=env)
        self.processes.append(process)
        print(f"Started {mode} worker {worker} with PID {process.pid}", flush=True)

    def check(self) -> None:
        for process in self.processes:
            code = process.poll()
            if code is not None:
                raise RuntimeError(
                    f"network worker PID {process.pid} exited with code {code}"
                )

    def stop(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()

        deadline = time.monotonic() + 5
        for process in self.processes:
            if process.poll() is not None:
                continue
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    pass

        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait()

        self.processes.clear()


class SenderSupervisor(_BaseSupervisor):
    def __init__(self, router_host: str) -> None:
        super().__init__()
        self.router_host = router_host
        self.socket_paths: list[Path] = []

    def start(self) -> list[Path]:
        workers = get_worker_count()
        base_port = get_base_port()

        for worker in range(workers):
            socket_path = get_sender_socket_path(worker)
            socket_path.unlink(missing_ok=True)

            env = os.environ.copy()
            env["IPC_SOCKET_PATH"] = str(socket_path)
            env["ROUTER_HOST"] = self.router_host
            env["UDP_PORT"] = str(base_port + worker)
            env["UNIFLOW_WORKER_INDEX"] = str(worker)
            env["UNIFLOW_WORKER_COUNT"] = str(workers)

            self.socket_paths.append(socket_path)
            self._start_worker("send", worker, env)

        self._wait_for_sender_sockets()
        return list(self.socket_paths)

    def _wait_for_sender_sockets(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout

        for path in self.socket_paths:
            while time.monotonic() < deadline:
                self.check()
                if path.exists():
                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                            sock.settimeout(0.2)
                            sock.connect(str(path))
                        break
                    except OSError:
                        pass
                time.sleep(0.05)
            else:
                raise RuntimeError(f"Sender socket did not become ready: {path}")

    def stop(self) -> None:
        super().stop()
        for path in self.socket_paths:
            path.unlink(missing_ok=True)
        self.socket_paths.clear()


class ReceiverSupervisor(_BaseSupervisor):
    def start(self) -> None:
        workers = get_worker_count()
        base_port = get_base_port()
        manager_socket = get_socket_path()

        for worker in range(workers):
            env = os.environ.copy()
            env["IPC_SOCKET_PATH"] = str(manager_socket)
            env["UDP_PORT"] = str(base_port + worker)
            env["UNIFLOW_WORKER_INDEX"] = str(worker)
            env["UNIFLOW_WORKER_COUNT"] = str(workers)
            self._start_worker("recv", worker, env)
