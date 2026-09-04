"""Shared helpers for deterministic transfer fixtures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 1024 * 1024
MANIFEST_SIDECAR = ".manifest.sha256"


@dataclass(frozen=True)
class FixtureEntry:
    relative_path: str
    size: int
    sha256: str


def parse_size(raw: str) -> int:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)

    units = {"K": 1024, "M": 1024**2, "G": 1024**3}
    suffix = raw[-1].upper()
    if suffix in units:
        return int(float(raw[:-1]) * units[suffix])
    raise ValueError(f"invalid size: {raw!r}")


def parse_manifest(manifest_path: Path) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for line in manifest_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"invalid manifest line: {line!r}")
        entries.append((parts[0], parse_size(parts[1])))
    return entries


def _pattern(relative_path: str) -> bytes:
    digest = hashlib.sha256(relative_path.encode()).digest()
    repeats = (CHUNK_SIZE + len(digest) - 1) // len(digest)
    return (digest * repeats)[:CHUNK_SIZE]


def _iter_chunks(relative_path: str, size: int):
    pattern = _pattern(relative_path)
    remaining = size
    while remaining > 0:
        chunk = pattern[: min(CHUNK_SIZE, remaining)]
        yield chunk
        remaining -= len(chunk)


def write_fixture_file(path: Path, relative_path: str, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for chunk in _iter_chunks(relative_path, size):
            handle.write(chunk)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha256(relative_path: str, size: int) -> str:
    digest = hashlib.sha256()
    for chunk in _iter_chunks(relative_path, size):
        digest.update(chunk)
    return digest.hexdigest()


def write_manifest_sidecar(out_dir: Path, entries: list[FixtureEntry]) -> Path:
    sidecar = out_dir / MANIFEST_SIDECAR
    lines = [
        f"{entry.relative_path} {entry.size} {entry.sha256}"
        for entry in entries
    ]
    sidecar.write_text("\n".join(lines) + "\n")
    return sidecar


def read_manifest_sidecar(sidecar_path: Path) -> list[FixtureEntry]:
    entries: list[FixtureEntry] = []
    for line in sidecar_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError(f"invalid sidecar line: {line!r}")
        entries.append(
            FixtureEntry(
                relative_path=parts[0],
                size=int(parts[1]),
                sha256=parts[2],
            )
        )
    return entries


def verify_entry(receive_dir: Path, entry: FixtureEntry) -> str | None:
    path = receive_dir / entry.relative_path
    if not path.is_file():
        return "missing"
    if path.stat().st_size != entry.size:
        return f"size mismatch (got {path.stat().st_size}, want {entry.size})"

    got = sha256_file(path)
    if got != entry.sha256:
        return f"checksum mismatch (got {got}, want {entry.sha256})"
    return None
