#!/bin/sh
set -eu

mkdir -p /data/in /data/out

exec python -m client.cli "$@"
