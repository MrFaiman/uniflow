# Uniflow devops test network

Emulates an unreliable UDP path between a sender and receiver so you can
exercise FEC recovery against packet loss, bit flips, and misrouting.

## Architecture

```
tx_machine (uniflow send) --> router (chaos) --> rx_machine (uniflow receive)
```

- **tx_machine** watches `data/out/` and sends files to hostname `router`
- **router** listens on UDP ports 9000–9002, applies disruptions, forwards to `rx_machine`
- **rx_machine** receives on UDP 9000–9002 and assembles files into `data/in/`, preserving relative paths (for example `data/out/sub/file.txt` arrives as `data/in/sub/file.txt`)

## Quick start

```bash
cd devops
docker compose up --build
```

In another terminal, drop a file into the send folder:

```bash
echo hello > data/out/test.txt
ls data/in/
```

## Router logs and statistics

Follow router output:

```bash
docker compose logs -f router
```

Per-packet events:

- `received` — packet arrived at the router
- `dropped` — packet loss applied
- `bit_flip` — byte and bit index corrupted
- `misrouted` — sent to the wrong receiver port
- `forwarded` — delivered to `rx_machine`

Periodic summaries (every 10s by default):

```
[stats] received=120 dropped=4 (3.3%) bit_flipped=3 (2.5%) misrouted=4 (3.3%) forwarded=116 bytes_in=184320 bytes_out=178176
[stats] port=9000 recv=40 drop=1 fwd=38 misroute_out=1
```

A final stats dump is printed on shutdown.

## Environment variables

Router (`docker-compose.yaml` or shell):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `9000` | Starting UDP port (router listens on PORT..PORT+N-1) |
| `PACKET_LOSS` | `0.03` | Probability of dropping a packet |
| `BIT_FLIP` | `0.03` | Probability of flipping one bit |
| `MISROUTING` | `0.03` | Probability of sending to wrong port |
| `STATS_INTERVAL_SEC` | `10` | Stats dump interval; `0` disables periodic dumps |

Uniflow services:

| Variable | Value | Description |
|----------|-------|-------------|
| `PORT` | `9000` | Starting receiver port (workers use 9000–9002) |
| `UNIFLOW_WORKERS` | `3` | Sender/receiver worker count |
| `UNIFLOW_SKIP_BUILD` | `1` | Use prebuilt Go binary in the image |
| `UNIFLOW_WATCH_POLLING` | `1` (tx only) | Poll bind mounts instead of inotify |
| `UNIFLOW_MAX_FILE_BYTES` | `5368709120` (5 GiB) | Maximum file size for coordinated transfer |

### Stress testing

FEC repair overhead is modest (~5% extra symbols per block). For harsh
chaos, raise disruption rates in `docker-compose.yaml`:

```yaml
environment:
  PACKET_LOSS: "0.15"
  BIT_FLIP: "0.15"
  MISROUTING: "0.15"
```

At 15% each, many transfers will fail to assemble — useful for verifying
failure modes.

## Data directories

- `data/out/` — files to send (bind-mounted into tx_machine)
- `data/in/` — received files (bind-mounted into rx_machine)

Only `.gitkeep` files are tracked; transferred files are ignored by git.

## Automated transfer test

Run the full multi-file workload (small, nested, coordinated, 1 GiB, and 1.5 GiB files)
with one command:

```bash
cd devops
./run-transfer-test.sh
```

The runner:

1. Starts `docker compose up -d --build`
2. Waits for tx/rx services to be ready
3. Generates deterministic test files into `data/out/` (see [`scripts/fixtures.manifest`](scripts/fixtures.manifest))
4. Polls `data/in/` until every file matches size and SHA-256, or times out
5. Tears down compose on exit (unless `--keep-running`)

Options:

```bash
./run-transfer-test.sh --keep-running          # leave stack up for debugging
./run-transfer-test.sh --chaos harsh         # 15% loss/flip/misroute
./run-transfer-test.sh --timeout 7200        # 2 hour verification window
UNIFLOW_TEST_TIMEOUT=7200 ./run-transfer-test.sh
```

Requirements:

- ~3+ GiB free disk under `devops/data/` for generated fixtures
- Sufficient RAM for the largest file (sender and receiver load full file contents in memory)
- Docker with enough resources; first run builds images and is slow

Manual steps (generate or verify only):

```bash
python3 scripts/generate_test_files.py
python3 scripts/verify_transfers.py --wait --timeout-sec 3600
```

Example success output ends with `Transfer test passed.` and `All transfers verified.`

If verification times out, try lowering chaos (`--chaos mild`), raising `--timeout`, or
checking `docker compose logs tx_machine rx_machine router`.
