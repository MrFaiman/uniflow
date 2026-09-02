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
RUN mkdir -p python/uniflow/src/uniflow/pb
RUN protoc --python_out=python/uniflow/src/uniflow/pb \
    --pyi_out=python/uniflow/src/uniflow/pb \
    --proto_path=schemas \
    schemas/message.proto

FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv

COPY go/go.mod go/go.sum /app/go/
COPY --from=go-builder /src/go/.bin/uniflow /app/go/.bin/uniflow

COPY python/uniflow /app/python/uniflow
COPY --from=go-builder /src/python/uniflow/src/uniflow/pb /app/python/uniflow/src/uniflow/pb

WORKDIR /app/python/uniflow
RUN uv sync --no-dev

ENV PATH="/app/go/.bin:/app/python/uniflow/.venv/bin:${PATH}"

COPY devops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]