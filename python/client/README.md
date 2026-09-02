# Uniflow — Python File Monitor & Session Manager

> Python side of the Uniflow distributed file-transfer project.

This branch contains the two Python components of Uniflow:

- **File Monitor (TX)** — watches the outgoing folder, prepares files for reliable transfer, and hands Protobuf packets to the local Sender through Unix Domain Sockets.
- **Session Manager (RX)** — receives Protobuf packets from the local Receiver, validates and reconstructs files, and verifies the final SHA-256 hash.

The **Sender**, **Receiver**, and **Router** are separate components owned by other parts of the team.

---

## Architecture

The system is designed to run in three Docker containers:

```text
┌────────────────────── TX CONTAINER ──────────────────────┐
│                                                         │
│  /data/out                                              │
│      │                                                  │
│      ▼                                                  │
│  File Monitor (Python)                                  │
│      │                                                  │
│      │ Unix Domain Socket                              │
│      │ /tmp/proto_ipc.sock                             │
│      ▼                                                  │
│  Sender (team component)                               │
│      │                                                  │
└──────┼──────────────────────────────────────────────────┘
       │
       │ Network packets
       ▼
┌──────────────────── ROUTER CONTAINER ────────────────────┐
│                                                         │
│  Simulates packet loss, bit flips, and misrouting       │
│                                                         │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────── RX CONTAINER ──────────────────────┐
│                                                         │
│  Receiver (team component)                              │
│      │                                                  │
│      │ Unix Domain Socket                              │
│      │ /tmp/proto_ipc.sock                             │
│      ▼                                                  │
│  Session Manager (Python)                               │
│      │                                                  │
│      ▼                                                  │
│  /data/in                                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

The TX and RX containers can both use `/tmp/proto_ipc.sock` because each container has its own filesystem namespace.

---

# TX — File Monitor

## What it does

The File Monitor continuously watches the outgoing directory for:

- newly created files
- modified files

When a changed file is found, it:

1. Calculates the file's SHA-256 hash.
2. Reads the file in blocks instead of loading the whole file into memory.
3. Encodes blocks with RaptorQ.
4. Builds Protobuf `FilePacket` messages.
5. Chooses the logical Sender/Receiver route.
6. Calculates a per-packet SHA-256 hash.
7. Serializes the packet with Protobuf.
8. Sends it to the local Sender over one Unix Domain Socket.

---

## Small and large files

### Small file

A file smaller than **10 MB** uses one route for the entire transfer.

Example:

```text
file A
  ├── packet 0 → route 1
  ├── packet 1 → route 1
  ├── packet 2 → route 1
  └── packet 3 → route 1
```

Different small files use round-robin selection:

```text
file A → route 0
file B → route 1
file C → route 2
file D → route 0
```

The round-robin implementation is a Python generator.

### Large file

A file of **10 MB or more** is distributed across all configured workers:

```text
packet 0 → route 0
packet 1 → route 1
packet 2 → route 2
packet 3 → route 0
packet 4 → route 1
packet 5 → route 2
...
```

The route is stored in:

```protobuf
target_receiver
```

The Python File Monitor still sends every packet through the same local UDS connection. The Sender uses `target_receiver` to choose the correct network worker/port.

---

# RX — Session Manager

## What it does

The Session Manager is the central Python process on the receiving side.

It:

1. Listens on one Unix Domain Socket.
2. Accepts multiple Receiver connections.
3. Reads framed Protobuf messages safely from stream sockets.
4. Parses each `FilePacket`.
5. Rejects invalid or corrupted packets.
6. Groups packets by `file_id`.
7. Groups RaptorQ data by `block_index`.
8. Ignores duplicate packets.
9. Reconstructs blocks with RaptorQ.
10. Writes decoded blocks directly to a temporary file.
11. Verifies the completed file with SHA-256.
12. Moves the temporary file to its final filename only when the hash matches.

---

## Why one RX socket works

All Receiver workers can connect to the same socket:

```text
Receiver worker 0 ─┐
Receiver worker 1 ─┼──> /tmp/proto_ipc.sock ──> Session Manager
Receiver worker 2 ─┘
```

Each accepted connection is handled independently and places received messages into a shared queue.

Only the main Session Manager flow changes file-transfer state, which keeps the design simple and avoids unnecessary locking.

---

# Reliability

## Packet loss

RaptorQ adds repair data to each encoded block.

If network packets are lost, the Session Manager may still reconstruct the original block from the remaining RaptorQ packets.

Current encoder settings:

```text
Block size:      1 MB
RaptorQ symbol:  1400 bytes
Repair packets:  10
```

`REPAIR_PACKETS` may need to be tuned after testing against the real router's packet-loss behavior.

---

## Bit flips

Each `FilePacket` contains a packet hash.

TX:

```text
finished FilePacket
      ↓
