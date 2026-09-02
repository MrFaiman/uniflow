#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-all}"

generate_go() {
  (cd "$root/go" && go generate ./...)
}

generate_python() {
  local out="$root/python/uniflow/src/uniflow/pb"
  mkdir -p "$out"
  protoc \
    --python_out="$out" \
    --pyi_out="$out" \
    --proto_path="$root/schemas" \
    "$root/schemas/message.proto"
}

case "$target" in
  go) generate_go ;;
  python) generate_python ;;
  all)
    generate_go
    generate_python
    ;;
  *)
    echo "usage: $0 [go|python|all]" >&2
    exit 1
    ;;
esac
