# Uniflow devops test network

Emulates an unreliable UDP path between a sender and receiver so you can
exercise FEC recovery against packet loss, bit flips, and misrouting.

## Architecture

```
tx_machine (uniflow send) --> router (chaos) --> rx_machine (uniflow receive)
```

- **tx_machine** watches `data/out/` and sends files to hostname `router`
- **router** listens on UDP ports 9000–9002, applies disruptions, forwards to `rx_machine`
- **rx_machine** receives on UDP 9000–9002 and assembles files into `data/in/`

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
