# Uniflow Python endpoint processes

This package contains the two Python processes required by the project:

- **TX File Monitor**: watches files, hashes them, RaptorQ-encodes them block-by-block, chooses Sender workers and sends Protobuf packets to three local C++ Senders through three Unix Domain Sockets.
- **RX Session Manager**: accepts Protobuf packets from all three C++ Receivers through one Unix Domain Socket, validates packet hashes, performs RaptorQ reconstruction, writes blocks to disk and verifies the final SHA-256.

The Docker runtime is started through `client.cli`:

```bash
python -m client.cli send /data/out router
python -m client.cli receive /data/in
```

For the complete architecture, Docker commands and end-to-end tests, see the repository-level `README.md`.
