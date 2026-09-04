#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-all}"

generate_go() {
  (cd "$root/go" && go generate ./...)
}

generate_python() {
  local out="$root/python/client/src/client"
  mkdir -p "$out"
  protoc \
    --proto_path="$root/proto" \
    --python_out="$out" \
    "$root/proto/transfer.proto"
}

generate_cpp() {
  local out="$root/cpp/generated"
  mkdir -p "$out"
  protoc \
    --proto_path="$root/proto" \
    --cpp_out="$out" \
    "$root/proto/transfer.proto"
}

case "$target" in
  go) generate_go ;;
  python) generate_python ;;
  cpp) generate_cpp ;;
  all)
    generate_go
    generate_python
    generate_cpp
    ;;
  *)
    echo "usage: $0 [go|python|cpp|all]" >&2
    exit 1
    ;;
esac
