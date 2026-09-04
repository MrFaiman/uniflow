import pytest

from client.common.paths import normalize_relative_path, safe_join


def test_nested_relative_path_is_preserved(tmp_path):
    normalized = normalize_relative_path("nested/sub/file.bin")
    assert normalized.as_posix() == "nested/sub/file.bin"
    assert safe_join(tmp_path, "nested/sub/file.bin") == (
        tmp_path / "nested" / "sub" / "file.bin"
    ).resolve()


@pytest.mark.parametrize("value", ["../secret", "/etc/passwd", "a/../../b", ""])
def test_unsafe_paths_are_rejected(value, tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, value)
