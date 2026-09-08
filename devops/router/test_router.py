"""Tests for the devops UDP router CLI and logger."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

DEVOPS = Path(__file__).resolve().parents[1]
ROUTER = DEVOPS / "router"
sys.path.insert(0, str(DEVOPS))
sys.path.insert(0, str(ROUTER))

from config import RouterConfig  # noqa: E402
from router import (  # noqa: E402
    config_from_args,
    configure_logging,
    create_parser,
    resolve_log_file,
)


def test_help_lists_logging_flags() -> None:
    help_text = create_parser().format_help()
    assert "--verbose" in help_text
    assert "--log-file" in help_text


def test_cli_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PACKET_LOSS", "0.03")
    monkeypatch.setenv("BIT_FLIP", "0.03")
    monkeypatch.setenv("RX_HOST", "rx_machine")
    args = create_parser().parse_args(
        [
            "--packet-loss",
            "0.5",
            "--bit-flip",
            "0.0",
            "--rx-host",
            "10.0.0.8",
            "--verbose",
        ]
    )
    config = config_from_args(args)
    assert config.packet_loss == 0.5
    assert config.bit_flip == 0.0
    assert config.rx_host == "10.0.0.8"
    assert args.verbose is True


def test_invalid_packet_loss_is_rejected() -> None:
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--packet-loss", "1.5"])


def test_log_file_flag_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIFLOW_LOG_FILE", "/tmp/from-env.log")
    args = create_parser().parse_args(["--log-file", "/tmp/from-cli.log"])
    assert resolve_log_file(args) == "/tmp/from-cli.log"


def test_log_file_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIFLOW_LOG_FILE", "/tmp/from-env.log")
    args = create_parser().parse_args([])
    assert resolve_log_file(args) == "/tmp/from-env.log"


def test_configure_logging_writes_file(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "router.log"
    configure_logging(verbose=True, log_file=str(log_path))
    logging.getLogger("router").debug("hello-debug")
    text = log_path.read_text()
    assert "[DEBUG] hello-debug" in text


def test_router_config_defaults() -> None:
    config = RouterConfig()
    config.validate()
    assert config.ports == [9000, 9001, 9002]


@pytest.mark.parametrize("values", [{"start_port": 0}, {"start_port": 65534}, {"packet_loss": float("nan")}, {"stats_interval_sec": -1}])
def test_invalid_router_configuration(values):
    with pytest.raises(ValueError):
        RouterConfig(**values).validate()
