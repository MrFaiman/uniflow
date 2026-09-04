#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$ROOT/scripts"
OUT_DIR="$ROOT/data/out"
IN_DIR="$ROOT/data/in"
TIMEOUT_SEC="${UNIFLOW_TEST_TIMEOUT:-3600}"
KEEP_RUNNING=0
CHAOS="none"
INCLUDE_1GB=0

usage() {
  cat <<'EOF'
Usage: run-transfer-test.sh [options]

Options:
  --keep-running    Leave Docker Compose running after the test
  --chaos none      No injected network faults (default)
  --chaos loss      3% packet loss only
  --chaos flip      3% bit flips only
  --chaos misroute  3% misrouting only
  --chaos mild      3% loss, 3% bit flips, 3% misrouting
  --chaos harsh     15% loss, 15% bit flips, 15% misrouting, 50% FEC repair
  --include-1gb     Also generate and verify the 1 GiB fixture
  --timeout SEC     Verification timeout (default: 3600)
  -h, --help        Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-running)
      KEEP_RUNNING=1
      shift
      ;;
    --chaos)
      CHAOS="${2:-}"
      shift 2
      ;;
    --include-1gb)
      INCLUDE_1GB=1
      shift
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

  find "$dir" \
    -mindepth 1 \
    ! -name '.gitkeep' \
    -print0 | xargs -0 -r rm -rf
}

teardown() {
  if [[ "$KEEP_RUNNING" -eq 0 ]]; then
    docker compose -f "$ROOT/docker-compose.yaml" down
  fi
}

wait_for_services() {
  local attempt

  for attempt in $(seq 1 120); do
    local tx_logs
    local rx_logs
    local tx_senders
    local rx_receivers

    tx_logs="$(
      docker compose \
        -f "$ROOT/docker-compose.yaml" \
        logs tx_machine 2>&1 || true
    )"

    rx_logs="$(
      docker compose \
        -f "$ROOT/docker-compose.yaml" \
        logs rx_machine 2>&1 || true
    )"

    tx_senders="$(
      grep -c "Started send worker" <<<"$tx_logs" || true
    )"

    rx_receivers="$(
      grep -c "Started recv worker" <<<"$rx_logs" || true
    )"

    if [[ "$tx_senders" -ge 3 && "$rx_receivers" -ge 3 ]] \
      && grep -q "Watching folder:" <<<"$tx_logs" \
      && grep -q "Receiving files into:" <<<"$rx_logs"; then

      echo "All required TX/RX processes are running."
      echo "TX Senders: $tx_senders"
      echo "RX Receivers: $rx_receivers"

      return 0
    fi

    echo \
      "Waiting for services... ($attempt/120) " \
      "- senders=$tx_senders receivers=$rx_receivers"

    sleep 1
  done

  echo "Timed out waiting for the required processes." >&2

  docker compose \
    -f "$ROOT/docker-compose.yaml" \
    logs >&2 || true

  return 1
}

export PACKET_LOSS
export BIT_FLIP
export MISROUTING
export UNIFLOW_FEC_REPAIR_PERCENT

case "$CHAOS" in
  none)
    PACKET_LOSS="0"
    BIT_FLIP="0"
    MISROUTING="0"
    UNIFLOW_FEC_REPAIR_PERCENT="20"
    ;;

  loss)
    PACKET_LOSS="0.03"
    BIT_FLIP="0"
    MISROUTING="0"
    UNIFLOW_FEC_REPAIR_PERCENT="20"
    ;;

  flip)
    PACKET_LOSS="0"
    BIT_FLIP="0.03"
    MISROUTING="0"
    UNIFLOW_FEC_REPAIR_PERCENT="20"
    ;;

  misroute)
    PACKET_LOSS="0"
    BIT_FLIP="0"
    MISROUTING="0.03"
    UNIFLOW_FEC_REPAIR_PERCENT="20"
    ;;

  mild)
    PACKET_LOSS="0.03"
    BIT_FLIP="0.03"
    MISROUTING="0.03"
    UNIFLOW_FEC_REPAIR_PERCENT="20"
    ;;

  harsh)
    PACKET_LOSS="0.15"
    BIT_FLIP="0.15"
    MISROUTING="0.15"
    UNIFLOW_FEC_REPAIR_PERCENT="50"
    ;;

  *)
    echo "unknown chaos mode: $CHAOS" >&2
    exit 1
    ;;
esac

trap teardown EXIT

clean_data_dir "$OUT_DIR"
clean_data_dir "$IN_DIR"

cd "$ROOT"

echo "Starting Docker Compose (chaos=$CHAOS)..."

docker compose up -d --build

wait_for_services

echo "Generating deterministic transfer fixtures..."

GEN_ARGS=(--out-dir "$OUT_DIR")

if [[ "$INCLUDE_1GB" -eq 1 ]]; then
  GEN_ARGS+=(--include-1gb)
fi

python \
  "$SCRIPTS/generate_test_files.py" \
  "${GEN_ARGS[@]}"

echo "Verifying transfers with SHA-256..."

if python \
  "$SCRIPTS/verify_transfers.py" \
  --receive-dir "$IN_DIR" \
  --sidecar "$OUT_DIR/.manifest.sha256" \
  --wait \
  --timeout-sec "$TIMEOUT_SEC"; then

  echo "Initial transfer suite passed."
  echo "Testing file modification..."

  python \
    "$SCRIPTS/test_modification.py" \
    --source "$OUT_DIR/tiny.txt" \
    --received "$IN_DIR/tiny.txt" \
    --timeout-sec 300

  echo "Transfer and modification tests passed."

  docker compose \
    -f "$ROOT/docker-compose.yaml" \
    logs router | tail -n 40 || true

  if [[ "$KEEP_RUNNING" -eq 1 ]]; then
    trap - EXIT
    echo "Leaving Compose running (--keep-running)."
  fi

  exit 0
fi

echo "Transfer test failed." >&2

docker compose \
  -f "$ROOT/docker-compose.yaml" \
  logs >&2 || true

exit 1