# Uniflow Docker environment

Run all commands from this directory.

## Profiles

| Profile | Services |
|---------|----------|
| `all` | router + tx_machine + rx_machine |
| `tx` | router + tx_machine |
| `rx` | rx_machine |
| `tx-external` | tx_machine only (point `ROUTER_HOST` at an external router) |

## Start

```bash
docker compose --profile all up --build
```

The TX container runs one Python File Monitor plus three independent C++ Sender processes. The RX container runs one Python Session Manager plus three independent C++ Receiver processes.

Ports are 9000, 9001 and 9002. Local IPC uses Unix Domain Sockets. Network traffic is UDP and only flows TX -> Router -> RX.

Build notes:

- Images use BuildKit caches and a multi-stage Dockerfile (GCC 14/C++20 workers and uv-managed Python on Debian Trixie).
- Prefer `DOCKER_BUILDKIT=1` (enabled by default in recent Docker Desktop).

## Zero-fault proof

```bash
./run-transfer-test.sh --chaos none
```

## Fault-injection proof

```bash
./run-transfer-test.sh --chaos mild
```

For a bounded suite including small, empty and multi-path files, add `--smoke`.
The script clears its fixture directories before running. Set
`UNIFLOW_TEST_OUT_DIR` and `UNIFLOW_TEST_IN_DIR` to dedicated absolute paths
to keep manual deployment data separate. See the root README for all modes,
two-PC startup ordering, defaults, and operational limits.

## 1 GiB proof

```bash
./run-transfer-test.sh --chaos none --include-1gb --timeout 7200
```

## Manual test

1. Start Compose.
2. Copy a file into `data/out/`.
3. Wait for `COMPLETE: <name> - HASH OK` in the RX logs.
4. Compare `data/out/<path>` with `data/in/<path>` using SHA-256.

```bash
sha256sum data/out/example.bin data/in/example.bin
```

## Useful runtime evidence

```bash
docker compose --profile all top tx_machine
docker compose --profile all top rx_machine
docker compose --profile all logs tx_machine
docker compose --profile all logs rx_machine
docker compose --profile all logs router
docker compose --profile all ps
```

You should see three Sender workers and three Receiver workers, not merely `UNIFLOW_WORKERS=3` in configuration.