SHA-256
      ↓
packet_hash
```

RX recalculates the same hash.

If the hashes differ:

```text
packet corrupted
      ↓
discard packet
      ↓
RaptorQ treats it effectively as missing data
```

The corrupted packet is never intentionally fed into the decoder.

---

## Final file integrity

The original TX file SHA-256 is stored in:

```protobuf
file_hash
```

After every block has been reconstructed, RX calculates the SHA-256 of the completed temporary file.

```text
received hash == original hash
           ↓
       HASH OK
           ↓
temporary .part file
           ↓
final received file
```

If the hash does not match, the transfer is reported as failed.

---

## Misrouting

The router may send a packet through a different Receiver worker than originally intended.

This does not prevent reconstruction.

The Session Manager groups packets using transfer metadata such as:

```text
file_id
block_index
packet_index
```

rather than depending on which local Receiver connection delivered the packet.

A valid packet that reaches the RX machine can therefore still contribute to reconstruction.

---

# Protobuf

Shared schema:

```text
proto/transfer.proto
```

Python generated file:

```text
python/client/src/client/transfer_pb2.py
```

Do **not** manually edit `transfer_pb2.py`.

When `transfer.proto` changes, regenerate it.

From:

```text
python/client
```

run:

```bash
uv run python -m grpc_tools.protoc \
  -I../../proto \
  --python_out=src/client \
  ../../proto/transfer.proto
```

The Sender and Receiver must generate their own language-specific Protobuf code from the **same** `transfer.proto`.

---

# IPC framing

Unix Domain Sockets use `SOCK_STREAM`, so message boundaries are not preserved automatically.

Every IPC message therefore uses this format:

```text
┌────────────────────────────────┐
│ 4-byte unsigned big-endian size│
├────────────────────────────────┤
│ serialized Protobuf FilePacket │
└────────────────────────────────┘
```

Python sends the length with:

```text
!I
```

which means a 4-byte unsigned integer in network/big-endian byte order.

The receiving side must read:

1. exactly 4 bytes
2. decode the message length
3. read exactly that many bytes
4. parse the Protobuf message

---

# Docker configuration

The provided Compose setup uses common environment variables:

```yaml
PORT: "9000"
UNIFLOW_WORKERS: "3"
UNIFLOW_SKIP_BUILD: "1"
IPC_SOCKET_PATH: /tmp/proto_ipc.sock
```

TX also uses:

```yaml
UNIFLOW_WATCH_POLLING: "1"
```

RX uses:

```yaml
RECEIVE_DIR: /data/in
```

---

## Python environment variables

| Variable                | Default               | Used by         |
| ----------------------- | --------------------- | --------------- |
| `IPC_SOCKET_PATH`       | `/tmp/proto_ipc.sock` | TX + RX         |
| `UNIFLOW_WORKERS`       | `3`                   | File Monitor    |
| `UNIFLOW_WATCH_POLLING` | `1`                   | File Monitor    |
| `UNIFLOW_WATCH_DIR`     | `/data/out`           | File Monitor    |
| `RECEIVE_DIR`           | `/data/in`            | Session Manager |

`PORT` is part of the shared container configuration but is handled by the network Sender/Receiver side rather than the Python components.

---

# Docker filesystem

The Compose volumes expose real host folders inside the containers.

TX:

```yaml
volumes:
  - ./data/out:/data/out
```

Meaning:

```text
host ./data/out
      ↕
container /data/out
```

RX:

```yaml
volumes:
  - ./data/in:/data/in
