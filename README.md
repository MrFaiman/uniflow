# Uniflow

Reliable one-way file distribution between two machines.

Files dropped into a watched folder on the **TX** machine appear, byte-identical,
in a folder on the **RX** machine. The network path is strictly one-way: RX never
sends anything back to TX, not even an acknowledgement. Reliability therefore
comes from forward error correction and redundant metadata rather than
retransmission.

---

## Architecture

```
        TX MACHINE                    NETWORK                  RX MACHINE
┌───────────────────────┐                            ┌──────────────────────────┐
│  File Monitor         │                            │  Receiver 0   :9000      │
│  (Python, watchdog)   │                            │  Receiver 1   :9001      │
│         │             │                            │  Receiver 2   :9002      │
│         │ UDS + protobuf                           │  (Go, one process each)  │
│         ▼             │                            │         │                │
│  Sender 0 ──┐         │                            │         │ UDS + protobuf │
│  Sender 1 ──┼─────────┼──► UDP ─► Router ─► UDP ───┼────────►│                │
│  Sender 2 ──┘         │          (chaos)           │         ▼                │
│  (Go, one process each)│                           │  Session Manager         │
└───────────────────────┘                            │  (Python)                │
                                                     │         ▼                │
                                                     │     /data/in             │
                                                     └──────────────────────────┘
```

Both machines run at least one Python process and at least one Go process.

| Component | Language | Responsibility |
|---|---|---|
| File Monitor | Python | Watches the source folder, decides small vs large, allocates workers, drives the Senders over IPC |
| Sender ×3 | Go | Reads its own share of the file, RaptorQ-encodes it, transmits UDP |
| Router | Python | Test-harness only. Injects packet loss, bit flips and misrouting |
| Receiver ×3 | Go | Listens on its own port, decodes blocks, stages them, reports to the Session Manager |
| Session Manager | Python | The only component that sees all three Receivers. Tracks completion, reconstructs the file, verifies SHA-256 |

### Small files (< 10 MB)

One Sender/Receiver pair carries the whole file. A pool hands each new file its
own free pair, so several small files transfer concurrently on different pairs.

### Large files (10 MB – 1 GB)

The file is split into 1 MiB source blocks and block *i* is owned by worker
`i % 3`. All three Senders transmit their share at the same time to their
matching Receiver port. The Session Manager reassembles the blocks in order.

### Why there is a Session Manager

No single Receiver can know a transfer is finished — it only ever sees its own
third of the blocks. Each Receiver reports every staged block to the Session
Manager over a Unix Domain Socket, and the Session Manager decides completion,
reconstructs, and verifies. This is local IPC on the RX machine only; nothing
is ever sent back across the network to TX.

---

## Reliability without ACKs

| Fault | How it is handled |
|---|---|
| Packet loss | RaptorQ repair symbols. Each block ships 30% more symbols than it strictly needs |
| Bit flip | Every datagram travels inside a `UdpEnvelope` carrying a CRC32 of its bytes. A mismatch is discarded and becomes an ordinary lost symbol that FEC repairs. Without this a flipped bit usually still decodes as valid protobuf with a *wrong* `object_id` or block number, silently poisoning receiver state. The final file is verified against the sender's SHA-256 |
| Misrouting | Receivers accept any block that reaches them, not only the ones they "own", and stage it into the directory all Receivers share, so the Session Manager still finds it |
| Duplicates | Blocks are keyed by index; a block already staged ignores further symbols |
| Reordering | Order is irrelevant — blocks are addressed by index, symbols by encoding-symbol ID |
| Data before its announcement | A Receiver cannot decode symbols for an object it has not been told about. Every worker announces the object before transmitting and repeats it periodically, and Receivers hold early symbols in a bounded buffer and replay them when the announcement arrives, rather than discarding data that will never be resent |

The 30% repair margin is sized for the specified conditions: roughly 3% dropped
plus 3% corrupted plus 3% misrouted stack to about 9%, and real loss is bursty.

If a block never arrives, the transfer cannot be retried — there is no back
channel to ask for one. The Session Manager reports it as `STALLED` with the
missing block numbers rather than hanging silently.

---

## Requirements

