# Uniflow

One-way file synchronization over three independent UDP paths.

```text
TX File Monitor (Python)
  -> 3 Unix sockets -> 3 C++ Senders
  -> router ports 9000/9001/9002
  -> 3 C++ Receivers -> shared Unix socket
  -> RX Session Manager (Python)
```

RX sends no ACK, NACK, or retransmission request to TX. The router only
forwards toward RX. All receiver workers feed one reconstruction manager,
so a packet delivered on the wrong path can still be used.

## Transfer semantics

- Recursive file create, modify, and delete synchronization, preserving paths.
  Directory moves/removals become writes and deletes for the affected files;
  empty directories are not transmitted.
- Files below **10,000,000 bytes** use one sender per file. Up to three small
  files transfer concurrently on different senders. Larger files stripe
  encoded packets across all three senders. Maximum file size: **1 GiB**.
- Files are observed over two stable processing passes. Watchdog wakes the
  monitor promptly; recursive reconciliation catches missing events on bind
  mounts and directory moves.
- Python encodes 1 MiB blocks with RaptorQ, using 1024-byte symbols and
  configurable repair overhead. Nonempty transfers stream block-by-block.
- Every Protobuf packet carries SHA-256 over its metadata and payload.
  RX checks framing, paths, versions, metadata, and packet hashes before
  decoding. The reconstructed file must pass its full SHA-256 before an
  atomic replacement of the destination.
- Empty-file metadata is repeated three times on its assigned sender. DELETE
  metadata is sent once on each of the three paths with a shared version ID.
- Versions are nanosecond timestamps with UUIDs, increasing within a running
  TX process even if the wall clock moves backward. Newer transfers supersede
  older ones. DELETE leaves an in-memory tombstone that rejects older writes.
- RX temporary data lives under `.uniflow/parts`. That path is reserved.
  Traversal, absolute paths, and noncanonical protocol paths are rejected.

This is bounded-redundancy delivery, not guaranteed delivery under arbitrary
loss. See operational limits below.

## Docker profiles

Requires Docker Compose **2.20 or newer** (optional profile dependencies and
`up --wait`) and a running Docker Engine with BuildKit. Commands below run
from the repository root.

| Profile | Services |
| --- | --- |
| `all` | TX, router, RX |
| `tx` | TX and router; set `RX_HOST` to the RX computer |
| `rx` | RX only; publishes UDP 9000, 9001, 9002 |
| `tx-external` | TX only; set `ROUTER_HOST` to an external router |

### One computer

```sh
docker compose -f devops/docker-compose.yaml --profile all up --build --wait
```

Place source files under `devops/data/out`. Reconstructed files appear under
`devops/data/in`. Changes and deletes propagate while both endpoints run.

Compose starts RX before the router and TX. Local health checks inspect all
three worker processes/socket paths and the bound UDP ports, without sending
network probes. The two endpoint images use the same Debian Trixie release
for C++ building and runtime libraries.

### Two physical computers

Start RX on PC B first and permit inbound UDP 9000-9002 through its firewall:

```sh
docker compose -f devops/docker-compose.yaml --profile rx up --build --wait
```

Then start TX and the router on PC A, using PC B's reachable address:

```sh
RX_HOST=192.168.1.50 docker compose -f devops/docker-compose.yaml --profile tx up --build --wait
```

The router stays on PC A. It forwards each input port to the matching UDP
port on PC B unless fault injection selects another path. No reverse
application traffic is required. The `tx` profile cannot verify remote RX
readiness, so start PC B before sending files.

### External router

```sh
ROUTER_HOST=192.168.1.20 docker compose -f devops/docker-compose.yaml --profile tx-external up --build --wait
```

Start the RX profile separately. The external router must forward the three
UDP paths to RX. The provided router container is not started in this mode.

## Configuration

Compose reads shell environment overrides. To use a file explicitly, add
`--env-file .env` before the profile option. Copy [`.env.example`](.env.example)
to `.env` to start with the documented Compose settings.

