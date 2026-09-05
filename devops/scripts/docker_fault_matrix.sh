#!/usr/bin/env bash
# Fault matrix against the three-container stack (tx_machine / router / rx_machine).
#
# Proves a clean zero-fault run first, then each fault in isolation, then all
# three together — so a failure can be attributed to one specific condition
# rather than to "the network".
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMPOSE="docker compose -f docker-compose.yaml -f docker-compose.offline.yaml"

# BSD stat: coreutils' gnubin may shadow /usr/bin/stat, where -f means
# something entirely different.
filesize() { /usr/bin/stat -f%z "$1" 2>/dev/null || stat -c%s "$1"; }

FIXTURES="tiny.bin small.bin nested/deep.bin mid5mb.bin just_over_10mb.bin big30mb.bin"

write_fixtures() {
  python3 - <<'EOF'
import os, hashlib, pathlib
out = pathlib.Path("data/out")
os.makedirs(out/"nested", exist_ok=True)
sizes = {"small.bin": 4096, "tiny.bin": 1, "mid5mb.bin": 5*1024*1024,
         "just_over_10mb.bin": 10*1024*1024+1, "big30mb.bin": 30*1024*1024,
         "nested/deep.bin": 2048}
for name, size in sizes.items():
    seed = hashlib.sha256(name.encode()).digest()
    (out/name).write_bytes((seed * (size//len(seed)+1))[:size])
EOF
}

run_case() {
  local label="$1" loss="$2" flip="$3" misroute="$4"
  echo
  echo "==================================================================="
  echo "CASE: $label  (loss=$loss flip=$flip misroute=$misroute)"
  echo "==================================================================="

  $COMPOSE down -v >/dev/null 2>&1
  rm -rf data/in/* data/in/.uniflow data/out/* 2>/dev/null

  PACKET_LOSS="$loss" BIT_FLIP="$flip" MISROUTING="$misroute" \
    $COMPOSE up -d >/dev/null 2>&1
  sleep 12

  write_fixtures

  local waited=0
  while [ "$waited" -lt 240 ]; do
    local missing=0
    for f in $FIXTURES; do [ -f "data/in/$f" ] || missing=1; done
    [ "$missing" = "0" ] && break
    sleep 3; waited=$((waited+3))
  done

  local fails=0
  for f in $FIXTURES; do
    if [ -f "data/in/$f" ]; then
      local a b
      a=$(shasum -a 256 "data/out/$f" | cut -d' ' -f1)
      b=$(shasum -a 256 "data/in/$f" | cut -d' ' -f1)
      if [ "$a" = "$b" ]; then
        printf '  MATCH    %-22s %s bytes\n' "$f" "$(filesize "data/in/$f")"
      else
        printf '  MISMATCH %-22s\n' "$f"; fails=$((fails+1))
      fi
    else
      printf '  MISSING  %-22s\n' "$f"; fails=$((fails+1))
    fi
  done

  # The router only dumps aggregate stats once its sockets go idle, so read
  # them after the transfers settle; otherwise the newest line is an early
  # all-zero dump from before any traffic arrived.
  sleep 12
  echo "  --- router ---"
  $COMPOSE logs router 2>&1 | grep '\[stats\] received' | tail -1 | sed 's/^/  /'
  echo "  --- receivers rejected by CRC ---"
  $COMPOSE logs rx_machine 2>&1 | grep -o 'corrupted_total=[0-9]*' | tail -1 | sed 's/^/  /'

  if [ "$fails" = "0" ]; then echo "  RESULT: PASS"; else echo "  RESULT: FAIL ($fails)"; fi
  return "$fails"
}

total=0
run_case "baseline (no faults)"  0     0     0     || total=$((total+1))
run_case "packet loss only"      0.03  0     0     || total=$((total+1))
run_case "bit flip only"         0     0.03  0     || total=$((total+1))
run_case "misrouting only"       0     0     0.03  || total=$((total+1))
run_case "all faults combined"   0.03  0.03  0.03  || total=$((total+1))

echo
echo "==================================================================="
[ "$total" = "0" ] && echo "ALL CASES PASSED" || echo "$total CASE(S) FAILED"
echo "==================================================================="
$COMPOSE down -v >/dev/null 2>&1
exit "$total"
