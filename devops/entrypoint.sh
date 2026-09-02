#!/bin/sh
set -e
mkdir -p /data/in /data/out

<<<<<<< HEAD
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
=======
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
>>>>>>> yair
else
    exec "$@"
fi