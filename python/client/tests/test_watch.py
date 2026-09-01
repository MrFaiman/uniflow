import pytest
from watchdog.events import (
    DirCreatedEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileMovedEvent,
)

from client.watch import FolderEventHandler


def test_handler_sends_file_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        "client.watch.Ipc.send",
        lambda command, data=b"": sent.append((command, data)),
    )
    handler = FolderEventHandler("10.0.0.1")
    handler.on_any_event(FileCreatedEvent(src_path="/tmp/folder/a.txt"))
    assert sent == [("created", b"/tmp/folder/a.txt")]


def test_handler_sends_moved_src_and_dest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        "client.watch.Ipc.send",
        lambda command, data=b"": sent.append((command, data)),
    )
    handler = FolderEventHandler("10.0.0.1")
    handler.on_any_event(
        FileMovedEvent(src_path="/tmp/a.txt", dest_path="/tmp/b.txt")
    )
    assert sent == [("moved", b"/tmp/a.txt\n/tmp/b.txt")]


def test_handler_ignores_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        "client.watch.Ipc.send",
        lambda command, data=b"": sent.append((command, data)),
    )
    handler = FolderEventHandler("10.0.0.1")
    handler.on_any_event(DirCreatedEvent(src_path="/tmp/folder/sub"))
    assert sent == []


def test_handler_ignores_closed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        "client.watch.Ipc.send",
        lambda command, data=b"": sent.append((command, data)),
    )
    handler = FolderEventHandler("10.0.0.1")
    handler.on_any_event(FileClosedEvent(src_path="/tmp/folder/a.txt"))
    assert sent == []
