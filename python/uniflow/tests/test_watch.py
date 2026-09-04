from pathlib import Path

import pytest
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileMovedEvent,
)

from uniflow.ipc import Ipc
from uniflow.watch import FolderEventHandler


def _handler(tmp_path: Path, ipc_clients: list[Ipc]) -> FolderEventHandler:
    return FolderEventHandler(tmp_path, "10.0.0.1", ipc_clients)


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
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        sent.append((coordinated, object_id))

    monkeypatch.setattr(ipc0, "send", fake_send)
    monkeypatch.setattr(ipc1, "send", fake_send)
    handler = _handler(tmp_path, [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(large)))
    handler.flush()
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
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        sent.append((0, coordinated, object_id))

    def fake_send1(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        sent.append((1, coordinated, object_id))

    monkeypatch.setattr(ipc0, "send", fake_send0)
    monkeypatch.setattr(ipc1, "send", fake_send1)
    handler = _handler(tmp_path, [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(small)))
    handler.flush()
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
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        pairs.append(0)

    def fake_send1(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        pairs.append(1)

    monkeypatch.setattr(ipc0, "send", fake_send0)
    monkeypatch.setattr(ipc1, "send", fake_send1)
    handler = _handler(tmp_path, [ipc0, ipc1])
    handler.on_any_event(FileCreatedEvent(src_path=str(a)))
    handler.flush()
    handler.on_any_event(FileCreatedEvent(src_path=str(b)))
    handler.flush()
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
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        sent.append(coordinated)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(
        FileMovedEvent(src_path=str(tmp_path / "a.txt"), dest_path=str(dest)),
    )
    handler.flush()
    assert sent == [False]


def test_handler_sends_directory_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, bool]] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        calls.append((command, relative_path, is_directory))

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(
        DirCreatedEvent(src_path=str(tmp_path / "folder" / "sub")),
    )
    handler.flush()
    assert calls == [("created", "folder/sub", True)]


def test_handler_sends_nested_file_relative_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    nested = tmp_path / "sub" / "file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"data")

    calls: list[str] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        calls.append(relative_path)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(FileCreatedEvent(src_path=str(nested)))
    handler.flush()
    assert calls == ["sub/file.txt"]


def test_handler_sends_directory_deleted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, bool]] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        calls.append((command, relative_path, is_directory))

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(DirDeletedEvent(src_path=str(tmp_path / "gone")))
    handler.flush()
    assert calls == [("deleted", "gone", True)]


def test_handler_sends_directory_moved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, str, bool]] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        calls.append((command, relative_path, dest_relative_path, is_directory))

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(
        DirMovedEvent(
            src_path=str(tmp_path / "old"),
            dest_path=str(tmp_path / "new"),
        ),
    )
    handler.flush()
    assert calls == [("moved", "old", "new", True)]


def test_handler_ignores_closed_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sent: list[bool] = []
    ipc = Ipc("/tmp/ignored.sock")

    def fake_send(
        command: str,
        data: bytes = b"",
        target_ip: str = "",
        object_id: int = 0,
        coordinated: bool = True,
        relative_path: str = "",
        dest_relative_path: str = "",
        is_directory: bool = False,
    ) -> None:
        sent.append(coordinated)

    monkeypatch.setattr(ipc, "send", fake_send)
    handler = _handler(tmp_path, [ipc])
    handler.on_any_event(FileClosedEvent(src_path=str(tmp_path / "a.txt")))
    handler.flush()
    assert sent == []
