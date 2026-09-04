# Uniflow Docker environment

Run all commands from this directory.

## Start

```bash
docker compose up --build
```

The TX container runs one Python File Monitor plus three independent C++ Sender processes. The RX container runs one Python Session Manager plus three independent C++ Receiver processes.

Ports are 9000, 9001 and 9002. Local IPC uses Unix Domain Sockets. Network traffic is UDP and only flows TX -> Router -> RX.

## Zero-fault proof

```bash
./run-transfer-test.sh --chaos none
```

## Fault-injection proof

```bash
./run-transfer-test.sh --chaos mild
```

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
docker compose top tx_machine
docker compose top rx_machine
docker compose logs tx_machine
docker compose logs rx_machine
docker compose logs router
```

You should see three Sender workers and three Receiver workers, not merely `UNIFLOW_WORKERS=3` in configuration.
