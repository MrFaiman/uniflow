#!/usr/bin/env python3
"""Verify devops transfer test files arrived with matching size and checksum."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from transfer_fixtures import MANIFEST_SIDECAR, read_manifest_sidecar, verify_entry


def verify_all(receive_dir: Path, sidecar_path: Path) -> tuple[bool, list[str]]:
    entries = read_manifest_sidecar(sidecar_path)
    failures: list[str] = []
    for entry in entries:
        err = verify_entry(receive_dir, entry)
        if err is None:
            print(f"OK   {entry.relative_path} ({entry.size} bytes)")
        else:
            print(f"FAIL {entry.relative_path}: {err}")
            failures.append(f"{entry.relative_path}: {err}")
    return len(failures) == 0, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify devops transfer test files")
    parser.add_argument(
        "--receive-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "in",
        help="Directory where files should appear",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "out" / MANIFEST_SIDECAR,
        help="Manifest sidecar with expected size and sha256",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until all files verify or timeout",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=3600,
        help="Max wait time when --wait is set",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=5.0,
        help="Poll interval when --wait is set",
    )
    args = parser.parse_args()

    if not args.sidecar.is_file():
        print(f"sidecar not found: {args.sidecar}", file=sys.stderr)
        return 1

    if not args.wait:
        ok, failures = verify_all(args.receive_dir, args.sidecar)
        if not ok:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("All transfers verified.")
        return 0

    deadline = time.monotonic() + args.timeout_sec
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        print(f"--- verification attempt {attempt} ---")
        ok, failures = verify_all(args.receive_dir, args.sidecar)
        if ok:
            print("All transfers verified.")
            return 0
        remaining = int(deadline - time.monotonic())
        print(f"Waiting {args.poll_sec:.0f}s ({remaining}s remaining)...")
        time.sleep(args.poll_sec)

    print("Timed out waiting for transfers.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
