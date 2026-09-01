from hashlib import sha256
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


def calculate_sha256(file_path: Path) -> str:
    file_hash = sha256()

    with file_path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            file_hash.update(chunk)

    return file_hash.hexdigest()