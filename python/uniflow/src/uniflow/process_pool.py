import logging
import multiprocessing
import subprocess
import time
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerSpec:
    binary: str
    cwd: str
    env: dict[str, str]
    args: list[str]


def _go_worker_entry(spec: WorkerSpec) -> int:
    proc = subprocess.Popen(
        [spec.binary, *spec.args],
        cwd=spec.cwd,
        env=spec.env,
    )
    try:
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


class WorkerProcessPool:
    def __init__(self, max_workers: int) -> None:
        ctx = multiprocessing.get_context("spawn")
        self._executor = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=ctx,
        )
        self._futures: list[Future[int]] = []

    def submit(self, spec: WorkerSpec) -> None:
        self._futures.append(self._executor.submit(_go_worker_entry, spec))

    def wait_for_failure(self, poll_interval: float = 0.5) -> None:
        try:
            while True:
                for future in self._futures:
                    if future.done():
                        exc = future.exception()
                        if exc is not None:
                            raise RuntimeError(f"worker failed: {exc}") from exc
                        code = future.result()
                        if code != 0:
                            raise RuntimeError(
                                f"worker exited with code {code}",
                            )
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("worker pool interrupted")

    def shutdown(self, timeout: float = 5.0) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        deadline = time.monotonic() + timeout
        for future in self._futures:
            if future.done():
                continue
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    future.result(timeout=remaining)
                except TimeoutError:
                    pass
        self._futures.clear()