| Variable | Compose default | Meaning |
| --- | --- | --- |
| `RX_HOST` | `rx_machine` | Router's destination host |
| `ROUTER_HOST` | `router` | TX's router host |
| `PACKET_LOSS` | `0.03` | Drop probability |
| `BIT_FLIP` | `0.03` | Per-packet bit-flip probability |
| `MISROUTING` | `0.03` | Wrong-path probability |
| `RANDOM_SEED` | `1400` | Router RNG seed |
| `STATS_INTERVAL_SEC` | `10` | Stats interval, 0 disables |
| `LOG_PACKETS` | `0` | Set to 1 for individual fault logs |
| `UNIFLOW_FEC_REPAIR_PERCENT` | `50` | Repair overhead, 0-200 percent |
| `UNIFLOW_SEND_RATE_MBPS` | `1` | Megabits/sec per sender; 0 disables pacing |
| `UNIFLOW_WATCH_POLLING` | `1.0` | Maximum wait between processing passes |
| `UNIFLOW_MAX_FILE_BYTES` | `1073741824` | Limit, at most 1 GiB |

IPC defaults to `/tmp/uniflow/recv.sock` on RX and
`/tmp/uniflow/send.sock.sender.0` through `.sender.2` on TX. Missing parent
directories are created automatically. `IPC_SOCKET_PATH` overrides the RX
socket or the Python TX socket base (the `.sender.N` suffix is retained).
Standalone C++ workers treat an explicit override as the exact socket path.

Compose fixes `PORT=9000` and `UNIFLOW_WORKERS=3`. For a native deployment,
`PORT` may be 1-65533 and `UNIFLOW_NET_BINARY` points to the built worker.
Native Python defaults to 20 percent FEC; standalone C++ defaults to unpaced sending.
Export the example's FEC and pacing values to use the Compose policy locally.

`UNIFLOW_LOG_FILE` optionally mirrors C++ logs to a file. Compose endpoints
use `/var/log/uniflow/tx.log` and `rx.log` inside their containers; stdout/stderr
remains available through `docker compose logs`.

## Native build and usage

Native development requires Python 3.13+, uv, a Rust toolchain for the
RaptorQ extension, CMake 3.28+, Ninja, Git, Protobuf with protoc, and a C++20
compiler/standard library implementing `std::format` (for example GCC 14 or
Clang 19 with a suitable standard library).

```sh
cmake -S cpp -B cpp/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DUNIFLOW_BUILD_TESTS=ON
cmake --build cpp/build --parallel
ctest --test-dir cpp/build --output-on-failure --parallel 4
uv sync --project python/client --all-groups --frozen
```

The Python CLI starts and supervises the three C++ workers for each endpoint.
After building, run RX first in one terminal and TX in another. Run these
commands from the repository root on each endpoint, replacing the example
directories and router address:

```sh
export UNIFLOW_NET_BINARY="$PWD/cpp/build/uniflow-net"
uv run --project python/client --frozen uniflow recv /absolute/path/to/in
```

```sh
export UNIFLOW_NET_BINARY="$PWD/cpp/build/uniflow-net"
export UNIFLOW_FEC_REPAIR_PERCENT=50
export UNIFLOW_SEND_RATE_MBPS=1
uv run --project python/client --frozen uniflow send /absolute/path/to/out 192.168.1.20
```

The router must forward UDP ports 9000-9002 to RX. The endpoint CLI does not
start a router. With the Python environment activated, `uniflow send ROUTER`
and `uniflow recv` use the current working directory as the source or
destination. `python -m client.cli` exposes the same commands. Stop an endpoint
with Ctrl+C or SIGTERM; its supervisor shuts down its workers.

## Tests and coverage

Run these commands from the repository root after the native build and
dependency installation above:

```sh
uv run --project python/client --frozen ruff check python/client/src python/client/tests
uv run --project python/client --frozen ruff format --check python/client/src python/client/tests
UNIFLOW_NET_BINARY="$PWD/cpp/build/uniflow-net" uv run --project python/client --frozen pytest -q python/client/tests
uv run --project python/client --frozen pytest -q devops/scripts/test_transfer_fixtures.py devops/router/test_router.py
shellcheck devops/entrypoint.sh devops/run-transfer-test.sh scripts/generate-proto.sh
```

