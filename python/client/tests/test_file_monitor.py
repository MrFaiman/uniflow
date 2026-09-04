from client.file_monitor.monitor import FileMonitor


def scan_until_changed(monitor: FileMonitor):
    monitor.get_changed_files()
    return monitor.get_changed_files()


def test_get_files_is_recursive(tmp_path):
    first_file = tmp_path / "first.txt"
    nested_file = tmp_path / "nested" / "second.txt"
    nested_file.parent.mkdir()
    first_file.write_text("Hello")
    nested_file.write_text("World")

    monitor = FileMonitor(tmp_path)
    files = monitor.get_files()

    assert first_file in files
    assert nested_file in files


def test_new_file_must_be_stable_before_transfer(tmp_path):
    monitor = FileMonitor(tmp_path)
    file = tmp_path / "new_file.txt"
    file.write_text("Hello")

    assert monitor.get_changed_files() == []
    assert monitor.get_changed_files() == [file]
    assert monitor.get_changed_files() == []


def test_modified_file_is_detected_again(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("Hello")
    monitor = FileMonitor(tmp_path)

    assert scan_until_changed(monitor) == [file]

    file.write_text("Hello again")
    assert monitor.get_changed_files() == []
    assert monitor.get_changed_files() == [file]


def test_failed_transfer_is_retried(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("Hello")
    monitor = FileMonitor(tmp_path)

    assert scan_until_changed(monitor) == [file]
    monitor.mark_failed(file)

    assert monitor.get_changed_files() == []
    assert monitor.get_changed_files() == [file]
