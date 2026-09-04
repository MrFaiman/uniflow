# Uniflow

Uniflow is a one-way reliable file-transfer project for the **team-of-three** assignment.

## Required runtime architecture

```text
TX machine
┌────────────────────────────────────────────────────────────┐
│ File Monitor (Python)                                     │
│   ├─ UDS -> Sender 0 (C++) -> UDP 9000 ─┐                │
│   ├─ UDS -> Sender 1 (C++) -> UDP 9001 ─┼─> Router       │
│   └─ UDS -> Sender 2 (C++) -> UDP 9002 ─┘                │
└────────────────────────────────────────────────────────────┘
                                              one-way only
RX machine
┌────────────────────────────────────────────────────────────┐
│ Router -> UDP 9000 -> Receiver 0 (C++) ─┐                 │
│ Router -> UDP 9001 -> Receiver 1 (C++) ─┼─ UDS ->         │
│ Router -> UDP 9002 -> Receiver 2 (C++) ─┘  Session Manager│
│                                              (Python)      │
└────────────────────────────────────────────────────────────┘
```

There is **no RX -> TX network ACK channel**.

## Small files

A file smaller than 10 MiB uses exactly one Sender/Receiver pair. Up to three small files can use the three pairs concurrently.

## Large files

A file from 10 MiB through 1 GiB is RaptorQ-encoded in 1 MiB blocks. Encoded packets from the same file are distributed across Sender 0, 1 and 2. All three C++ Sender processes therefore transmit data belonging to the same file.

The Python File Monitor reads the file block-by-block; it does not load a 1 GiB file into RAM.

## Reliability

Each packet contains:

- file ID
- file path
- original file size
- original SHA-256
- block index / offset
- RaptorQ encoded data
- target pair
- per-packet SHA-256

The router may drop, corrupt or misroute UDP packets.

- **Loss:** RaptorQ repair packets recover missing encoded data within the configured tolerance.
- **Bit flip:** the Session Manager rejects packets whose packet SHA-256 changed.
- **Misrouting:** every Receiver forwards every valid Protobuf packet to the same Session Manager. The Session Manager groups by file/block metadata, so the physical Receiver port does not decide ownership.
- **Final integrity:** the reconstructed file is moved into place only when its SHA-256 matches the original SHA-256.

## Languages

Runtime on both endpoint machines includes both required languages:

- Python: File Monitor / Session Manager
- C++: Sender / Receiver workers

The old `go/` and `python/uniflow/` directories are legacy code and are not used by the Docker runtime after this fix.

## Main source directories

```text
proto/transfer.proto              shared Protobuf FilePacket
python/client/                    File Monitor + Session Manager
cpp/                              C++ Sender + Receiver

devops/router/                    fault-injection router
devops/docker-compose.yaml        complete local topology
```

## Build and run

From `devops/`:

```bash
docker compose up --build
```

Expected TX processes/logs:

```text
File Monitor (Python)
Sender 0 (C++)
Sender 1 (C++)
Sender 2 (C++)
```

Expected RX processes/logs:

```text
Session Manager (Python)
Receiver 0 (C++)
Receiver 1 (C++)
Receiver 2 (C++)
```

Put a file inside:

```text
devops/data/out/
```

A valid reconstructed copy appears under the same relative path in:

```text
devops/data/in/
```

## Automated end-to-end tests

Always prove the zero-fault path first:

```bash
cd devops
./run-transfer-test.sh --chaos none
```

Then test faults individually and together:

```bash
./run-transfer-test.sh --chaos loss
./run-transfer-test.sh --chaos flip
./run-transfer-test.sh --chaos misroute
./run-transfer-test.sh --chaos mild
```

The test suite includes an empty file, tiny, 1 KiB, 5 MiB, just-below-10 MiB, just-above-10 MiB, 30 MiB, nested-path files, and a modification test.

For the explicit 1 GiB requirement:

```bash
./run-transfer-test.sh --chaos none --include-1gb --timeout 7200
```

The verifier checks both file size and SHA-256.

## Fault settings

Docker Compose accepts:

```text
PACKET_LOSS
BIT_FLIP
MISROUTING
RANDOM_SEED
UNIFLOW_FEC_REPAIR_PERCENT
UNIFLOW_SEND_RATE_MBPS
```

`UNIFLOW_SEND_RATE_MBPS` is deliberate UDP pacing to avoid creating accidental local kernel/router packet loss before the simulated router fault logic. It is not used for synchronization.

## Local Python tests

```bash
bash scripts/generate-proto.sh python
cd python/client
uv sync --all-groups
uv run ruff check src tests
uv run pytest
```

## Local C++ build

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --parallel
```

## Protobuf

`proto/transfer.proto` is the shared schema for both IPC and UDP messages. Do not hand-edit generated `transfer_pb2.py` or `transfer.pb.cc/.h` files.

Generate Python bindings with:

```bash
bash scripts/generate-proto.sh python
```

The C++ build generates its bindings automatically through CMake.