Setting `UNIFLOW_NET_BINARY` includes the compiled worker and CLI lifecycle
tests in the Python suite. Pytest reports line and branch coverage and writes
`htmlcov/index.html` relative to the working directory. Add `--no-cov` to
disable coverage for a run.

For C++ coverage, run:

```sh
cmake -S cpp -B cpp/build-coverage -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DUNIFLOW_BUILD_TESTS=ON \
  -DUNIFLOW_ENABLE_COVERAGE=ON
cmake --build cpp/build-coverage --target coverage --parallel
```

The coverage target runs CTest and Python worker/CLI integration tests against
the instrumented binary, then writes `cpp/build-coverage/coverage/index.html`.
See the [C++ coverage instructions](cpp/README.md) for supported toolchains
and coverage thresholds, and the [Python test instructions](python/client/README.md)
for package-local commands.

CMake generates its own C++ Protobuf sources. To regenerate the checked-in
Python bindings, use protoc 35.1, matching Python Protobuf 7.35.1 and the
locked runtime:

```sh
bash scripts/generate-proto.sh python
```

The script also accepts `cpp` for standalone C++ bindings or `all` (the
default) for both languages. CI checks that Python regeneration produces
no changes.

### Transfer tests

**The transfer script clears its input/output fixture directories.** Defaults
are `devops/data/out` and `devops/data/in`. Use dedicated directories to
avoid touching files from a manual deployment:

```sh
export COMPOSE_PROJECT_NAME=uniflow-test
export UNIFLOW_TEST_OUT_DIR="$PWD/.test-data/out"
export UNIFLOW_TEST_IN_DIR="$PWD/.test-data/in"
export UNIFLOW_SEND_RATE_MBPS=10
bash devops/run-transfer-test.sh --smoke --chaos none --timeout 180
bash devops/run-transfer-test.sh --smoke --chaos mild --timeout 180
```

The smoke suite covers small, empty, nested, and multi-path files, modification,
and deletion. Fixtures contain position-dependent bytes so reordered blocks
fail their checksum. `--chaos mild` injects 3 percent loss, 3 percent bit flips,
and 3 percent misrouting, with 20 percent FEC. Other modes are `loss`, `flip`,
`misroute`, and `harsh` (15 percent each, 50 percent FEC).

Omit `--smoke` for the larger fixture suite; add `--include-1gb --timeout 7200`
for a 1 GiB file. The script builds and starts the stack and removes its
containers on exit unless `--keep-running` is given.

CI builds/tests C++ with GCC 14 and Clang 19, lints/tests Python, validates
every Compose profile, checks DevOps helpers and shell scripts, and runs
Docker smoke transfers with both `none` and `mild` fault modes. It also
validates workflow syntax and uses path filters to select the C++, Python,
and DevOps jobs for pull requests.

The GCC 14 coverage build enforces an 80 percent line coverage minimum.
GitHub Actions uploads the `cpp-coverage-gcc14` and `python-coverage` HTML
reports for seven days, along with test diagnostics. Compiled Linux worker
artifacts are retained for fourteen days.

## Operational limits

- No ACK means TX cannot know whether RX received a complete transfer.
  Loss exceeding FEC/control-message redundancy can leave missing files.
  Keep RX running before TX and choose pacing/repair overhead for the link.
- Version/tombstone state is currently in memory and is lost on RX restart.
  TX does not retain an inventory of files deleted while it was stopped.
  Restart reconciliation and durable tombstones are not provided.
- Version ordering assumes one authoritative TX clock per output tree.
  Monotonic IDs within a process do not solve clock rollback across restarts.
- Incomplete sessions retain temporary disk space and decoder state until a
  newer version supersedes them or RX restarts. There is no stale-session TTL.
- Hashes detect corruption, not sender authenticity. Output trees and IPC
  locations should be dedicated to Uniflow.
- Both services require writable storage. Worker exits are detected by the
  Python supervisor and cause the endpoint to fail; automatic restart/replay
  is not implemented.

See the [Docker environment guide](devops/README.md) for process inspection,
logs, and manual checksum verification.
