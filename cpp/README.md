# C++ coverage

With the normal C++ and Python client build prerequisites (including `uv` and
Python 3.13+) installed, run from the repository root:

```sh
cmake -S cpp -B cpp/build-coverage -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DUNIFLOW_BUILD_TESTS=ON \
  -DUNIFLOW_ENABLE_COVERAGE=ON
cmake --build cpp/build-coverage --target coverage --parallel
```

The `coverage` target builds instrumented binaries, clears old counters, runs
CTest plus the Python worker and CLI integration tests against the instrumented
binary, and generates `cpp/build-coverage/coverage/index.html` with source-level
line, function, and branch coverage. It also prints a terminal summary. Reports
cover `cpp/src`, excluding generated protobuf code, dependencies, and tests.
The coverage build and reports are ignored by Git.

Coverage supports GCC, Clang, and AppleClang. The matching gcov/llvm-cov reader
is selected automatically; for a custom toolchain, configure
`-DUNIFLOW_GCOV_EXECUTABLE=gcov-14` or
`-DUNIFLOW_GCOV_EXECUTABLE="llvm-cov-19 gcov"` as appropriate. The first report
run uses `uv tool run` to download the pinned gcovr tool into uv's cache.

CTest runs serially while collecting coverage. Workers handle SIGTERM/SIGINT
through a stop flag and interruptible socket/pacing waits, returning normally
so coverage counters are saved. Python integration tests run with `--no-cov`
here to preserve the separate Python HTML report.

Local runs have no minimum percentage by default; configure
`-DUNIFLOW_COVERAGE_MIN_LINES=80` to enforce an 80 percent line coverage floor.
Normal builds leave `UNIFLOW_ENABLE_COVERAGE` off and require no coverage tools.

GitHub Actions enforces the 80 percent line coverage floor in a separate GCC 14
build and uploads the full HTML report as `cpp-coverage-gcc14`, retained for
seven days. Download
and extract the artifact, then open `index.html`.
