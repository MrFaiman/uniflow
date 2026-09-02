from client.file_monitor.monitor import FileMonitor


def test_get_files(tmp_path):
    first_file = tmp_path / "first.txt"
    second_file = tmp_path / "second.txt"
    folder = tmp_path / "another_folder"

    first_file.write_text("Hello")
    second_file.write_text("World")
    folder.mkdir()

    monitor = FileMonitor(tmp_path)

    files = monitor.get_files()

    assert first_file in files
    assert second_file in files
    assert folder not in files


def test_get_new_file(tmp_path):
    monitor = FileMonitor(tmp_path)

    assert monitor.get_changed_files() == []

    file = tmp_path / "new_file.txt"
    file.write_text("Hello")

    changed_files = monitor.get_changed_files()

    assert changed_files == [file]

    assert monitor.get_changed_files() == []


def test_get_modified_file(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("Hello")

    monitor = FileMonitor(tmp_path)

    monitor.get_changed_files()

    file.write_text("Hello again")

    changed_files = monitor.get_changed_files()

    assert changed_files == [file]