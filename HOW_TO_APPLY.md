# How to apply this patch set

This archive is an **overlay** for the existing `MrFaiman/uniflow` repository.
It contains every file that I changed or added for the corrected runtime architecture.

## 1. Create a safety branch

```bash
git checkout main
git pull
git checkout -b fix/trio-runtime
```

## 2. Copy the overlay into the repository root

Extract the archive and copy its contents over the repository, preserving paths.
Existing files with the same paths should be replaced.

On Linux/WSL, make the shell scripts executable:

```bash
chmod +x devops/entrypoint.sh devops/run-transfer-test.sh scripts/generate-proto.sh
```

## 3. Generate Python Protobuf

```bash
bash scripts/generate-proto.sh python
```

## 4. Run Python checks

```bash
cd python/client
uv sync --all-groups
uv run ruff check src tests
uv run pytest
cd ../..
```

## 5. Build C++

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --parallel
```

## 6. Run the complete Docker system

```bash
cd devops
./run-transfer-test.sh --chaos none
./run-transfer-test.sh --chaos loss
./run-transfer-test.sh --chaos flip
./run-transfer-test.sh --chaos misroute
./run-transfer-test.sh --chaos mild
```

For the explicit 1 GiB requirement:

```bash
./run-transfer-test.sh --chaos none --include-1gb --timeout 7200
```

## 7. Runtime process evidence

While Compose is running:

```bash
docker compose top tx_machine
docker compose top rx_machine
```

TX must show the Python File Monitor plus 3 `uniflow-net send` C++ processes.
RX must show the Python Session Manager plus 3 `uniflow-net recv` C++ processes.

## Important

The existing `go/`, `python/uniflow/`, and `schemas/` trees are legacy implementations after this change. They are not used by the corrected Docker runtime. Do not delete them until the new runtime has passed the full Docker tests on your machine; after that, removing them is a reasonable cleanup step.
