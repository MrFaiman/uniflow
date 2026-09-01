#!/bin/sh
set -e
mkdir -p /data/in /data/out

ACTION=$1
ARG1=$2
ARG2=$3

if [ "$ACTION" = "send" ]; then
    echo "Starting Go uniflow background transport daemon..."
    uniflow &
    
    echo "Starting Python file watcher for sender..."
    exec python -m client.watch "$ARG1" "$ARG2"
elif [ "$ACTION" = "receive" ]; then
    echo "Starting Go uniflow background receiver daemon..."
    uniflow &
    
    echo "Starting Python receiver handler..."
    exec python -m client.watch "$ARG1" "$ARG2"
else
    exec "$@"
fi