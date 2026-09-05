#!/usr/bin/env bash
# Prepare the inputs the offline Docker build needs, using the host toolchain.
#
# The normal image fetches protoc-gen-go and the Go module set at build time.
# Where TLS is intercepted that fails inside the container even though the
# host can reach the same hosts. Generating protobuf code and vendoring the
# modules here lets the image build with no network access.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for tool in go protoc; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "error: $tool is required on the host for the offline build" >&2
    exit 1
  }
done

echo "==> generating protobuf code"
bash "$root/scripts/generate-proto.sh" all

echo "==> vendoring Go modules"
(cd "$root/go" && go mod vendor)

echo
echo "Ready. Bring the three-machine stack up with:"
echo "  cd devops"
echo "  docker compose -f docker-compose.yaml -f docker-compose.offline.yaml up --build"
