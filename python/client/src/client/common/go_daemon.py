import atexit
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def find_go_binary() -> Path:
    override = os.getenv("UNIFLOW_GO_BIN")
    if override:
        path = Path(override)
        if path.is_file():
            return path
        msg = f"UNIFLOW_GO_BIN does not exist: {override}"
        raise FileNotFoundError(msg)

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "go" / "uniflow"
        if candidate.is_file():
            return candidate

    from_path = shutil.which("uniflow-go")
    if from_path:
        return Path(from_path)

    msg = (
        "Go uniflow binary not found. Build it with "
        "'cd go && go build -o uniflow .' and set UNIFLOW_GO_BIN "
        "if it is not at <repo>/go/uniflow"
    )
    raise FileNotFoundError(msg)


def wait_for_socket(
    socket_path: Path,
    timeout_sec: float = 30.0,
    poll_interval: float = 0.1,
) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(poll_interval)

    msg = f"Timed out waiting for socket: {socket_path}"
    raise TimeoutError(msg)


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


class _SkippedProcess:
    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        return None


@contextmanager
def run_go_daemon(*args: str) -> Iterator[subprocess.Popen[bytes]]:
    if os.getenv("UNIFLOW_SKIP_GO") == "1":
        yield _SkippedProcess()  # type: ignore[misc]
        return

    binary = find_go_binary()
    proc = subprocess.Popen(
        [str(binary), *args],
        env=os.environ.copy(),
    )

    def cleanup() -> None:
        _stop_process(proc)

    atexit.register(cleanup)

    try:
        yield proc
    finally:
        atexit.unregister(cleanup)
        cleanup()

        exit_code = proc.poll()
        if exit_code not in (0, -15, None):
            msg = f"Go process exited with code {exit_code}: {args}"
            raise RuntimeError(msg)
