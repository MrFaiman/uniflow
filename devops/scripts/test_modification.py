#!/usr/bin/env python3
"""Modify one TX file and verify RX eventually contains the new version."""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--received", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=300)
    args = parser.parse_args()

    new_data = (b"uniflow-modified-version\n" * 4096) + b"done\n"
    args.source.parent.mkdir(parents=True, exist_ok=True)
    args.source.write_bytes(new_data)
    expected = hashlib.sha256(new_data).hexdigest()

    deadline = time.monotonic() + args.timeout_sec
    while time.monotonic() < deadline:
        if args.received.is_file():
            if args.received.stat().st_size == len(new_data):
                if sha256_file(args.received) == expected:
                    print(f"Modification verified: {args.received} SHA-256={expected}")
                    return 0
        time.sleep(1)

    print("Timed out waiting for modified file")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
