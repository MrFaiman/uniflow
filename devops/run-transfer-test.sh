#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$ROOT/scripts"
OUT_DIR="$ROOT/data/out"
IN_DIR="$ROOT/data/in"
TIMEOUT_SEC="${UNIFLOW_TEST_TIMEOUT:-3600}"
KEEP_RUNNING=0
CHAOS="mild"

usage() {
  cat <<'EOF'
Usage: run-transfer-test.sh [options]

  Automated devops transfer test: start compose, generate files, verify receipt.

Options:
  --keep-running    Leave docker compose running after the test
  --chaos mild      Default router disruption rates (3%)
  --chaos harsh     Raise PACKET_LOSS, BIT_FLIP, MISROUTING to 15%
  --timeout SEC     Verification timeout (default: 3600)
  -h, --help        Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-running) KEEP_RUNNING=1; shift ;;
    --chaos)
      CHAOS="${2:-}"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

clean_data_dir() {
  local dir=$1
  mkdir -p "$dir"
  find "$dir" -mindepth 1 ! -name '.gitkeep' -print0 | xargs -0 rm -rf
}

teardown() {
  if [[ "$KEEP_RUNNING" -eq 0 ]]; then
    docker compose -f "$ROOT/docker-compose.yaml" down
  fi
}

wait_for_services() {
  local attempt
  for attempt in $(seq 1 90); do
    if docker compose -f "$ROOT/docker-compose.yaml" logs tx_machine 2>&1 | grep -q "watching" \
      && docker compose -f "$ROOT/docker-compose.yaml" logs rx_machine 2>&1 | grep -q "receiver listening"; then
      echo "Services ready."
      return 0
    fi
    echo "Waiting for services... ($attempt/90)"
    sleep 2
  done
  echo "Timed out waiting for tx/rx services." >&2
  return 1
}

export PACKET_LOSS BIT_FLIP MISROUTING
case "$CHAOS" in
  mild)
    PACKET_LOSS="0.03"
    BIT_FLIP="0.03"
    MISROUTING="0.03"
    ;;
  harsh)
    PACKET_LOSS="0.15"
    BIT_FLIP="0.15"
    MISROUTING="0.15"
    ;;
  *)
    echo "unknown chaos mode: $CHAOS (use mild or harsh)" >&2
    exit 1
    ;;
esac

trap teardown EXIT

cd "$ROOT"
echo "Starting docker compose (chaos=$CHAOS)..."
docker compose up -d --build

wait_for_services

echo "Cleaning receive directory..."
clean_data_dir "$IN_DIR"

echo "Generating test files..."
python3 "$SCRIPTS/generate_test_files.py" --out-dir "$OUT_DIR"

echo "Verifying transfers (timeout=${TIMEOUT_SEC}s)..."
if python3 "$SCRIPTS/verify_transfers.py" \
  --receive-dir "$IN_DIR" \
  --sidecar "$OUT_DIR/.manifest.sha256" \
  --wait \
  --timeout-sec "$TIMEOUT_SEC"; then
  echo "Transfer test passed."
  if [[ "$KEEP_RUNNING" -eq 1 ]]; then
    trap - EXIT
    echo "Leaving compose running (--keep-running)."
  fi
  exit 0
fi

echo "Transfer test failed." >&2
exit 1
