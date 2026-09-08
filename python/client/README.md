# Uniflow Python endpoint processes

This package contains the two Python processes required by the project:

- **TX File Monitor**: uses `watchdog` to watch the source tree, waits for files to stabilize, hashes them, RaptorQ-encodes them block-by-block, chooses Sender workers and sends Protobuf packets to three local C++ Senders through three Unix Domain Sockets.
- **RX Session Manager**: accepts Protobuf packets from all three C++ Receivers through one Unix Domain Socket, validates packet hashes, performs RaptorQ reconstruction, writes blocks to disk and verifies the final SHA-256.

The Docker runtime is started through `client.cli`:

```bash
python -m client.cli send /data/out router
python -m client.cli recv /data/in
```

The folder defaults to the current working directory when omitted:

```bash
uniflow send router
uniflow recv
```

For the complete architecture, Docker commands and end-to-end tests, see the repository-level `README.md`.

Run the test suite from this directory:

```bash
uv run pytest
```

Tests report line and branch coverage for the `client` package in the terminal
and generate an HTML report at `htmlcov/index.html`. Generated Protobuf modules
are excluded. Run `uv run pytest --no-cov` to disable coverage for a test run.

GitHub Actions uploads the HTML report from the Python test job as
`python-coverage`, retained for seven days. Download and extract the artifact,
then open `index.html`. This job excludes compiled worker and worker CLI tests,
which run separately in the C++ build jobs.

To include compiled worker integration tests, build the C++ worker first, then
run:

```bash
UNIFLOW_NET_BINARY=../../cpp/build/uniflow-net uv run pytest
```