```

Meaning:

```text
container /data/in
      ↕
host ./data/in
```

Put a file in:

```text
devops/data/out
```

and, after a successful complete transfer, the reconstructed file should appear in:

```text
devops/data/in
```

depending on the working directory used to launch Docker Compose.

---

# Python project structure

```text
python/client/
├── src/client/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── hash_utils.py
│   │   ├── ipc.py
│   │   ├── packet_hash.py
│   │   └── round_robin.py
│   │
│   ├── file_monitor/
│   │   ├── __init__.py
│   │   ├── monitor.py
│   │   ├── packet_router.py
│   │   ├── raptorq_encoder.py
│   │   ├── transfer.py
│   │   └── run.py
│   │
│   ├── session_manager/
│   │   ├── __init__.py
│   │   ├── decoder.py
│   │   ├── file_session.py
│   │   ├── listener.py
│   │   ├── manager.py
│   │   ├── packet_validator.py
│   │   └── run.py
│   │
│   └── transfer_pb2.py
│
└── tests/
```

---

# Main Python files

## Common

### `hash_utils.py`

Calculates SHA-256 by reading files in chunks instead of loading the complete file into RAM.

### `packet_hash.py`

Calculates the integrity hash of a Protobuf `FilePacket`.

### `ipc.py`

Contains the shared Unix Domain Socket helpers and outgoing message framing.

### `round_robin.py`

Generator used to rotate small-file transfers across the configured routes.

---

## File Monitor

### `monitor.py`

Finds files and detects creation/modification.

### `packet_router.py`

Implements the `< 10 MB` vs `>= 10 MB` routing rules.

### `raptorq_encoder.py`

Reads files in blocks and produces RaptorQ-backed Protobuf packets.

### `transfer.py`

Final TX pipeline:

```text
RaptorQ packet
    ↓
route
    ↓
packet hash
    ↓
Protobuf serialization
    ↓
UDS
```

### `run.py`

Docker/runtime entry point for the File Monitor.

---

## Session Manager

### `listener.py`

Handles the Unix Domain Socket server, exact stream reads, multiple Receiver connections, and queueing messages.

### `packet_validator.py`

Checks packet structure, sizes, indexes, bounds, and packet SHA-256.

### `decoder.py`

Owns the RaptorQ decoding step.

### `file_session.py`

Stores the state of one active file transfer:

- file metadata
- active block decoders
- duplicate packet indexes
- completed blocks
- temporary output path

### `manager.py`

Coordinates packet processing and final file completion.

### `run.py`

Docker/runtime entry point for the Session Manager.

---

# Development setup

The project requires Python 3.13+ and uses `uv`.

From:

```text
python/client
```

install dependencies:

```bash
uv sync --dev
```

If using the separate WSL environment used during development:

```bash
export UV_PROJECT_ENVIRONMENT=.venv-wsl
uv sync --dev
```

---

# Run checks

From:

```text
python/client
```

run:

```bash
uv run ruff check . --fix
uv run ruff check .
uv run pytest
```

Expected result:

```text
All checks passed!
all tests passed
```

Do not push a branch with failing Ruff or pytest checks.

---

# Run the Python processes manually

These commands are useful for debugging even when Docker normally starts the components.

## Session Manager

Environment defaults already match the Docker configuration:

```bash
uv run python -m client.session_manager.run
```

It listens on:

```text
/tmp/proto_ipc.sock
```

and writes completed files to:

```text
/data/in
```

You can override them:

```bash
IPC_SOCKET_PATH=/tmp/test.sock \
RECEIVE_DIR=/tmp/uniflow-in \
uv run python -m client.session_manager.run
```

---

## File Monitor

The local Sender must create/listen on the configured UDS before the File Monitor can connect.

Run:

```bash
uv run python -m client.file_monitor.run
```

Defaults:

```text
watch directory: /data/out
IPC socket:      /tmp/proto_ipc.sock
workers:         3
poll interval:   1 second
```

Override for local testing:

```bash
IPC_SOCKET_PATH=/tmp/test.sock \
UNIFLOW_WATCH_DIR=/tmp/uniflow-out \
UNIFLOW_WORKERS=3 \
UNIFLOW_WATCH_POLLING=1 \
uv run python -m client.file_monitor.run
```

---

# Run with Docker Compose

From the directory containing the Compose file:

```bash
docker compose up --build
```

The intended containers are:

```text
router
rx_machine
tx_machine
```

The container launcher must start:

### TX container

```text
Python File Monitor
+
Sender
```

### RX container

```text
Receiver
+
Python Session Manager
```

The current Compose commands are:

```yaml
tx_machine:
  command: ["uniflow", "send", "/data/out", "router"]

