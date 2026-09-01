from hashlib import sha256

from client.common.hash_utils import calculate_sha256


def test_calculate_sha256(tmp_path):
    file_path = tmp_path / "hello.txt"
    data = b"Hello World"

    file_path.write_bytes(data)

    expected_hash = sha256(data).hexdigest()
    actual_hash = calculate_sha256(file_path)

    assert actual_hash == expected_hash