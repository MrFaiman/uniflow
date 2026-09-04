FROM debian:bookworm-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake \
        g++ \
        make \
        libprotobuf-dev \
        protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY proto/ ./proto/
COPY cpp/ ./cpp/

RUN cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build cpp/build --parallel

RUN mkdir -p /generated-python \
    && protoc \
        --proto_path=/src/proto \
        --python_out=/generated-python \
        /src/proto/transfer.proto

FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app/python/client
COPY python/client/ /app/python/client/
COPY --from=builder /generated-python/transfer_pb2.py /app/python/client/src/client/transfer_pb2.py

RUN uv sync --no-dev

COPY --from=builder /src/cpp/build/uniflow-net /usr/local/bin/uniflow-net
COPY devops/entrypoint.sh /usr/local/bin/uniflow-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/uniflow-entrypoint \
    && chmod +x /usr/local/bin/uniflow-entrypoint

ENV PATH="/app/python/client/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/uniflow-entrypoint"]
