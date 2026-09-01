from pathlib import Path

import pytest
from watchdog.events import (
    DirCreatedEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileMovedEvent,
)

from uniflow.ipc import Ipc
from uniflow.watch import FolderEventHandler


def test_handler_broadcasts_coordinated_for_large_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    large = tmp_path / "big.bin"
    large.write_bytes(b"x" * (10 * 1024 * 1024))

    sent: list[tuple[bool, int]] = []
    ipc0 = Ipc("/tmp/ignored0.sock")
    ipc1 = Ipc("/tmp/ignored1.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append((coordinated, object_id))

    monkeypatch.setattr(ipc0, "send", fake_send)
    monkeypatch.setattr(ipc1, "send", fake_send)
    handler = FolderEventHandler("10.0.0.1", [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(large)))
    assert sent == [(True, 1), (True, 1)]


def test_handler_single_pair_for_small_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    small = tmp_path / "small.bin"
    small.write_bytes(b"hello")

    sent: list[tuple[int, bool, int]] = []
    ipc0 = Ipc("/tmp/ignored0.sock")
    ipc1 = Ipc("/tmp/ignored1.sock")

    def fake_send0(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append((0, coordinated, object_id))

    def fake_send1(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append((1, coordinated, object_id))

    monkeypatch.setattr(ipc0, "send", fake_send0)
    monkeypatch.setattr(ipc1, "send", fake_send1)
    handler = FolderEventHandler("10.0.0.1", [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(small)))
    assert len(sent) == 1
    assert sent[0] == (0, False, 1)


def test_handler_parallel_small_files_use_different_pairs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    pairs: list[int] = []
    ipc0 = Ipc("/tmp/ignored0.sock")
    ipc1 = Ipc("/tmp/ignored1.sock")

    def fake_send0(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        pairs.append(0)

    def fake_send1(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        pairs.append(1)

    monkeypatch.setattr(ipc0, "send", fake_send0)
    monkeypatch.setattr(ipc1, "send", fake_send1)
    handler = FolderEventHandler("10.0.0.1", [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(a)))
    handler.on_any_event(FileCreatedEvent(src_path=str(b)))
    assert pairs == [0, 1]


def test_handler_sends_moved_src_and_dest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dest = tmp_path / "b.txt"
    dest.write_bytes(b"data")

    sent: list[bool] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append(coordinated)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = FolderEventHandler("10.0.0.1", [ipc])
    handler.on_any_event(
        FileMovedEvent(src_path=str(tmp_path / "a.txt"), dest_path=str(dest)),
    )
    assert sent == [False]


def test_handler_ignores_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[bool] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append(coordinated)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = FolderEventHandler("10.0.0.1", [ipc])
    handler.on_any_event(DirCreatedEvent(src_path="/tmp/folder/sub"))
    assert sent == []


def test_handler_ignores_closed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[bool] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
    ) -> None:
        sent.append(coordinated)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = FolderEventHandler("10.0.0.1", [ipc])
    handler.on_any_event(FileClosedEvent(src_path="/tmp/folder/a.txt"))
    assert sent == []
