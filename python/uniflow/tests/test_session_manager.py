import hashlib
from pathlib import Path

from uniflow.pb import message_pb2
from uniflow.session_manager import SessionManager


def _report(
    *,
    object_id: int,
    block_index: int,
    staging_path: str,
    file_name: str,
    file_size: int,
    source_blocks: int,
    checksum: bytes,
    worker_index: int = 0,
) -> message_pb2.BlockReport:
    return message_pb2.BlockReport(
        session_id=1,
        object_id=object_id,
        worker_index=worker_index,
        file_name=file_name,
        file_size=file_size,
        source_blocks=source_blocks,
        symbol_size=1024,
        checksum=checksum,
        block_index=block_index,
        staging_path=staging_path,
    )


def _stage(tmp_path: Path, name: str, payload: bytes) -> str:
    path = tmp_path / "staging" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_reconstructs_only_after_every_block_reported(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    part_a = b"a" * 32
    part_b = b"b" * 16
    whole = part_a + part_b
    checksum = hashlib.sha256(whole).digest()

    manager.handle_report(
        _report(
            object_id=1,
            block_index=0,
            staging_path=_stage(tmp_path, "b0", part_a),
            file_name="out.bin",
            file_size=len(whole),
            source_blocks=2,
            checksum=checksum,
        ),
    )
    # One of two blocks: nothing may be written yet.
    assert not (out_dir / "out.bin").exists()

    manager.handle_report(
        _report(
            object_id=1,
            block_index=1,
            staging_path=_stage(tmp_path, "b1", part_b),
            file_name="out.bin",
            file_size=len(whole),
            source_blocks=2,
            checksum=checksum,
            worker_index=1,
        ),
    )
    assert (out_dir / "out.bin").read_bytes() == whole


def test_blocks_from_different_workers_are_combined(tmp_path: Path) -> None:
    """Blocks are keyed by index, not by which Receiver reported them.

    This is what lets a misrouted packet still count: whichever Receiver
    decoded the block, the Session Manager files it under the same object.
    """
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    parts = [b"0" * 8, b"1" * 8, b"2" * 8]
    whole = b"".join(parts)
    checksum = hashlib.sha256(whole).digest()

    # Deliberately report block 1 from the "wrong" worker.
    for index, (part, worker) in enumerate(zip(parts, [0, 2, 2])):
        manager.handle_report(
            _report(
                object_id=7,
                block_index=index,
                staging_path=_stage(tmp_path, f"blk{index}", part),
                file_name="combined.bin",
                file_size=len(whole),
                source_blocks=3,
                checksum=checksum,
                worker_index=worker,
            ),
        )
    assert (out_dir / "combined.bin").read_bytes() == whole


def test_hash_mismatch_leaves_no_output_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    payload = b"z" * 16
    manager.handle_report(
        _report(
            object_id=2,
            block_index=0,
            staging_path=_stage(tmp_path, "bad", payload),
            file_name="bad.bin",
            file_size=len(payload),
            source_blocks=1,
            checksum=hashlib.sha256(b"something else").digest(),
        ),
    )
    assert not (out_dir / "bad.bin").exists()
    assert not (out_dir / "bad.bin.part").exists()


def test_empty_file_is_created(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    manager.handle_report(
        _report(
            object_id=3,
            block_index=0,
            staging_path="",
            file_name="empty.bin",
            file_size=0,
            source_blocks=0,
            checksum=hashlib.sha256(b"").digest(),
        ),
    )
    assert (out_dir / "empty.bin").read_bytes() == b""


def test_nested_relative_path_is_preserved(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    payload = b"nested"
    manager.handle_report(
        _report(
            object_id=4,
            block_index=0,
            staging_path=_stage(tmp_path, "n", payload),
            file_name="sub/deep/file.bin",
            file_size=len(payload),
            source_blocks=1,
            checksum=hashlib.sha256(payload).digest(),
        ),
    )
    assert (out_dir / "sub" / "deep" / "file.bin").read_bytes() == payload


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    payload = b"evil"
    manager.handle_report(
        _report(
            object_id=5,
            block_index=0,
            staging_path=_stage(tmp_path, "e", payload),
            file_name="../escaped.bin",
            file_size=len(payload),
            source_blocks=1,
            checksum=hashlib.sha256(payload).digest(),
        ),
    )
    assert not (tmp_path / "escaped.bin").exists()


def test_stalled_transfer_is_reported_once(tmp_path: Path) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    payload = b"partial"
    manager.handle_report(
        _report(
            object_id=6,
            block_index=0,
            staging_path=_stage(tmp_path, "p", payload),
            file_name="partial.bin",
            file_size=len(payload) * 4,
            source_blocks=4,
            checksum=hashlib.sha256(payload).digest(),
        ),
    )
    # Not yet idle long enough.
    assert manager.report_stalls(stall_after=600.0) == []
    # Idle past the threshold: reported exactly once, never repeatedly.
    assert manager.report_stalls(stall_after=0.0) == [6]
    assert manager.report_stalls(stall_after=0.0) == []


def test_completed_transfer_is_never_reported_as_stalled(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "in"
    out_dir.mkdir()
    manager = SessionManager(str(tmp_path / "sock"), out_dir)

    payload = b"done"
    manager.handle_report(
        _report(
            object_id=8,
            block_index=0,
            staging_path=_stage(tmp_path, "d", payload),
            file_name="done.bin",
            file_size=len(payload),
            source_blocks=1,
            checksum=hashlib.sha256(payload).digest(),
        ),
    )
    assert (out_dir / "done.bin").exists()
    assert manager.report_stalls(stall_after=0.0) == []
