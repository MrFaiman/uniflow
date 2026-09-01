FROM golang:1.27 AS go-builder

WORKDIR /src
COPY go/ ./
RUN mkdir -p .bin && go build -o .bin/uniflow .

FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY go/go.mod go/go.sum /app/go/
COPY --from=go-builder /src/.bin/uniflow /app/go/.bin/uniflow

COPY python/uniflow /app/python/uniflow
WORKDIR /app/python/uniflow
RUN uv sync --no-dev

ENV PATH="/app/python/uniflow/.venv/bin:${PATH}"

COPY devops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
