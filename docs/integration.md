# Best-of branch integration

Base: main (00dcbb3)
Branch A: unislop (00cff16)
Branch B: test-three-modes-fixed (5f27eb9)
Target: merge/best-of-A-B, based on main; no commits.

B is an ancestor of A. A adds b683fb9 (empty fixture placeholders) and
00cff16 (modular C++ workers, Python and router changes, CI).
Three-dot stats below describe changes since the merge base, not the final
diff against main. Use git diff main and git status to review the deliverable,
New files have intent-to-add entries so the diff includes them.

## Integration plan and choices

- [x] Fetch all three refs and inventory changes and overlaps.
- [x] Compare main's Go runtime/Python watcher and A/B's C++ workers,
  Python File Monitor/Session Manager, protobuf, router, Compose and CI.
- [x] Create an isolated tree from main; transplant selected live code from A.
- [x] Fix and test the integration's configuration, UDP, watcher and version gaps.
- [x] Remove obsolete Go runtime and schema generation, align env/docs/Compose.
- [x] Build C++, run CTest, lint/test Python and DevOps, validate every profile,
  and exercise real three-path transfers with and without faults.
- [x] Record final results and remaining risks.

A supplies config/framing/sockets/rate-limiter/UniqueFd/logging boundaries,
Catch2 tests, shared Python IPC/constants, typed routing, and multi-stack CI.
B supplies the protocol/runtime already inherited by A: block RaptorQ,
packet and file SHA-256, streaming reconstruction, DELETE redundancy over
three paths, timestamp versions, three-worker supervision, and two-PC profiles
with pacing/FEC. Receiver misroutes remain useful at the shared Session Manager.
A's raw-byte receiver avoids redundant protobuf parsing but must ignore empty
datagrams before framing them.

main supplies the base history, existing fixture verification/helper tests
(unchanged where equivalent), and the requirement to retain directory/move
and polling behavior from its watcher. Port that behavior into the selected
File Monitor rather than carry a second Python/Go execution path.
The on-wire DELETE operation is a file deletion; directory moves/deletes are
represented by their affected files, without a new protocol.

Discard obsolete go/, python/uniflow/, schemas/, legacy Python Go hooks,
and unused Go protobuf generation. Do not import A/B's alternative Go runtime
or wire.proto. Clear accidental .gitkeep payloads. Preserve three independent
sender/receiver ports, UDP only in the TX-to-RX direction, no ACK/NACK.

## Final integration and verification

Additional corrections made after comparing the branches:

- Preserve A's C++ split with B's sender routing, receive forwarding and pacing.
  Ignore empty UDP datagrams, reject malformed/nonfinite numeric config and
  out-of-range worker IDs, and refuse to unlink ordinary files at IPC paths.
- Keep watchdog notifications with B-style recursive reconciliation so lost
  events and directory renames cannot silently leave files unsynchronized.
  Retain deletion history after failed writes.
- Reject noncanonical/reserved paths, oversized or non-ASCII version strings,
  and malformed RaptorQ symbol lengths before native decoding. Close completed
  versions even after the bounded finished-ID cache evicts them.
- Repeat empty metadata on the assigned sender, retain three-path DELETE
  redundancy, and generate monotonically increasing in-process TX versions.
- Restore main's position-sensitive fixture behavior with efficient SHAKE-256
  chunks, plus tests for file hash mismatch, delayed DELETE/WRITE ordering,
  directory reconciliation and real three-sender lifecycle behavior.
- Use one Debian Trixie release for Docker build/runtime libraries and C++20,
  the standard actually needed by A's modules. Keep frozen Python dependencies
  and native Rust build prerequisites. Final image build checks binary startup.
- Replace placeholder health checks with local worker/socket/port checks.
  Optional healthy dependencies preserve all/tx/rx/tx-external isolation and
  ensure all-in-one RX starts before initial TX transmission.
