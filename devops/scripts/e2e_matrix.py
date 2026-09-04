#!/usr/bin/env python3
"""End-to-end transfer matrix for Uniflow.

Brings up the real process topology (File Monitor + 3 Senders on TX,
3 Receivers + Session Manager on RX), optionally routes traffic through the
chaos router, drops a set of files into the watched directory, and verifies
every one arrives with a byte-identical SHA-256.

Usage:
    python3 e2e_matrix.py                 # direct TX -> RX, no faults
    python3 e2e_matrix.py --router        # traffic through the chaos router
    python3 e2e_matrix.py --router \\
        --loss 0.03 --flip 0.03 --misroute 0.03
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = REPO_ROOT / "python" / "uniflow"
GO_BIN = REPO_ROOT / "go" / ".bin" / "uniflow"

SMALL_MAX = 10 * 1024 * 1024


@dataclass
class Fixture:
    name: str
    size: int
    mode: str  # "single_pair" or "coordinated"
    nested: bool = False


def build_fixtures() -> list[Fixture]:
    return [
        Fixture("empty.bin", 0, "single_pair"),
        Fixture("tiny.bin", 1, "single_pair"),
        Fixture("1kb.bin", 1024, "single_pair"),
        Fixture("5mb.bin", 5 * 1024 * 1024, "single_pair"),
        Fixture("just_under_10mb.bin", SMALL_MAX - 1, "single_pair"),
        Fixture("just_over_10mb.bin", SMALL_MAX + 1, "coordinated"),
        Fixture("30mb.bin", 30 * 1024 * 1024, "coordinated"),
        Fixture("nested/deep/path.bin", 2048, "single_pair", nested=True),
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class Stack:
    """Owns every process this harness starts, so nothing is left behind."""

    def __init__(self, workdir: Path, use_router: bool, chaos: dict) -> None:
        self.workdir = workdir
        self.use_router = use_router
        self.chaos = chaos
        self.tx_out = workdir / "tx_out"
        self.rx_in = workdir / "rx_in"
        self.tx_log = workdir / "tx.log"
        self.rx_log = workdir / "rx.log"
        self.router_log = workdir / "router.log"
        # Unix socket paths must stay short; macOS caps sun_path near 104 B.
        self.ipc_socket = f"/tmp/uf_e2e_{os.getpid()}.sock"
        self.session_socket = f"/tmp/uf_e2e_sess_{os.getpid()}.sock"
        self.procs: list[subprocess.Popen] = []

    def _env(self, **extra: str) -> dict:
        env = os.environ.copy()
        env.update(
            {
                "PORT": "9000",
                "UNIFLOW_WORKERS": "3",
                "UNIFLOW_SKIP_BUILD": "1",
                "IPC_SOCKET_PATH": self.ipc_socket,
                "UNIFLOW_SESSION_SOCKET": self.session_socket,
                "RECEIVE_DIR": str(self.rx_in),
                "UNIFLOW_WATCH_POLLING": "1",
            },
        )
        env.update(extra)
        return env

    def start(self) -> None:
        self.tx_out.mkdir(parents=True, exist_ok=True)
        self.rx_in.mkdir(parents=True, exist_ok=True)
        for stale in (self.ipc_socket, self.session_socket):
            for path in Path("/tmp").glob(Path(stale).name + "*"):
                path.unlink(missing_ok=True)

        uv = shutil.which("uv") or "uv"

        with open(self.rx_log, "wb") as rx_log:
            self.procs.append(
                subprocess.Popen(
                    [uv, "run", "python", "-m", "uniflow.cli",
                     "receive", str(self.rx_in)],
                    cwd=PYTHON_DIR,
                    env=self._env(),
                    stdout=rx_log,
                    stderr=subprocess.STDOUT,
                ),
            )
        self._await_log(self.rx_log, "receiver listening", count=3)

        if self.use_router:
            with open(self.router_log, "wb") as router_log:
                self.procs.append(
                    subprocess.Popen(
                        # -u: unbuffered, so periodic [stats] lines reach the
                        # log file while the run is still in progress.
                        [sys.executable, "-u", "router/router.py"],
                        cwd=REPO_ROOT / "devops",
                        env=self._env(
                            PACKET_LOSS=str(self.chaos["loss"]),
                            BIT_FLIP=str(self.chaos["flip"]),
                            MISROUTING=str(self.chaos["misroute"]),
                            STATS_INTERVAL_SEC="5",
                            # Router and receivers share this host, so the
                            # router must listen on a distinct port range.
                            UNIFLOW_ROUTER_LISTEN_PORT="19000",
                            RX_HOST="127.0.0.1",
                        ),
                        stdout=router_log,
                        stderr=subprocess.STDOUT,
                    ),
                )
                self._await_log(self.router_log, "listening for TX", count=3)

        target = "127.0.0.1"
        with open(self.tx_log, "wb") as tx_log:
            self.procs.append(
                subprocess.Popen(
                    [uv, "run", "python", "-m", "uniflow.cli",
                     "send", str(self.tx_out), target],
                    cwd=PYTHON_DIR,
                    env=self._env(
                        **({"UNIFLOW_TARGET_PORT": "19000"}
                           if self.use_router else {}),
                    ),
                    stdout=tx_log,
                    stderr=subprocess.STDOUT,
                ),
            )
        self._await_log(self.tx_log, "watching", count=1)

    def _await_log(self, path: Path, needle: str, count: int,
                   timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                text = path.read_text(errors="replace")
                if text.count(needle) >= count:
                    return
            time.sleep(0.2)
        tail = path.read_text(errors="replace")[-2000:] if path.exists() else ""
        raise TimeoutError(
            f"waiting for {count}x {needle!r} in {path}\n--- log ---\n{tail}",
        )

    def stop(self) -> None:
        for proc in reversed(self.procs):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        for proc in reversed(self.procs):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs.clear()
        # The supervisors spawn grandchildren; make sure none survive.
        subprocess.run(
            ["pkill", "-f", f"IPC_SOCKET_PATH={self.ipc_socket}"],
            check=False,
        )
        for path in (self.ipc_socket, self.session_socket):
            for stale in Path("/tmp").glob(Path(path).name + "*"):
                stale.unlink(missing_ok=True)


def run_modification_phase(stack: Stack, timeout: float) -> int:
    """Overwrite already-transferred files and re-verify.

    Covers the spec's "creation and modification" watch requirement, repeated
    transfers of the same path, and re-use of an object that RX has already
    completed once.
    """
    print("\n=== MODIFICATION PHASE ===")
    targets = [
        ("1kb.bin", 4096),
        ("5mb.bin", 6 * 1024 * 1024),
        ("just_over_10mb.bin", 12 * 1024 * 1024),
    ]
    expected: dict[str, tuple[int, str]] = {}
    for name, new_size in targets:
        seed = hashlib.sha256(("modified-" + name).encode()).digest()
        data = (seed * (new_size // len(seed) + 1))[:new_size]
        (stack.tx_out / name).write_bytes(data)
        expected[name] = (new_size, hashlib.sha256(data).hexdigest())
        print(f"  modified {name} -> {new_size} bytes")

    deadline = time.monotonic() + timeout
    remaining = dict(expected)
    while remaining and time.monotonic() < deadline:
        for name, (size, want_hash) in list(remaining.items()):
            candidate = stack.rx_in / name
            if (
                candidate.exists()
                and candidate.stat().st_size == size
                and sha256_file(candidate) == want_hash
            ):
                del remaining[name]
        if remaining:
            time.sleep(0.5)

    failures = 0
    for name, (size, want_hash) in expected.items():
        candidate = stack.rx_in / name
        if not candidate.exists():
            print(f"  FAIL {name}: modified version never arrived")
            failures += 1
        elif sha256_file(candidate) != want_hash:
            print(f"  FAIL {name}: still holds the pre-modification content")
            failures += 1
        else:
            print(f"  OK   {name}  {size} bytes (modified content verified)")
    return failures


def run_matrix(stack: Stack, timeout: float) -> int:
    fixtures = build_fixtures()
    expected: dict[str, tuple[int, str]] = {}

    for fixture in fixtures:
        path = stack.tx_out / fixture.name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deterministic-but-incompressible content, seeded per fixture.
        content = hashlib.sha256(fixture.name.encode()).digest()
        data = (content * (fixture.size // len(content) + 1))[: fixture.size]
        path.write_bytes(data)
        expected[fixture.name] = (fixture.size, hashlib.sha256(data).hexdigest())
        print(f"  queued {fixture.name} ({fixture.size} bytes, {fixture.mode})")

    print("\nwaiting for transfers...")
    deadline = time.monotonic() + timeout
    remaining = dict(expected)
    while remaining and time.monotonic() < deadline:
        for name, (size, _) in list(remaining.items()):
            candidate = stack.rx_in / name
            if candidate.exists() and candidate.stat().st_size == size:
                del remaining[name]
        if remaining:
            time.sleep(0.5)

    failures = 0
    print("\n=== RESULTS ===")
    for fixture in fixtures:
        name = fixture.name
        size, want_hash = expected[name]
        candidate = stack.rx_in / name
        if not candidate.exists():
            print(f"  FAIL {name}: never arrived")
            failures += 1
            continue
        got_size = candidate.stat().st_size
        got_hash = sha256_file(candidate)
        if got_size != size:
            print(f"  FAIL {name}: size {got_size} != {size}")
            failures += 1
        elif got_hash != want_hash:
            print(f"  FAIL {name}: sha256 mismatch")
            print(f"       want {want_hash}")
            print(f"       got  {got_hash}")
            failures += 1
        else:
            print(f"  OK   {name}  {size} bytes  sha256={got_hash[:16]}...")
    return failures


def check_router_traffic(stack: Stack) -> int:
    """Fail loudly if a --router run never actually traversed the router.

    Misconfigured ports silently route TX straight to RX, which makes a
    fault-injection run look like a clean pass while injecting nothing.
    """
    if not stack.use_router:
        return 0
    # The router dumps aggregate stats only when its socket goes idle, so a
    # run that finishes promptly can reach this check before the first dump.
    # Wait for one rather than reporting a false failure.
    deadline = time.monotonic() + 20.0
    summary: list[str] = []
    while time.monotonic() < deadline:
        text = stack.router_log.read_text(errors="replace")
        summary = [
            ln for ln in text.splitlines() if ln.startswith("[stats] received")
        ]
        if summary:
            break
        time.sleep(0.5)
    if not summary:
        print("\nrouter: no stats line found")
        print("  ERROR: router produced no statistics")
        return 1
    print(f"\nrouter {summary[-1]}")
    received = int(summary[-1].split("received=")[1].split()[0])
    if received == 0:
        print("  ERROR: router saw no traffic; TX bypassed it entirely")
        return 1
    return 0


def check_concurrency(stack: Stack) -> None:
    """Report whether senders/receivers actually overlapped in time."""
    tx = stack.tx_log.read_text(errors="replace")
    starts = [
        line.split("time=")[1].split()[0]
        for line in tx.splitlines()
        if "ipc command" in line and "coordinated=true" in line
    ]
    if starts:
        print(f"\ncoordinated sender dispatches: {len(starts)}")
        print(f"  earliest start: {min(starts)}")
        print(f"  latest start:   {max(starts)}")
        print("  (identical/near-identical starts == genuine parallelism)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", action="store_true")
    parser.add_argument("--loss", type=float, default=0.0)
    parser.add_argument("--flip", type=float, default=0.0)
    parser.add_argument("--misroute", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args()

    if not GO_BIN.is_file():
        print(f"missing Go binary at {GO_BIN}; build it first", file=sys.stderr)
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="uniflow-e2e-"))
    chaos = {
        "loss": args.loss,
        "flip": args.flip,
        "misroute": args.misroute,
    }
    label = "via router" if args.router else "direct"
    print(f"=== Uniflow E2E matrix ({label}) ===")
    if args.router:
        print(f"chaos: loss={args.loss} flip={args.flip} "
              f"misroute={args.misroute}")
    print(f"workdir: {workdir}\n")

    stack = Stack(workdir, args.router, chaos)
    try:
        stack.start()
        failures = run_matrix(stack, args.timeout)
        failures += check_router_traffic(stack)
        check_concurrency(stack)
    finally:
        stack.stop()
        if not args.keep_workdir and not failures:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"\nlogs kept in {workdir}")

    print(f"\n{'FAILED' if failures else 'PASSED'}: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