- Go 1.27+
- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/)
- `protoc` (Protocol Buffers compiler)
- Docker + Docker Compose (for the containerised path)

---

## Quick start (Docker — three machines)

The Compose stack models the three physical machines of the assignment as
three containers on one bridge network: `tx_machine`, `router`, `rx_machine`.

```bash
cd devops
docker compose up --build
```

Then drop a file in and watch it arrive:

```bash
echo hello > devops/data/out/test.txt
ls devops/data/in/
```

The router injects 3% packet loss, 3% bit flips and 3% misrouting by default,
so this path exercises the fault handling, not just the happy case.

Confirm the process topology inside the containers:

```bash
docker compose exec tx_machine sh -c \
  'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline; echo; done'
# python -m uniflow.cli send /data/out router   <- File Monitor
# /app/go/.bin/uniflow send   x3                <- three Senders

docker compose exec rx_machine sh -c \
  'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline; echo; done'
# /app/go/.bin/uniflow recv /data/in   x3       <- three Receivers
# python -m uniflow.session_manager_run /data/in <- Session Manager
```

Router statistics and per-file verification:

```bash
docker compose logs router     | grep '\[stats\]'
docker compose logs rx_machine | grep COMPLETE
```

### If the Docker build fails on Go module checksums

On networks that intercept TLS, the image cannot verify Go module checksums
and the build fails before any project code compiles:

```
x509: certificate signed by unknown authority
```

Build offline instead — vendored modules and protobuf generated on the host:

```bash
./devops/build-offline.sh
cd devops
docker compose -f docker-compose.yaml -f docker-compose.offline.yaml up --build
```

---

## Running locally (no Docker)

Generate protobuf code and build the Go binary once:

```bash
bash scripts/generate-proto.sh all
cd go && go build -o .bin/uniflow . && cd ..
cd python/uniflow && uv sync --all-groups && cd ../..
```

Start the RX side (3 Receivers + Session Manager):

```bash
cd python/uniflow
PORT=9000 UNIFLOW_WORKERS=3 UNIFLOW_SKIP_BUILD=1 \
RECEIVE_DIR=/tmp/uniflow-in \
UNIFLOW_SESSION_SOCKET=/tmp/uniflow_session.sock \
uv run python -m uniflow.cli receive /tmp/uniflow-in
```

Start the TX side (File Monitor + 3 Senders) in another terminal:

```bash
cd python/uniflow
PORT=9000 UNIFLOW_WORKERS=3 UNIFLOW_SKIP_BUILD=1 \
IPC_SOCKET_PATH=/tmp/uf_tx.sock UNIFLOW_WATCH_POLLING=1 \
uv run python -m uniflow.cli send /tmp/uniflow-out 127.0.0.1
```

> On macOS keep socket paths short — the OS limits Unix socket paths to about
> 104 bytes, and a long temp path will fail with `bind: invalid argument`.

Verify a transfer:

```bash
cp somefile.bin /tmp/uniflow-out/
shasum -a 256 /tmp/uniflow-out/somefile.bin /tmp/uniflow-in/somefile.bin
```

Both hashes must be identical. The Session Manager also logs:

```
COMPLETE: somefile.bin - HASH OK (31457280 bytes, sha256=...)
```

---

## Ports and sockets

| What | Default |
|---|---|
| Receiver 0 / 1 / 2 | UDP 9000 / 9001 / 9002 |
| File Monitor → Sender *i* | `${IPC_SOCKET_PATH}.i` (e.g. `/tmp/proto_ipc.sock.0`) |
| Receivers → Session Manager | `UNIFLOW_SESSION_SOCKET` (`/tmp/uniflow_session.sock`) |

## Environment variables

