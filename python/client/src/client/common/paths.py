from pathlib import Path, PurePosixPath


def relative_path_from_root(file_path: Path, root: Path) -> str:
    root = root.resolve()
    file_path = file_path.resolve()
    return file_path.relative_to(root).as_posix()


def normalize_relative_path(value: str) -> Path:
    if not value or "\x00" in value:
        raise ValueError("empty or invalid relative path")

    value = value.replace("\\", "/")
    path = PurePosixPath(value)

    if path.is_absolute():
        raise ValueError("absolute paths are not allowed")

    parts = [part for part in path.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("path traversal is not allowed")

    return Path(*parts)


def safe_join(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    normalized = normalize_relative_path(relative_path)
    result = (root / normalized).resolve()
    result.relative_to(root)
    return result
