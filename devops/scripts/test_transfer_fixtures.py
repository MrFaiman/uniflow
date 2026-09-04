"""Tests for devops transfer fixture helpers."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from transfer_fixtures import (  # noqa: E402
    FixtureEntry,
    expected_sha256,
    parse_manifest,
    read_manifest_sidecar,
    verify_entry,
    write_fixture_file,
    write_manifest_sidecar,
)


def test_parse_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "fixtures.manifest"
    manifest.write_text("a.bin 1024\nnested/b.bin 2048\n")
    assert parse_manifest(manifest) == [("a.bin", 1024), ("nested/b.bin", 2048)]


def test_expected_sha256_matches_written_file(tmp_path: Path) -> None:
    rel = "sample.bin"
    size = 4096
    path = tmp_path / rel
    write_fixture_file(path, rel, size)
    digest = expected_sha256(rel, size)
    sidecar = write_manifest_sidecar(
        tmp_path,
        [FixtureEntry(relative_path=rel, size=size, sha256=digest)],
    )
    entries = read_manifest_sidecar(sidecar)
    assert verify_entry(tmp_path, entries[0]) is None