- Grant CI path filtering its PR read permission, retain separate stack jobs,
  and add a real Docker build/fault-transfer smoke job. README and .env.example
  describe actual Compose defaults and distinguish native runtime defaults.

Verified on 2026-09-07:

| Check | Result |
| --- | --- |
| CMake configure/build, Release, C++20, tests enabled | Passed on AppleClang 21 |
| CTest, local UDP/Unix socket tests included | 22 passed |
| Python pytest with UNIFLOW_NET_BINARY set | 54 passed, no skips |
| Ruff lint and format check on src/tests | Passed |
| DevOps router and fixture helper pytest | 14 passed |
| ShellCheck entrypoint, transfer runner, protobuf generation | Passed |
| Compose config: all / tx / rx / tx-external | Correct service sets; valid |
| Docker image builds, C++ shared-library startup check | Passed |
| Docker smoke, chaos none | Small/nested/12 MiB files, modify/delete passed |
| Docker smoke, chaos mild | Small/empty/nested/12 MiB files, modify/delete passed |

The mild run used 20 percent FEC and 10 Mbit/s per sender. Router evidence:
15,070 received, 474 dropped, 471 flipped, 457 misrouted; traffic on all three
ports (4,937 / 5,014 / 5,119 packets). Files passed SHA-256 despite those faults.
Targeted fixes were preceded by failing reproductions on the imported code,
which passed after correction. Both smoke runs removed their
test containers/network afterward; test data is isolated under ignored
.test-data rather than the source branch checkouts.

Not verified: a real two-physical-PC link, a full 1 GiB transfer, harsh-loss
delivery, or remote GitHub Actions execution. Profile configuration and
the complete local Docker path were verified.

Inherited operational limits remain explicit: RX tombstones/version state
do not survive restart; TX cannot discover files deleted while it was stopped;
a single TX clock is assumed; unfinished sessions have no TTL; storage errors
or worker exits can stop an endpoint; finite redundancy cannot guarantee
delivery under arbitrary loss. SHA-256 provides corruption detection, not
sender authentication. No reverse channel or replacement architecture was added.

All work is uncommitted on merge/best-of-A-B at main's original HEAD.
New files have intent-to-add entries so git diff main includes the complete
deliverable; there are no staged content changes. A/, B/, and main/ remain
clean reference checkouts.

## Commits unique to A versus main

```text
00cff16 Refactor C++ workers into testable modules and expand CI for the Python, C++, and devops stack.
b683fb9 Clear accidental test data from .gitkeep files.
5f27eb9 save stable two-PC fault transfer settings
b0f5431 three modes fixed
c8611bc run modes added
c8b1515 feat: add deletion sync and finalize deployment docs
33e18ac docker compose fix to run faster
683e320 docs: finalize deployment and assignment requirements
3daac64 fix: implement three-path fault-tolerant transfer runtime
4af09ce feat: implement graceful shutdown for sender supervisor
26b6e09 feat: go
```

## Commits unique to B versus main

```text
5f27eb9 save stable two-PC fault transfer settings
b0f5431 three modes fixed
c8611bc run modes added
c8b1515 feat: add deletion sync and finalize deployment docs
33e18ac docker compose fix to run faster
683e320 docs: finalize deployment and assignment requirements
3daac64 fix: implement three-path fault-tolerant transfer runtime
4af09ce feat: implement graceful shutdown for sender supervisor
26b6e09 feat: go
```

## Commits unique to main versus A

