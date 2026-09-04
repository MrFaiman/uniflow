<div align="center">

# Uniflow

### Reliable one-way file synchronization over three parallel UDP paths

[![CI](https://github.com/MrFaiman/uniflow/actions/workflows/ci.yml/badge.svg)](https://github.com/MrFaiman/uniflow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![C++](https://img.shields.io/badge/C%2B%2B-17-00599C?logo=cplusplus&logoColor=white)
![Protocol Buffers](https://img.shields.io/badge/Protocol-Buffers-4285F4)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

**Uniflow** continuously mirrors files from a TX machine to an RX machine through a strictly one-way network.  
It is designed to keep working when the router drops packets, corrupts packets, or sends packets to the wrong receiver.

</div>

---

## Table of contents

- [Overview](#overview)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [Process model](#process-model)
- [How transfers work](#how-transfers-work)
- [Reliability model](#reliability-model)
- [File lifecycle](#file-lifecycle)
- [Quick start — one computer](#quick-start--one-computer)
- [Run on two physical computers](#run-on-two-physical-computers)
- [Automated end-to-end testing](#automated-end-to-end-testing)
- [Development and unit tests](#development-and-unit-tests)
- [Configuration](#configuration)
- [Repository structure](#repository-structure)
- [Assignment requirement coverage](#assignment-requirement-coverage)
- [Security and integrity notes](#security-and-integrity-notes)
- [Troubleshooting](#troubleshooting)
- [Team workflow](#team-workflow)

---

## Overview

Uniflow is a fault-tolerant file-transfer system built around a **three-path TX/RX architecture**.

The TX side continuously watches a source folder. New files, modified files, and deletions are propagated toward the RX side. The network path is intentionally one-way: the RX side never sends acknowledgements or retransmission requests back to TX.

Reliability is therefore handled entirely on the forward path using:

- **RaptorQ forward error correction** for packet loss,
- **per-packet SHA-256** for corruption detection,
- **final file SHA-256** before a reconstructed file is accepted,
- **three independent Sender/Receiver paths**,
- centralized reconstruction in the RX **Session Manager**,
- version-aware handling of modifications and deletions.

The Docker development environment also contains a fault-injection router that can simulate:

- packet loss,
- bit flips,
- packet misrouting.

> **Important:** Uniflow is an academic fault-tolerance project. It provides integrity checks, but it does not provide encryption, peer authentication, or production-grade access control.

---

## Highlights

| Capability             | Behavior                                                                      |
| ---------------------- | ----------------------------------------------------------------------------- |
| Continuous monitoring  | Watches the TX folder until the process is stopped                            |
| New files              | Automatically transferred                                                     |
| Modified files         | Automatically transferred again as a newer version                            |
| Deleted files          | RX copy is removed using a one-way `DELETE` control message                   |
| Small files            | One Sender/Receiver pair per file                                             |
| Concurrent small files | Up to three files can use different pairs simultaneously                      |
| Large files            | Encoded in blocks and distributed across all three paths                      |
| Maximum file size      | 1 GiB                                                                         |
| Packet loss            | Recovered with RaptorQ repair packets within available FEC tolerance          |
| Bit corruption         | Rejected using packet SHA-256                                                 |
| Misrouting             | Tolerated because every Receiver forwards packets to the same Session Manager |
| Final integrity        | File is published only after the final SHA-256 matches                        |
| Reverse channel        | None — no RX → TX ACK path                                                    |
| IPC                    | Unix Domain Sockets                                                           |
| Serialization          | Protocol Buffers                                                              |
| Endpoint languages     | Python + C++ on both physical endpoint machines                               |

---

## Architecture

```mermaid
flowchart LR
    subgraph TX["TX machine"]
        FM["File Monitor<br/>Python"]
        S0["Sender 0<br/>C++"]
        S1["Sender 1<br/>C++"]
        S2["Sender 2<br/>C++"]

        FM -->|"UDS"| S0
        FM -->|"UDS"| S1
        FM -->|"UDS"| S2
    end

    R["Router<br/>loss / bit flip / misroute"]

    S0 -->|"UDP 9000"| R
    S1 -->|"UDP 9001"| R
    S2 -->|"UDP 9002"| R

    subgraph RX["RX machine"]
        R0["Receiver 0<br/>C++"]
        R1["Receiver 1<br/>C++"]
        R2["Receiver 2<br/>C++"]
        SM["Session Manager<br/>Python"]

        R0 -->|"UDS"| SM
        R1 -->|"UDS"| SM
        R2 -->|"UDS"| SM
    end

    R -->|"UDP 9000"| R0
    R -->|"UDP 9001"| R1
    R -->|"UDP 9002"| R2
```

The network direction is strictly:

```text
TX  ───────────────>  Router  ───────────────>  RX
```

There is deliberately **no**:

```text
RX  ───────────────>  TX
```

ACK, NACK, retry request, or other reverse network channel.

---

## Process model

### TX machine

| Process      | Language | Responsibility                                                                               |
| ------------ | -------- | -------------------------------------------------------------------------------------------- |
| File Monitor | Python   | Watches the source tree, detects create/modify/delete events, encodes files, schedules paths |
| Sender 0     | C++      | UDS → UDP path using port 9000                                                               |
| Sender 1     | C++      | UDS → UDP path using port 9001                                                               |
| Sender 2     | C++      | UDS → UDP path using port 9002                                                               |

### RX machine

| Process         | Language | Responsibility                                                              |
| --------------- | -------- | --------------------------------------------------------------------------- |
| Receiver 0      | C++      | UDP 9000 → shared Session Manager UDS                                       |
| Receiver 1      | C++      | UDP 9001 → shared Session Manager UDS                                       |
| Receiver 2      | C++      | UDP 9002 → shared Session Manager UDS                                       |
| Session Manager | Python   | Validates packets, reconstructs blocks/files, handles versions and deletion |

This intentionally guarantees that **both endpoint machines run Python and C++ processes**.

---

## How transfers work

### 1. File detection

The File Monitor recursively scans the TX source directory.

A file must remain stable for multiple scans before transmission begins. This reduces the chance of sending a file while another application is still writing it.

The default polling interval is:

```text
1 second
```

### 2. Small files

Files below the configured small-file threshold use one Sender/Receiver pair.

Example:

```text
file-a.txt  -> Sender 0 -> Receiver 0
file-b.txt  -> Sender 1 -> Receiver 1
file-c.txt  -> Sender 2 -> Receiver 2
```

Up to three small files can therefore be transferred concurrently.

The current implementation uses a **10 MiB** threshold.

### 3. Large files

Large files are processed in **1 MiB blocks**.

Each block is RaptorQ-encoded, and its encoded packets are distributed across all three Sender paths:

```text
Large file
   |
   +--> Sender 0
   +--> Sender 1
   +--> Sender 2
```

The File Monitor streams the file block-by-block rather than loading an entire 1 GiB file into memory.

### 4. Packet validation

Every packet contains enough metadata for independent RX processing, including:

- file ID/version,
- relative file path,
- original file size,
- original file SHA-256,
- packet index,
- block index and offset,
- RaptorQ symbol data,
- target receiver,
- operation (`WRITE` or `DELETE`),
- packet SHA-256.

### 5. Reconstruction

All three C++ Receivers forward received Protobuf messages to the same Python Session Manager through Unix Domain Sockets.

The Session Manager:

1. parses Protobuf,
2. validates metadata and the packet hash,
3. ignores invalid/corrupted packets,
4. groups valid packets by file and block,
5. lets RaptorQ reconstruct blocks when enough symbols are available,
6. writes reconstructed blocks to a temporary `.part` file,
7. validates the final SHA-256,
8. atomically moves the completed file into its final location.

---

## Reliability model

| Network problem                     | Uniflow behavior                                                |
| ----------------------------------- | --------------------------------------------------------------- |
| Packet dropped                      | RaptorQ repair symbols can replace missing symbols              |
| Packet bit flipped                  | Packet SHA-256 no longer matches; packet is rejected            |
| Packet sent to wrong Receiver       | Receiver still forwards it to the shared Session Manager        |
| Packets arrive out of order         | Session Manager groups by file/block metadata                   |
| Duplicate packet                    | Duplicate packet state is ignored                               |
| Old version arrives late            | Version comparison prevents it from replacing a newer version   |
| Old `DELETE` arrives late           | Version-aware delete handling prevents deletion of a newer file |
| Old `WRITE` arrives after delete    | Delete tombstone/version prevents recreation of the old file    |
| Final reconstructed bytes are wrong | Final SHA-256 fails; file is not published                      |

### Why there is no retransmission protocol

Uniflow cannot ask TX to resend a packet because the assignment network is strictly one-way.

Instead:

```text
TX sends original data + repair data
                   |
                   v
RX reconstructs whatever was lost
```

This is forward error correction rather than an ACK/retry protocol.

---

## File lifecycle

Uniflow continuously mirrors these operations:

```text
CREATE
TX/data/out/hello.txt
        |
        v
RX/data/in/hello.txt
```

```text
MODIFY
TX/data/out/hello.txt
        |
        v
newer RX/data/in/hello.txt
```

```text
DELETE
TX/data/out/hello.txt
        |
        v
DELETE Protobuf control message
        |
        v
RX/data/in/hello.txt is removed
```

Deletion remains one-way. RX does not acknowledge the delete.

The delete control message is sent through all three Sender paths to improve the chance that at least one copy survives packet loss.

---

# Quick start — one computer

This is the recommended development and demonstration mode.

Docker Compose creates three containers:

```text
tx_machine  ->  router  ->  rx_machine
```

The containers behave as separate network participants while running on one physical computer.

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose v2
- Git

On Windows, Docker Desktop should be using **Linux containers**.

## 1. Clone the repository

```bash
git clone https://github.com/MrFaiman/uniflow.git
cd uniflow
```

Check out the branch you want to test if it has not yet been merged into `main`:

```bash
git checkout docs/final-deployment
```

## 2. Start the complete topology

From the repository:

```bash
cd devops
docker compose up --build
```

By default, the development router currently injects mild faults:

```text
3% packet loss
3% bit flips
3% misrouting
```

This is useful for demonstrating fault tolerance.

### Start with no injected faults

For a clean baseline in Bash/Git Bash:

```bash
PACKET_LOSS=0 BIT_FLIP=0 MISROUTING=0 docker compose up --build
```

For Windows PowerShell:

```powershell
$env:PACKET_LOSS="0"
$env:BIT_FLIP="0"
$env:MISROUTING="0"
docker compose up --build
```

## 3. Transfer files

While Compose is still running, place a file in:

```text
devops/data/out/
```

For example from `devops/`:

```bash
echo "hello from Uniflow" > data/out/hello.txt
```

The reconstructed file should appear at:

```text
devops/data/in/hello.txt
```

A successful RX log contains:

```text
COMPLETE: hello.txt - HASH OK
```

## 4. Test modification

```bash
echo "updated content" > data/out/hello.txt
```

After the monitor detects the stable modification, the RX copy is replaced with the newer version.

## 5. Test deletion

```bash
rm data/out/hello.txt
```

The RX log should report:

```text
DELETED: hello.txt
```

and:

```text
data/in/hello.txt
```

should disappear.

## 6. Watch logs

In another terminal:

```bash
cd devops
docker compose logs -f tx_machine rx_machine router
```

## 7. Stop the system

If Compose is attached to the terminal:

```text
Ctrl+C
```

Then clean up:

```bash
docker compose down
```

---

# Run on two physical computers

This is the deployment model that demonstrates that TX and RX are genuinely separate physical endpoints.

## Physical topology

```text
┌──────────────────────────┐
│ PC A — TX                │
│ Python File Monitor      │
│ C++ Sender 0 / 1 / 2     │
└────────────┬─────────────┘
             │
             │ UDP 9000-9002
             v
       ┌───────────────┐
       │ Router        │
       │ one-way only  │
       └───────┬───────┘
               │
               │ UDP 9000-9002
               v
┌──────────────────────────┐
│ PC B — RX                │
│ C++ Receiver 0 / 1 / 2   │
│ Python Session Manager   │
└──────────────────────────┘
```

> The real two-PC assignment setup assumes an **external/instructor router** between TX and RX.
>
> The bundled `devops/router` container is configured for the local Docker Compose topology and resolves RX by the Compose hostname `rx_machine`. Use it for the one-computer simulation unless you explicitly make its RX host configurable.

## Network requirements

Before starting:

- PC A must be able to reach the router.
- The router must receive UDP ports **9000, 9001, and 9002** from TX.
- The router must forward traffic toward PC B.
- PC B must allow inbound UDP ports **9000, 9001, and 9002**.
- No network route from RX back to TX is required by Uniflow.
- If an instructor controls the router, provide them with the RX machine IP and required UDP ports.

Find the RX IP on Windows:

```powershell
ipconfig
```

or Linux:

```bash
ip addr
```

---

## Step 1 — clone and build on both PCs

On **both PC A and PC B**, from the repository root:

```bash
git clone https://github.com/MrFaiman/uniflow.git
cd uniflow
git checkout docs/final-deployment
docker build -f devops/uniflow.Dockerfile -t uniflow-endpoint .
```

Once the final project is merged, the checkout command can simply use `main`.

---

## Step 2 — start RX first on PC B

### Windows PowerShell

Run from the repository root:

```powershell
New-Item -ItemType Directory -Force .\devops\data\in | Out-Null

docker run --rm --name uniflow-rx `
  -p 9000:9000/udp `
  -p 9001:9001/udp `
  -p 9002:9002/udp `
  -e PORT=9000 `
  -e UNIFLOW_WORKERS=3 `
  -e IPC_SOCKET_PATH=/tmp/proto_ipc.sock `
  -e UNIFLOW_NET_BINARY=/usr/local/bin/uniflow-net `
  -v "${PWD}\devops\data\in:/data/in" `
  uniflow-endpoint receive /data/in
```

### Linux/macOS Bash

```bash
mkdir -p devops/data/in

docker run --rm --name uniflow-rx \
  -p 9000:9000/udp \
  -p 9001:9001/udp \
  -p 9002:9002/udp \
  -e PORT=9000 \
  -e UNIFLOW_WORKERS=3 \
  -e IPC_SOCKET_PATH=/tmp/proto_ipc.sock \
  -e UNIFLOW_NET_BINARY=/usr/local/bin/uniflow-net \
  -v "$PWD/devops/data/in:/data/in" \
  uniflow-endpoint receive /data/in
```

Expected RX processes:

```text
Python Session Manager
C++ Receiver 0
C++ Receiver 1
C++ Receiver 2
```

### Windows firewall

If Windows Defender Firewall blocks the RX ports, open an elevated PowerShell and allow UDP 9000-9002:

```powershell
New-NetFirewallRule `
  -DisplayName "Uniflow UDP 9000-9002" `
  -Direction Inbound `
  -Protocol UDP `
  -LocalPort 9000-9002 `
  -Action Allow
```

Remove that firewall rule after the demonstration if it is no longer required.

---

## Step 3 — configure the router

The router must forward TX traffic to the IP of **PC B**.

Expected port flow:

```text
TX Sender 0 -> router:9000 -> RX:9000
TX Sender 1 -> router:9001 -> RX:9001
TX Sender 2 -> router:9002 -> RX:9002
```

The router may intentionally:

```text
drop packets
flip packet bits
send a packet to another RX port
```

The router must not create an ACK path back to TX.

If the instructor provides the router, use the IP/hostname they provide as `ROUTER_IP` in the next step.

---

## Step 4 — start TX on PC A

Replace:

```text
192.168.1.100
```

with the real router IP.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force .\devops\data\out | Out-Null

$ROUTER_IP="192.168.1.100"

docker run --rm --name uniflow-tx `
  -e PORT=9000 `
  -e UNIFLOW_WORKERS=3 `
  -e IPC_SOCKET_PATH=/tmp/proto_ipc.sock `
  -e UNIFLOW_NET_BINARY=/usr/local/bin/uniflow-net `
  -e UNIFLOW_WATCH_POLLING=1.0 `
  -e UNIFLOW_MAX_FILE_BYTES=1073741824 `
  -e UNIFLOW_FEC_REPAIR_PERCENT=20 `
  -e UNIFLOW_SEND_RATE_MBPS=25 `
  -v "${PWD}\devops\data\out:/data/out" `
  uniflow-endpoint send /data/out $ROUTER_IP
```

### Linux/macOS Bash

```bash
mkdir -p devops/data/out

ROUTER_IP="192.168.1.100"

docker run --rm --name uniflow-tx \
  -e PORT=9000 \
  -e UNIFLOW_WORKERS=3 \
  -e IPC_SOCKET_PATH=/tmp/proto_ipc.sock \
  -e UNIFLOW_NET_BINARY=/usr/local/bin/uniflow-net \
  -e UNIFLOW_WATCH_POLLING=1.0 \
  -e UNIFLOW_MAX_FILE_BYTES=1073741824 \
  -e UNIFLOW_FEC_REPAIR_PERCENT=20 \
  -e UNIFLOW_SEND_RATE_MBPS=25 \
  -v "$PWD/devops/data/out:/data/out" \
  uniflow-endpoint send /data/out "$ROUTER_IP"
```

Expected TX processes:

```text
Python File Monitor
C++ Sender 0
C++ Sender 1
C++ Sender 2
```

---

## Step 5 — verify the two-PC transfer

On **PC A**, create:

```text
devops/data/out/two-pc-test.txt
```

PC B should reconstruct:

```text
devops/data/in/two-pc-test.txt
```

Then verify all three lifecycle operations:

```text
1. CREATE the file on PC A -> it appears on PC B.
2. MODIFY the file on PC A -> PC B receives the newer version.
3. DELETE the file on PC A -> it disappears on PC B.
```

The RX log should show:

```text
COMPLETE: two-pc-test.txt - HASH OK
```

and after deletion:

```text
DELETED: two-pc-test.txt
```

---

## Step 6 — prove the required processes are running

On PC A:

```bash
docker top uniflow-tx
```

On PC B:

```bash
docker top uniflow-rx
```

This provides an easy demonstration that each physical endpoint is running both:

```text
Python
C++
```

and that exactly three network workers exist on each side.

---

# Automated end-to-end testing

The repository includes a Docker-based end-to-end test runner.

Run from `devops/`.

## Clean network

```bash
./run-transfer-test.sh --chaos none
```

## Packet loss only

```bash
./run-transfer-test.sh --chaos loss
```

## Bit flips only

```bash
./run-transfer-test.sh --chaos flip
```

## Misrouting only

```bash
./run-transfer-test.sh --chaos misroute
```

## Mild combined faults

```bash
./run-transfer-test.sh --chaos mild
```

Equivalent fault profile:

```text
3% loss
3% bit flips
3% misrouting
20% RaptorQ repair percentage
```

## Harsh combined faults

```bash
./run-transfer-test.sh --chaos harsh
```

Configured profile:

```text
15% loss
15% bit flips
15% misrouting
50% RaptorQ repair percentage
```

## Full 1 GiB verification

```bash
./run-transfer-test.sh \
  --chaos none \
  --include-1gb \
  --timeout 7200
```

The verifier checks file size and SHA-256.

## Keep the topology running after the test

```bash
./run-transfer-test.sh --chaos none --keep-running
```

Unlike the normal test runner, this leaves the containers alive so the File Monitor continues watching for later changes.

The standard automated fixtures cover:

- empty file,
- tiny file,
- 1 KiB file,
- 5 MiB file,
- below-threshold file,
- above-threshold file,
- nested-path file,
- 30 MiB file,
- file modification,
- optional 1 GiB file.

Deletion can also be verified manually while the continuous topology is running.

---

# Development and unit tests

## Python requirements

- Python 3.13+
- `uv`
- Protocol Buffers compiler when regenerating bindings

Install `uv` with pip if necessary:

```bash
python -m pip install uv
```

If the `uv` executable is not in your shell `PATH`, use:

```bash
python -m uv
```

instead.

## Generate Python Protobuf

Preferred when standalone `protoc` is available:

```bash
bash scripts/generate-proto.sh python
```

If `protoc` is not installed on the host:

```bash
python -m pip install grpcio-tools

python -m grpc_tools.protoc \
  -I proto \
  --python_out=python/client/src/client \
  proto/transfer.proto
```

Do not manually edit generated Protobuf files.

## Run Python tests

```bash
cd python/client
python -m uv sync --all-groups
python -m uv run ruff check src tests
python -m uv run pytest
```

### Windows host note

Uniflow intentionally uses **Unix Domain Sockets** for IPC.

Some native Windows Python builds do not expose:

```python
socket.AF_UNIX
```

On such a host, the UDS-specific tests will fail even though they work inside the Linux Docker runtime and Linux CI.

Check:

```bash
python -c "import socket; print(hasattr(socket, 'AF_UNIX'))"
```

If it prints:

```text
False
```

you can run the Windows-compatible subset:

```bash
python -m uv run pytest \
  -k "not unix_socket and not multiple_receivers_use_one_socket"
```

For the complete suite, use the Linux Docker/CI environment.

## Build C++ locally

Requirements:

- CMake 3.16+
- C++17 compiler
- Protocol Buffers development library/compiler

Build:

```bash
cmake \
  -S cpp \
  -B cpp/build \
  -DCMAKE_BUILD_TYPE=Release

cmake --build cpp/build --parallel
```

The CMake build generates the C++ Protobuf bindings automatically.

---

# Configuration

## Endpoint configuration

| Variable                     |                      Default | Purpose                                                     |
| ---------------------------- | ---------------------------: | ----------------------------------------------------------- |
| `PORT`                       |                       `9000` | Base UDP port; workers use 9000, 9001, 9002                 |
| `UNIFLOW_WORKERS`            |                          `3` | Worker count; this project intentionally requires exactly 3 |
| `IPC_SOCKET_PATH`            |        `/tmp/proto_ipc.sock` | Base Unix Domain Socket path                                |
| `UNIFLOW_WATCH_POLLING`      |                        `1.0` | TX filesystem polling interval in seconds                   |
| `UNIFLOW_MAX_FILE_BYTES`     |                 `1073741824` | Maximum accepted source file size (1 GiB)                   |
| `UNIFLOW_FEC_REPAIR_PERCENT` |                         `20` | RaptorQ repair packet percentage                            |
| `UNIFLOW_NET_BINARY`         | `/usr/local/bin/uniflow-net` | C++ network worker executable                               |
| `UNIFLOW_SEND_RATE_MBPS`     |              `25` in Compose | Per-Sender UDP pacing                                       |

## Router configuration

| Variable             | Default | Purpose                                          |
| -------------------- | ------: | ------------------------------------------------ |
| `PACKET_LOSS`        |  `0.03` | Probability of dropping a packet                 |
| `BIT_FLIP`           |  `0.03` | Probability of corrupting a packet               |
| `MISROUTING`         |  `0.03` | Probability of forwarding to a different RX port |
| `RANDOM_SEED`        |  `1337` | Deterministic random seed                        |
| `STATS_INTERVAL_SEC` |    `10` | Router statistics interval                       |
| `LOG_PACKETS`        |     `0` | Enable detailed packet logging                   |

Probabilities are decimal values:

```text
0.03 = 3%
0.15 = 15%
```

---

# Repository structure

```text
uniflow/
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── cpp/
│   ├── CMakeLists.txt
│   └── src/
│       ├── main.cpp
│       ├── sender.cpp
│       └── receiver.cpp
│
├── devops/
│   ├── docker-compose.yaml
│   ├── uniflow.Dockerfile
│   ├── entrypoint.sh
│   ├── config.py
│   ├── router/
│   ├── scripts/
│   ├── data/
│   │   ├── out/
│   │   └── in/
│   └── run-transfer-test.sh
│
├── proto/
│   └── transfer.proto
│
├── python/
│   └── client/
│       ├── pyproject.toml
│       ├── src/client/
│       │   ├── file_monitor/
│       │   ├── session_manager/
│       │   ├── common/
│       │   └── cli.py
│       └── tests/
│
├── scripts/
│   └── generate-proto.sh
│
└── README.md
```

The active endpoint runtime is implemented by:

```text
python/client/
cpp/
proto/
devops/
```

Any older experimental implementation that remains elsewhere in the repository should not be treated as part of the active Docker runtime.

---

# Assignment requirement coverage

| Requirement                       | Implementation                                   |
| --------------------------------- | ------------------------------------------------ |
| Two physical endpoint computers   | Separate TX and RX deployment supported          |
| Strictly one-way network          | No RX → TX ACK/retry channel                     |
| TX File Monitor                   | Python File Monitor                              |
| Three independent Senders         | Three C++ Sender processes                       |
| Three independent Receivers       | Three C++ Receiver processes                     |
| Different network ports           | UDP 9000, 9001, 9002                             |
| RX Session Manager                | Central Python Session Manager                   |
| Small files on one pair           | Round-robin pair selection                       |
| Multiple small files concurrently | Up to three pair-specific transfers              |
| Large file across all three paths | Packet distribution across all Senders           |
| Router packet loss                | Configurable fault injection                     |
| Router bit corruption             | Configurable fault injection                     |
| Router misrouting                 | Configurable fault injection                     |
| File creation monitoring          | Continuous File Monitor                          |
| File modification monitoring      | Stable-signature change detection                |
| File deletion synchronization     | One-way `DELETE` extension                       |
| Final hash comparison             | SHA-256 before publish                           |
| Files up to 1 GiB                 | Enforced maximum + explicit 1 GiB test           |
| Python process on each endpoint   | File Monitor / Session Manager                   |
| C++ process on each endpoint      | Sender / Receiver workers                        |
| Unix Domain Socket IPC            | Python ↔ C++ process communication               |
| Protocol Buffers                  | Shared `transfer.proto` for IPC/network messages |
| Documented build/run flow         | This README + automated scripts                  |
| Automated verification            | Python tests, CI, Docker end-to-end tests        |

---

# Security and integrity notes

Uniflow performs several defensive checks:

- relative paths are normalized,
- absolute paths and path traversal are rejected,
- packet metadata is validated,
- packet SHA-256 is checked,
- final file SHA-256 is checked,
- partial files are written separately before atomic replacement,
- stale file versions are prevented from replacing newer versions,
- stale delete operations are prevented from deleting newer versions.

However, this project does **not** currently implement:

- encryption,
- authenticated peers,
- packet signatures/MACs,
- authorization,
- internet-facing hardening.

Therefore, Uniflow should be demonstrated on a controlled lab/LAN environment rather than exposed directly to an untrusted public network.

---

# Troubleshooting

## `protoc: command not found`

Either install the Protocol Buffers compiler or generate Python bindings using:

```bash
python -m pip install grpcio-tools

python -m grpc_tools.protoc \
  -I proto \
  --python_out=python/client/src/client \
  proto/transfer.proto
```

## `uv: command not found` after installation

Run:

```bash
python -m uv --version
```

and use:

```bash
python -m uv sync --all-groups
python -m uv run pytest
```

## Windows test failure: `socket.AF_UNIX`

Check:

```bash
python -c "import socket; print(hasattr(socket, 'AF_UNIX'))"
```

If it returns `False`, run UDS-dependent tests in Docker/Linux/CI.

## A file does not transfer

Check:

```bash
docker compose ps
docker compose logs -f tx_machine rx_machine router
```

Confirm that the source file is under:

```text
devops/data/out/
```

and wait for the stable-file scans.

## A deleted file remains on RX

Make sure the containers were rebuilt after adding the `DELETE` Protobuf operation:

```bash
docker compose down
docker compose up --build
```

Then confirm the TX log reports a delete message and the RX log reports:

```text
DELETED: <relative-path>
```

## One-PC test exits and monitoring stops

The normal test script intentionally tears Compose down when verification finishes.

Use:

```bash
./run-transfer-test.sh --chaos none --keep-running
```

or run the application directly:

```bash
docker compose up --build
```

---

# Team workflow

For a three-person project, keep contributions visible and reviewable in Git history.

Recommended workflow:

```text
main
  ^
  |
final integration branch
  ^
  |
feature/docs branches from individual contributors
```

Typical contribution flow:

```bash
git checkout -b feature/my-change
git add <specific-files>
git commit -m "feat: describe the change"
git push -u origin feature/my-change
```

Then open a pull request, review it, run CI, and merge it into the integration branch.

Before submission:

1. verify every team member has meaningful commits,
2. run the Python/C++/Docker checks,
3. perform the two-physical-PC demonstration,
4. merge the final working branch into `main`,
5. confirm GitHub CI is green on the submitted revision.

---

<div align="center">

**Uniflow — one direction, three paths, reliable reconstruction.**

</div>