rx_machine:
  command: ["uniflow", "receive", "/data/in"]
```

Therefore the `uniflow` launcher/entrypoint must ensure the matching Python process is also running inside each container.

The Python code itself does not start the Go Sender or Receiver.

---

# End-to-end test

Start the containers:

```bash
docker compose up --build
```

Then add a test file to the host TX directory:

```text
./data/out/example.txt
```

Expected flow:

```text
example.txt
   ↓
File Monitor
   ↓
Sender
   ↓
Router
   ↓
Receiver
   ↓
Session Manager
   ↓
./data/in/example.txt
```

The Session Manager should report:

```text
COMPLETE: example.txt - HASH OK
```

Verify the files match.

Linux/macOS:

```bash
sha256sum ./data/out/example.txt
sha256sum ./data/in/example.txt
```

The hashes must be identical.

---

# Test fault handling

The router configuration currently includes:

```yaml
PACKET_LOSS: "0.03"
BIT_FLIP: "0.03"
MISROUTING: "0.03"
```

That means the final team integration test should verify transfers while the router is actively introducing:

- packet loss
- corrupted data
- misrouting

Expected behavior:

```text
packet loss
   ↓
RaptorQ repair data

bit flip
   ↓
packet hash mismatch
   ↓
discard corrupted packet
   ↓
RaptorQ may recover it as missing data

misrouting
   ↓
packet still reaches RX
   ↓
Session Manager groups by transfer metadata
```

---

# Tests

The Python test suite covers the major pieces independently:

```text
File Monitor
SHA-256
Unix Domain Sockets
packet routing
Protobuf
RaptorQ
round robin
Session Manager
Session Manager listener
transfer pipeline
Docker runtime configuration
```

Run all tests with:

```bash
uv run pytest
```

---

# Important integration contract

The Sender and Receiver teammates must agree with the Python side on all of the following:

### 1. Protobuf

Use the latest:

```text
proto/transfer.proto
```

### 2. IPC socket

```text
/tmp/proto_ipc.sock
```

unless `IPC_SOCKET_PATH` overrides it.

### 3. IPC framing

```text
4-byte unsigned big-endian message length
+
serialized FilePacket
```

### 4. Routing

`FilePacket.target_receiver` contains the logical route/worker selected by the File Monitor.

### 5. One-way behavior

There is no application-level ACK from RX back to TX.

### 6. File locations

TX:

```text
/data/out
```

RX:

```text
/data/in
```

---

# Current responsibility boundary

## Python side

Implemented here:

```text
File Monitor
Session Manager
RaptorQ encode/decode
hashing
packet validation
routing decisions
Protobuf creation/parsing
local UDS IPC
file reconstruction
```

## Other team components

Not implemented by this Python branch:

```text
Sender
Receiver
Router
Docker orchestration/launcher
```

---

# Before merging

Run:

```bash
uv run ruff check .
uv run pytest
```

Then perform the real Docker integration test:

```text
data/out
   ↓
TX container
   ↓
router
   ↓
RX container
   ↓
data/in
```

A branch is ready for final integration when the received file is reconstructed and the Session Manager reports:

```text
HASH OK
```

---

## Summary

The Python side is designed around four principles:

1. **Simple responsibilities** — monitoring, routing, decoding, validation, and session state live in separate small modules.
2. **Streaming** — large files are processed in blocks instead of being held entirely in memory.
3. **Reliability** — RaptorQ, per-packet integrity, and final SHA-256 verification protect transfers over the unreliable one-way network.
4. **Container-first configuration** — paths, worker count, polling, and IPC location are controlled through environment variables rather than Windows-specific paths.
