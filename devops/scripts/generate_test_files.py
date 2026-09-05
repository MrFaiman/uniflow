#!/usr/bin/env python3
"""Generate deterministic devops transfer test files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from transfer_fixtures import (
    FixtureEntry,
    expected_sha256,
    parse_manifest,
    write_fixture_file,
    write_manifest_sidecar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate devops transfer test files")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("fixtures.manifest"),
        help="Manifest listing relative_path and size",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "out",
        help="Directory to write test files",
    )
    args = parser.parse_args()

    manifest_entries = parse_manifest(args.manifest)
    sidecar_entries: list[FixtureEntry] = []

    print(f"Generating {len(manifest_entries)} files in {args.out_dir}")
    for relative_path, size in manifest_entries:
        out_path = args.out_dir / relative_path
        print(f"  {relative_path} ({size} bytes)")
        write_fixture_file(out_path, relative_path, size)
        digest = expected_sha256(relative_path, size)
        sidecar_entries.append(
            FixtureEntry(relative_path=relative_path, size=size, sha256=digest),
        )

    sidecar = write_manifest_sidecar(args.out_dir, sidecar_entries)
    print(f"Wrote manifest sidecar: {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
