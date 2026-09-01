FROM golang:1.27 AS go-builder

RUN apt-get update && apt-get install -y protobuf-compiler
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest

WORKDIR /src
COPY schemas/ ./schemas/
COPY go/ ./go/

WORKDIR /src/go
RUN go generate ./...
RUN mkdir -p .bin && go build -o .bin/uniflow .

WORKDIR /src
RUN mkdir -p python/client/src/client/pb
RUN protoc --python_out=python/client/src/client/pb \
    --pyi_out=python/client/src/client/pb \
    --proto_path=schemas \
    schemas/message.proto

FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv

COPY go/go.mod go/go.sum /app/go/
COPY --from=go-builder /src/go/.bin/uniflow /app/go/.bin/uniflow
COPY python/client /app/python/client
COPY --from=go-builder /src/python/client/src/client/pb /app/python/client/src/client/pb

WORKDIR /app/python/client
RUN uv sync --no-dev
ENV PATH="/app/python/client/.venv/bin:${PATH}"

COPY devops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]