```text
00dcbb3 Restore uniflow
3e455a2 .
66e5be2 .
227558a .
f53a6ff .
c283578 .
e0de19a .
c7de8fd git push origin mainMerge branch 'main' of https://github.com/MrFaiman/uniflow
62fe736 Fix line length error for ruff in watch.py
548aaf8 Resolve merge conflict in docker-compose.yaml
45146d0 Fix entrypoint and python watcher execution
58e60fb final version
c4903b3 Refactor test connection handling in checksum and path sync tests to use t.Cleanup for closing connections.
a20dc19 Add transfer integrity, directory sync, CLI parsing, and devops multi-file tests.
0c7cd3a .
ec5cd43 final version
2cfcaf4 combined the tx with rx and the router
d9d711b Add protobuf generation to CI and improve PairPool functionality with tests.
17e5735 Replace mock TX/RX with uniflow and derive receiver ports from PORT.
ca64674 Add FLUTE UDP transfer with multi-worker coordination and project tooling.
2c1ed49 Merge branch 'yair' of https://github.com/MrFaiman/uniflow
a99636c .
cf316c1 added router implementation
30f40ab Watch the client folder with watchdog and forward file events over IPC.
80604f6 Add protobuf IPC between the Python client and Go server.
5d16353 init
71d5e79 .
2ebfd0c .
35e9017 added router host
6d4663e added docker and testing
a9597ff Watch the client folder with watchdog and forward file events over IPC.
a0f4b5e fixed the router recive port
c9e3be7 Add protobuf IPC between the Python client and Go server.
9e8f1fe added router implementation
```

## Requested diff stats

`git diff --stat main...unislop`

