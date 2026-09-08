# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-trixie AS cpp-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cmake \
        git \
        g++ \
        ninja-build \
        libprotobuf-dev \
        protobuf-compiler

WORKDIR /src
COPY proto/ ./proto/
COPY cpp/ ./cpp/

RUN cmake -S cpp -B cpp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DUNIFLOW_BUILD_TESTS=OFF \
    && cmake --build cpp/build

# Stage the system protobuf shared library used by the dynamically linked binary.
# Builder and runtime use the same Debian release and protobuf ABI.
RUN mkdir -p /opt/uniflow/lib \
    && protobuf_lib="$(ldd /src/cpp/build/uniflow-net \
        | awk '/libprotobuf\.so/ { print $3; exit }')" \
    && test -n "$protobuf_lib" \
    && real_lib="$(readlink -f "$protobuf_lib")" \
    && soname="$(basename "$protobuf_lib")" \
    && cp -aL "$real_lib" "/opt/uniflow/lib/$(basename "$real_lib")" \
    && ln -sfn "$(basename "$real_lib")" "/opt/uniflow/lib/$soname" \
    && ls -l /opt/uniflow/lib

RUN mkdir -p /generated-python \
    && protoc \
        --proto_path=/src/proto \
        --python_out=/generated-python \
        /src/proto/transfer.proto

FROM python:3.13-slim-trixie AS python-deps

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/python/client/.venv \
    PATH="/root/.cargo/bin:${PATH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable --profile minimal

WORKDIR /app/python/client
COPY python/client/pyproject.toml python/client/uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --frozen --no-dev --no-install-project

COPY python/client/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --frozen --no-dev

FROM python:3.13-slim-trixie AS runtime

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        libstdc++6 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-deps /app/python/client /app/python/client
COPY --from=cpp-builder /generated-python/transfer_pb2.py \
    /app/python/client/src/client/transfer_pb2.py
COPY --from=cpp-builder /src/cpp/build/uniflow-net /usr/local/bin/uniflow-net
COPY --from=cpp-builder /opt/uniflow/lib/ /usr/local/lib/uniflow/
COPY devops/entrypoint.sh /usr/local/bin/uniflow-entrypoint
COPY devops/healthcheck.py /app/healthcheck.py

RUN sed -i 's/\r$//' /usr/local/bin/uniflow-entrypoint \
    && chmod +x /usr/local/bin/uniflow-entrypoint /usr/local/bin/uniflow-net \
    && mkdir -p /data/in /data/out /var/log/uniflow \
    && ldconfig /usr/local/lib/uniflow \
    && /usr/local/bin/uniflow-net --help

ENV PATH="/app/python/client/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    UNIFLOW_NET_BINARY=/usr/local/bin/uniflow-net \
    LD_LIBRARY_PATH=/usr/local/lib/uniflow

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/uniflow-entrypoint"]
