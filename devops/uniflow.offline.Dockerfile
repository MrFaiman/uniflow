# Offline variant of uniflow.Dockerfile.
#
# The normal image downloads protoc-gen-go and the Go module set during the
# build. On networks that intercept TLS (corporate proxies), that fails inside
# the container even though the host can reach the same hosts, because the
# container trust store does not contain the intercepting CA:
#
#   go: ... verifying module: tls: failed to verify certificate:
#       x509: certificate signed by unknown authority
#
# This variant builds with no network access at all. It expects two things to
# have been produced on the host beforehand (see devops/build-offline.sh):
#
#   1. go/vendor/            - go mod vendor
#   2. generated protobuf    - bash scripts/generate-proto.sh all
#
# Behaviour of the resulting image is identical to the normal one.

FROM golang:1.27 AS go-builder

WORKDIR /src
COPY go/ ./go/

WORKDIR /src/go
# -mod=vendor keeps the build entirely offline; the pb/ package is copied in
# pre-generated rather than produced by protoc here.
RUN GOFLAGS=-mod=vendor CGO_ENABLED=0 go build -o .bin/uniflow .

FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv

COPY go/go.mod go/go.sum /app/go/
COPY --from=go-builder /src/go/.bin/uniflow /app/go/.bin/uniflow

COPY python/uniflow /app/python/uniflow

WORKDIR /app/python/uniflow
RUN uv sync --no-dev --offline || uv sync --no-dev

# The Python venv must precede go/.bin: both contain an executable named
# "uniflow", and the supervisor CLI (Python) is the correct entrypoint. With
# the Go binary first, a bare `uniflow` starts a single sender/receiver
# process instead of the three-worker supervisor.
ENV PATH="/app/python/uniflow/.venv/bin:/app/go/.bin:${PATH}"

COPY devops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