```text
 .dockerignore                                      |   26 +
 .env.example                                       |   11 +
 .github/workflows/ci.yml                           |  218 +++-
 .gitignore                                         |   12 +
 README.md                                          | 1098 ++++++++++++++++++++
 cpp/CMakeLists.txt                                 |  123 +++
 cpp/cmake/Dependencies.cmake                       |   26 +
 cpp/src/config.cpp                                 |  102 ++
 cpp/src/config.h                                   |   31 +
 cpp/src/framing.cpp                                |   91 ++
 cpp/src/framing.h                                  |   23 +
 cpp/src/log.cpp                                    |  107 ++
 cpp/src/log.h                                      |   62 ++
 cpp/src/main.cpp                                   |   89 ++
 cpp/src/rate_limiter.cpp                           |   30 +
 cpp/src/rate_limiter.h                             |   24 +
 cpp/src/receiver.cpp                               |   86 ++
 cpp/src/runtime.h                                  |    8 +
 cpp/src/sender.cpp                                 |   96 ++
 cpp/src/sockets.cpp                                |  139 +++
 cpp/src/sockets.h                                  |   25 +
 cpp/src/unique_fd.h                                |   56 +
 cpp/tests/CMakeLists.txt                           |   31 +
 cpp/tests/test_config.cpp                          |  121 +++
 cpp/tests/test_framing.cpp                         |   76 ++
 cpp/tests/test_log.cpp                             |   65 ++
 cpp/tests/test_rate_limiter.cpp                    |   20 +
 cpp/tests/test_sockets.cpp                         |   77 ++
 cpp/tests/test_unique_fd.cpp                       |   54 +
 devops/README.md                                   |   69 ++
 devops/config.py                                   |   97 ++
 devops/data/in/.gitkeep                            |    0
 devops/data/out/.gitkeep                           |    0
 devops/docker-compose.yaml                         |  123 +++
 devops/entrypoint.sh                               |    6 +
 devops/router/Dockerfile                           |   11 +
 devops/router/router.py                            |  361 +++++++
 devops/router/test_router.py                       |   82 ++
 devops/run-transfer-test.sh                        |  239 +++++
 devops/scripts/fixtures.manifest                   |   10 +
 devops/scripts/generate_test_files.py              |   65 ++
 devops/scripts/test_modification.py                |   46 +
 devops/scripts/test_transfer_fixtures.py           |   39 +
 devops/scripts/transfer_fixtures.py                |  121 +++
 devops/scripts/verify_transfers.py                 |   91 ++
 devops/uniflow.Dockerfile                          |  117 +++
 go/.gitignore                                      |    3 +
 go/generate.go                                     |    3 +
 go/go.mod                                          |   12 +
 go/go.sum                                          |   14 +
 go/internal/chaos/chaos.go                         |  132 +++
 go/internal/child/child.go                         |  126 +++
 go/internal/config/config.go                       |  158 +++
 go/internal/ipc/framing.go                         |   73 ++
 go/internal/packet/hash.go                         |   45 +
 go/internal/receiver/reassembler.go                |  116 +++
 go/internal/receiver/supervisor.go                 |   45 +
 go/internal/receiver/worker.go                     |  112 ++
 go/internal/sender/supervisor.go                   |  195 ++++
 go/internal/sender/worker.go                       |  120 +++
 go/internal/wire/shard.go                          |  141 +++
 go/main.go                                         |   77 +-
 go/tests/framing_test.go                           |  124 +++
 go/tests/loopback_test.go                          |  223 ++++
 go/tests/packet_hash_test.go                       |  133 +++
 go/tests/reassembler_test.go                       |  149 +++
 go/tests/sender_supervisor_test.go                 |  119 +++
 go/tests/shard_test.go                             |  160 +++
 go/tests/testdata/golden.json                      |    4 +
 proto/transfer.proto                               |    9 +-
 proto/wire.proto                                   |   14 +
 python/client/.python-version                      |    1 -
 python/client/README.md                            |  958 +----------------
 python/client/pyproject.toml                       |   31 +-
 python/client/src/client/__init__.py               |    3 +-
 python/client/src/client/cli.py                    |   53 +-
 python/client/src/client/common/config.py          |   71 +-
 python/client/src/client/common/hash_utils.py      |    2 +-
 python/client/src/client/common/ids.py             |    7 +
 python/client/src/client/common/ipc.py             |   89 +-
 python/client/src/client/common/packet_hash.py     |    2 +-
 python/client/src/client/common/paths.py           |   32 +
 python/client/src/client/common/round_robin.py     |   10 +-
 python/client/src/client/common/transfer_limits.py |    9 +
 python/client/src/client/file_monitor/monitor.py   |  240 ++++-
 .../src/client/file_monitor/packet_router.py       |   17 +-
 .../src/client/file_monitor/raptorq_encoder.py     |  130 ++-
 python/client/src/client/file_monitor/run.py       |  178 +++-
 python/client/src/client/file_monitor/transfer.py  |   68 +-
 .../client/src/client/session_manager/decoder.py   |   11 +-
 .../src/client/session_manager/file_session.py     |   79 +-
 .../client/src/client/session_manager/listener.py  |  128 +--
 .../client/src/client/session_manager/manager.py   |  238 +++--
 .../src/client/session_manager/packet_validator.py |   76 +-
 python/client/src/client/session_manager/run.py    |   71 +-
 python/client/src/client/supervisor.py             |  121 +++
 python/client/src/client/transfer_pb2.py           |    6 +-
 python/client/tests/test_cli.py                    |   35 +-
 python/client/tests/test_config.py                 |   63 +-
 python/client/tests/test_file_monitor.py           |   98 +-
 python/client/tests/test_hash_utils.py             |    2 +-
 python/client/tests/test_ipc.py                    |   76 +-
 python/client/tests/test_packet_router.py          |    2 +-
 python/client/tests/test_paths.py                  |   18 +
 python/client/tests/test_protobuf.py               |    2 +-
 python/client/tests/test_raptorq.py                |   14 +-
 python/client/tests/test_round_robin.py            |    2 +-
 python/client/tests/test_session_manager.py        |  255 ++---
 .../client/tests/test_session_manager_listener.py  |  142 +--
 python/client/tests/test_transfer.py               |   94 +-
 python/client/uv.lock                              |  183 ++--
 scripts/generate-proto.sh                          |   42 +
 112 files changed, 8216 insertions(+), 2154 deletions(-)
```

`git diff --stat main...test-three-modes-fixed`

