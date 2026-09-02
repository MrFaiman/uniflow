#!/bin/sh
set -e
mkdir -p /data/in /data/out

MODE=$1
DIR=$2
TARGET=$3

if [ "$MODE" = "send" ]; then
    echo "Starting Go uniflow sender daemon..."
    uniflow send &
    
    echo "Starting Python folder watcher..."
    exec python -m uniflow.watch "$DIR" "$TARGET"
elif [ "$MODE" = "receive" ] || [ "$MODE" = "recv" ]; then
    echo "Starting Go uniflow receiver daemon..."
    exec uniflow recv
else
    exec "$@"
fi