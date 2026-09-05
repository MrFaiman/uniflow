#!/bin/sh
set -e
mkdir -p /data/in /data/out

MODE=$1
DIR=$2
TARGET=$3

if [ "$MODE" = "send" ]; then
    echo "Starting uniflow send supervisor (File Monitor + Sender workers)..."
    exec python -m uniflow.cli send "$DIR" "$TARGET"
elif [ "$MODE" = "receive" ] || [ "$MODE" = "recv" ]; then
    echo "Starting uniflow receive supervisor (Receiver workers)..."
    exec python -m uniflow.cli receive "$DIR"
else
    exec "$@"
fi