```text
 .dockerignore                                      |   16 +
 .env.example                                       |    9 +
 .github/workflows/ci.yml                           |   87 +-
 .gitignore                                         |   12 +
 README.md                                          | 1068 ++++++++++++++++++++
 cpp/CMakeLists.txt                                 |   39 +
 cpp/src/common.h                                   |  155 +++
 cpp/src/main.cpp                                   |   33 +
 cpp/src/receiver.cpp                               |  114 +++
 cpp/src/runtime.h                                  |    8 +
 cpp/src/sender.cpp                                 |  186 ++++
 devops/README.md                                   |   54 +
 devops/config.py                                   |  108 ++
 devops/data/in/.gitkeep                            |    1 +
 devops/data/out/.gitkeep                           |    1 +
 devops/docker-compose.yaml                         |  107 ++
 devops/entrypoint.sh                               |    6 +
 devops/router/Dockerfile                           |    8 +
 devops/router/router.py                            |  460 +++++++++
 devops/run-transfer-test.sh                        |  227 +++++
 devops/scripts/fixtures.manifest                   |   10 +
 devops/scripts/generate_test_files.py              |   65 ++
 devops/scripts/test_modification.py                |   46 +
 devops/scripts/test_transfer_fixtures.py           |   39 +
 devops/scripts/transfer_fixtures.py                |  121 +++
 devops/scripts/verify_transfers.py                 |   91 ++
 devops/uniflow.Dockerfile                          |   47 +
 go/.gitignore                                      |    3 +
 go/generate.go                                     |    3 +
 go/go.mod                                          |   12 +
 go/go.sum                                          |   14 +
 go/internal/chaos/chaos.go                         |  132 +++
 go/internal/child/child.go                         |  126 +++
 go/internal/config/config.go                       |  158 +++
 go/internal/ipc/framing.go                         |   73 ++
 go/internal/packet/hash.go                         |   45 +
 go/internal/receiver/reassembler.go                |  116 +++
 go/internal/receiver/supervisor.go                 |   45 +
 go/internal/receiver/worker.go                     |  112 ++
 go/internal/sender/supervisor.go                   |  195 ++++
 go/internal/sender/worker.go                       |  120 +++
 go/internal/wire/shard.go                          |  141 +++
 go/main.go                                         |   77 +-
 go/tests/framing_test.go                           |  124 +++
 go/tests/loopback_test.go                          |  223 ++++
 go/tests/packet_hash_test.go                       |  133 +++
 go/tests/reassembler_test.go                       |  149 +++
 go/tests/sender_supervisor_test.go                 |  119 +++
 go/tests/shard_test.go                             |  160 +++
 go/tests/testdata/golden.json                      |    4 +
 proto/transfer.proto                               |    9 +-
 proto/wire.proto                                   |   14 +
 python/client/.python-version                      |    1 -
 python/client/README.md                            |  958 +-----------------
 python/client/pyproject.toml                       |   30 +-
 python/client/src/client/__init__.py               |    3 +-
 python/client/src/client/cli.py                    |   53 +-
 python/client/src/client/common/config.py          |   68 +-
 python/client/src/client/common/go_daemon.py       |  104 ++
 python/client/src/client/common/ipc.py             |   60 +-
 python/client/src/client/common/paths.py           |   32 +
 python/client/src/client/file_monitor/monitor.py   |   95 +-
 .../src/client/file_monitor/packet_router.py       |    2 +-
 .../src/client/file_monitor/raptorq_encoder.py     |  122 ++-
 python/client/src/client/file_monitor/run.py       |  176 +++-
 python/client/src/client/file_monitor/transfer.py  |   69 +-
 .../src/client/session_manager/file_session.py     |   77 +-
 .../client/src/client/session_manager/listener.py  |  118 +--
 .../client/src/client/session_manager/manager.py   |  231 +++--
 .../src/client/session_manager/packet_validator.py |   77 +-
 python/client/src/client/session_manager/run.py    |   71 +-
 python/client/src/client/supervisor.py             |  121 +++
 python/client/src/client/transfer_pb2.py           |    6 +-
 python/client/src/client/watch.py                  |   59 ++
 python/client/tests/test_cli.py                    |   35 +-
 python/client/tests/test_config.py                 |   63 +-
 python/client/tests/test_file_monitor.py           |   49 +-
 python/client/tests/test_go_daemon.py              |  101 ++
 python/client/tests/test_ipc.py                    |   65 +-
 python/client/tests/test_paths.py                  |   17 +
 python/client/tests/test_raptorq.py                |   11 +-
 python/client/tests/test_session_manager.py        |  254 ++---
 .../client/tests/test_session_manager_listener.py  |  125 +--
 python/client/tests/test_transfer.py               |   94 +-
 python/client/uv.lock                              |  166 +--
 scripts/generate-proto.sh                          |   42 +
 86 files changed, 6870 insertions(+), 2110 deletions(-)
```

