import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "schemas" / "message.proto").is_file():
            return parent
    raise RuntimeError("could not find repo root")


def pytest_configure(config: pytest.Config) -> None:
    script = _repo_root() / "scripts" / "generate-proto.sh"
    subprocess.run(["bash", str(script), "python"], check=True)
