#!/usr/bin/env bash
# Transfer a real 1 GiB file across the three-container stack.
#
# The spec requires support for files up to 1 GB. This exercises that literally
# rather than extrapolating from smaller files, and records peak sender memory
# so the "supports 1 GB" claim can be checked against actual RSS.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMPOSE="docker compose -f docker-compose.yaml -f docker-compose.offline.yaml"
SIZE_BYTES=$((1024 * 1024 * 1024))

filesize() { /usr/bin/stat -f%z "$1" 2>/dev/null || stat -c%s "$1"; }

# Faults default to the compose values; override to test a clean 1 GiB run.
LOSS="${PACKET_LOSS:-0.03}"
FLIP="${BIT_FLIP:-0.03}"
MISROUTE="${MISROUTING:-0.03}"

echo "=== 1 GiB transfer (loss=$LOSS flip=$FLIP misroute=$MISROUTE) ==="
$COMPOSE down -v >/dev/null 2>&1
rm -rf data/in/* data/in/.uniflow data/out/* 2>/dev/null

PACKET_LOSS="$LOSS" BIT_FLIP="$FLIP" MISROUTING="$MISROUTE" \
  $COMPOSE up -d >/dev/null 2>&1
sleep 12

echo "generating 1 GiB fixture..."
python3 - <<EOF
import hashlib, pathlib
size = $SIZE_BYTES
chunk = hashlib.sha256(b"uniflow-1gb").digest() * 4096   # 128 KiB, incompressible-ish
path = pathlib.Path("data/out/onegb.bin")
digest = hashlib.sha256()
written = 0
with open(path, "wb") as fh:
    while written < size:
        take = min(len(chunk), size - written)
        fh.write(chunk[:take]); digest.update(chunk[:take]); written += take
pathlib.Path("/tmp/uniflow_1gb_expected").write_text(digest.hexdigest())
print("expected sha256:", digest.hexdigest())
EOF

echo "waiting for transfer (this takes a while)..."
start=$(date +%s)
peak_tx=0
waited=0
while [ "$waited" -lt 3600 ]; do
  # Track peak sender-side memory while the transfer is in flight.
  mem=$($COMPOSE exec -T tx_machine sh -c \
        "awk '/VmRSS/{s+=\$2} END{print s+0}' /proc/[0-9]*/status" 2>/dev/null | tr -d '\r')
  case "$mem" in ''|*[!0-9]*) mem=0 ;; esac
  [ "$mem" -gt "$peak_tx" ] && peak_tx=$mem

  if [ -f data/in/onegb.bin ] && [ "$(filesize data/in/onegb.bin)" = "$SIZE_BYTES" ]; then
    break
  fi
  sleep 5; waited=$((waited+5))
done
elapsed=$(( $(date +%s) - start ))

echo
echo "=== RESULT ==="
if [ -f data/in/onegb.bin ]; then
  got=$(shasum -a 256 data/in/onegb.bin | cut -d' ' -f1)
  want=$(cat /tmp/uniflow_1gb_expected)
  echo "  size:     $(filesize data/in/onegb.bin) bytes"
  echo "  expected: $want"
  echo "  received: $got"
  [ "$got" = "$want" ] && echo "  SHA-256:  MATCH" || echo "  SHA-256:  MISMATCH"
  echo "  elapsed:  ${elapsed}s"
else
  echo "  onegb.bin NEVER ARRIVED after ${elapsed}s"
fi
echo "  peak TX container RSS (all processes): $((peak_tx / 1024)) MiB"
echo
echo "  --- router ---"
$COMPOSE logs router 2>&1 | grep '\[stats\] received' | tail -1 | sed 's/^/  /'
echo "  --- session manager ---"
$COMPOSE logs rx_machine 2>&1 | grep -E "COMPLETE|STALLED" | tail -3 | sed 's/^/  /'

$COMPOSE down -v >/dev/null 2>&1