## Overlapping files

These 82 paths change on both branches relative to the merge base.
C++ implementation changes in A were compared with the equivalent B common.h
and worker logic; main has no C++ implementation. Python and deployment
changes were compared against both branch tips and main's corresponding paths.
Go paths are discarded as inactive for this architecture.

```text
.dockerignore
.env.example
.github/workflows/ci.yml
.gitignore
README.md
cpp/CMakeLists.txt
cpp/src/main.cpp
cpp/src/receiver.cpp
cpp/src/runtime.h
cpp/src/sender.cpp
devops/README.md
devops/config.py
devops/data/in/.gitkeep
devops/data/out/.gitkeep
devops/docker-compose.yaml
devops/entrypoint.sh
devops/router/Dockerfile
devops/router/router.py
devops/run-transfer-test.sh
devops/scripts/fixtures.manifest
devops/scripts/generate_test_files.py
devops/scripts/test_modification.py
devops/scripts/test_transfer_fixtures.py
devops/scripts/transfer_fixtures.py
devops/scripts/verify_transfers.py
devops/uniflow.Dockerfile
go/.gitignore
go/generate.go
go/go.mod
go/go.sum
go/internal/chaos/chaos.go
go/internal/child/child.go
go/internal/config/config.go
go/internal/ipc/framing.go
go/internal/packet/hash.go
go/internal/receiver/reassembler.go
go/internal/receiver/supervisor.go
go/internal/receiver/worker.go
go/internal/sender/supervisor.go
go/internal/sender/worker.go
go/internal/wire/shard.go
go/main.go
go/tests/framing_test.go
go/tests/loopback_test.go
go/tests/packet_hash_test.go
go/tests/reassembler_test.go
go/tests/sender_supervisor_test.go
go/tests/shard_test.go
go/tests/testdata/golden.json
proto/transfer.proto
proto/wire.proto
python/client/.python-version
python/client/README.md
python/client/pyproject.toml
python/client/src/client/__init__.py
python/client/src/client/cli.py
python/client/src/client/common/config.py
python/client/src/client/common/ipc.py
python/client/src/client/common/paths.py
python/client/src/client/file_monitor/monitor.py
python/client/src/client/file_monitor/packet_router.py
python/client/src/client/file_monitor/raptorq_encoder.py
python/client/src/client/file_monitor/run.py
python/client/src/client/file_monitor/transfer.py
python/client/src/client/session_manager/file_session.py
python/client/src/client/session_manager/listener.py
python/client/src/client/session_manager/manager.py
python/client/src/client/session_manager/packet_validator.py
python/client/src/client/session_manager/run.py
python/client/src/client/supervisor.py
python/client/src/client/transfer_pb2.py
python/client/tests/test_cli.py
python/client/tests/test_config.py
python/client/tests/test_file_monitor.py
python/client/tests/test_ipc.py
python/client/tests/test_paths.py
python/client/tests/test_raptorq.py
python/client/tests/test_session_manager.py
python/client/tests/test_session_manager_listener.py
python/client/tests/test_transfer.py
python/client/uv.lock
scripts/generate-proto.sh
```