| Variable | Default | Used by | Purpose |
|---|---|---|---|
| `PORT` | `9000` | both | Base UDP port; workers use `PORT`..`PORT+2` |
| `UNIFLOW_WORKERS` | `3` | both | Worker count (minimum 3) |
| `IPC_SOCKET_PATH` | — | TX | Base path for File-Monitor→Sender sockets |
| `UNIFLOW_SESSION_SOCKET` | `/tmp/uniflow_session.sock` | RX | Receiver→Session-Manager socket |
| `RECEIVE_DIR` | `/tmp/uniflow-in` | RX | Where reconstructed files are written |
| `UNIFLOW_TARGET_PORT` | same as `PORT` | TX | Base port to transmit to; set when a router listens elsewhere |
| `UNIFLOW_WATCH_POLLING` | unset | TX | `1` to poll instead of using inotify (needed for bind mounts) |
| `UNIFLOW_SKIP_BUILD` | unset | both | `1` to use the prebuilt Go binary |
| `UNIFLOW_MAX_FILE_BYTES` | `1073741824` | TX | Reject files larger than this |
| `PACKET_LOSS` / `BIT_FLIP` / `MISROUTING` | `0.03` | router | Fault probabilities |
| `ROUTER_TRACE_PACKETS` | unset | router | `1` to log every packet (slow; off by default) |
| `RX_HOST` | `rx_machine` | router | Where the router forwards |
| `UNIFLOW_ROUTER_LISTEN_PORT` | same as `PORT` | router | Set when the router shares a host with the Receivers |

---

## Tests

```bash
# Go: unit tests plus the race detector
cd go && go test -race ./transfer ./tests ./scripts

# Python: unit tests and lint
cd python/uniflow && uv run pytest && uv run ruff check .
```

End-to-end, covering empty/1 B/1 KB/5 MB/just-under-10 MB/just-over-10 MB/30 MB
and a nested path, comparing SHA-256 for every file:

```bash
# direct TX -> RX
python3 devops/scripts/e2e_matrix.py

# through the router, no faults (prove this first)
python3 devops/scripts/e2e_matrix.py --router --loss 0 --flip 0 --misroute 0

# then introduce faults, individually and combined
python3 devops/scripts/e2e_matrix.py --router --loss 0.03
python3 devops/scripts/e2e_matrix.py --router --flip 0.03
python3 devops/scripts/e2e_matrix.py --router --misroute 0.03
python3 devops/scripts/e2e_matrix.py --router --loss 0.03 --flip 0.03 --misroute 0.03
```

The harness fails the run if the router reports no traffic, so a
misconfigured port range cannot masquerade as a clean fault-injection pass.

---

## Memory behaviour

A 1 GB transfer does not need 1 GB of RAM. Each Sender hashes the file as a
stream and reads only the blocks it owns, one 1 MiB block at a time into a
reused buffer. The Session Manager reconstructs by streaming staged blocks
into the output file while hashing incrementally. Peak working set per process
is a few MB regardless of file size.

Staged blocks do occupy disk under `RECEIVE_DIR/.uniflow/staging/` until the
object completes, so RX needs free disk on the order of the file size.

---

## Protobuf

Schemas live in `schemas/`:

- `message.proto` — IPC: `IPCRequest`/`IPCResponse` (TX) and `BlockReport` (RX)
- `flute.proto` — wire format: `FileDeliveryTable`, `FluteDataPacket`,
  `PathOperation`, wrapped in `UdpDatagram`, which in turn travels inside a
  CRC-carrying `UdpEnvelope` — that envelope is what a UDP packet contains

Regenerate after any change:

```bash
bash scripts/generate-proto.sh all   # or: go | python
```

Generated code is not committed.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `bind: invalid argument` on a socket | Unix socket path too long (macOS ~104 bytes). Use a short path |
| `IPC_SOCKET_PATH is not set` | Export it, or add it to `.env` |
| Transfer never completes, `STALLED` in the log | A block never arrived. With no ACK it cannot be retried; check router loss rates and the receive-side drop counters |
| Router shows `received=0` | TX is bypassing it — check `UNIFLOW_TARGET_PORT` against the router's listen ports |
| Files never appear on a bind mount | Set `UNIFLOW_WATCH_POLLING=1`; inotify does not fire reliably on bind mounts |

---

## Repository layout

```
go/                  Sender, Receiver, FEC, framing, checksum, IPC server
python/uniflow/      File Monitor, Session Manager, supervisors, CLI
schemas/             Protobuf definitions (canonical)
devops/              Docker Compose, router, test harness
scripts/             Protobuf generation
```

`python/client/` is an earlier, superseded pure-Python prototype. It is not
built, imported, or run by anything here, and `proto/transfer.proto` belongs to
it rather than to the current system.
