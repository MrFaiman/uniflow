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

    # First scan - the folder is empty
    assert monitor.get_changed_files() == []

    # Create a new file
    new_file = tmp_path / "new_file.txt"
    new_file.write_text("Hello")

    # The new file should be detected
    changed_files = monitor.get_changed_files()

    assert new_file in changed_files

    # Nothing changed since the last scan
    assert monitor.get_changed_files() == []


def test_get_modified_file(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("Hello")

    monitor = FileMonitor(tmp_path)

    # First scan remembers the existing file
    monitor.get_changed_files()

    # Modify the file
    file.write_text("Hello World")

    # The modified file should be detected
    changed_files = monitor.get_changed_files()

    assert file in changed_files

def test_small_file(tmp_path):
    file = tmp_path / "small_file.txt"

    # Create a file just under 10 MB
    file.write_bytes(b"0" * (10 * 1024 * 1024 - 1))

    monitor = FileMonitor(tmp_path)

    assert monitor.is_small_file(file) is True


def test_large_file(tmp_path):
    file = tmp_path / "large_file.txt"

    # Create a file exactly 10 MB
    file.write_bytes(b"0" * (10 * 1024 * 1024))

    monitor = FileMonitor(tmp_path)

    assert monitor.is_small_file(file) is False