if(NOT UNIFLOW_BUILD_TESTS)
    message(FATAL_ERROR "UNIFLOW_ENABLE_COVERAGE requires UNIFLOW_BUILD_TESTS=ON")
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang|AppleClang)$")
    message(FATAL_ERROR "Coverage requires GCC or Clang")
endif()

find_program(UNIFLOW_UV_EXECUTABLE uv REQUIRED)
set(UNIFLOW_COVERAGE_MIN_LINES 0 CACHE STRING "Minimum line coverage percentage")

# Match the coverage reader to the compiler; allow an explicit toolchain override.
if(NOT UNIFLOW_GCOV_EXECUTABLE)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        execute_process(
            COMMAND "${CMAKE_CXX_COMPILER}" -print-prog-name=gcov
            OUTPUT_VARIABLE coverage_reader
            OUTPUT_STRIP_TRAILING_WHITESPACE
            COMMAND_ERROR_IS_FATAL ANY
        )
    else()
        if(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
            execute_process(
                COMMAND xcrun --find llvm-cov
                OUTPUT_VARIABLE llvm_cov
                OUTPUT_STRIP_TRAILING_WHITESPACE
                COMMAND_ERROR_IS_FATAL ANY
            )
        else()
            get_filename_component(compiler_dir "${CMAKE_CXX_COMPILER}" DIRECTORY)
            find_program(llvm_cov llvm-cov HINTS "${compiler_dir}" REQUIRED)
        endif()
        set(coverage_reader "\"${llvm_cov}\" gcov")
    endif()
    set(UNIFLOW_GCOV_EXECUTABLE "${coverage_reader}" CACHE STRING
        "gcov command matching the C++ compiler (e.g. gcov-14 or llvm-cov gcov)")
endif()

# Instrument only our targets, not Catch2 or other third-party libraries.
foreach(coverage_target uniflow_net_core uniflow-net uniflow_net_tests)
    target_compile_options(${coverage_target} PRIVATE --coverage -O0 -g)
    target_link_options(${coverage_target} PRIVATE --coverage)
endforeach()

add_custom_target(coverage
    COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_BINARY_DIR}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/ResetCoverage.cmake"
    COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${CMAKE_BINARY_DIR}"
            --build-config "$<CONFIG>"
            --output-on-failure --parallel 1 --no-tests=error
    COMMAND "${CMAKE_COMMAND}" -E env
            "UNIFLOW_NET_BINARY=$<TARGET_FILE:uniflow-net>"
            "${UNIFLOW_UV_EXECUTABLE}" run
            --project "${CMAKE_CURRENT_SOURCE_DIR}/../python/client" --frozen
            pytest --no-cov -q
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/client/tests/test_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/client/tests/test_worker_cli.py"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_BINARY_DIR}/coverage"
    COMMAND "${UNIFLOW_UV_EXECUTABLE}" tool run --from gcovr==8.6 gcovr
            --root "${CMAKE_CURRENT_SOURCE_DIR}"
            --filter "${CMAKE_CURRENT_SOURCE_DIR}/src/"
            --gcov-executable "${UNIFLOW_GCOV_EXECUTABLE}"
            --fail-under-line "${UNIFLOW_COVERAGE_MIN_LINES}"
            --html-details "${CMAKE_BINARY_DIR}/coverage/index.html"
            --txt --print-summary "${CMAKE_BINARY_DIR}"
    DEPENDS uniflow-net uniflow_net_tests
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Running C++ tests and generating coverage/index.html"
    USES_TERMINAL
    VERBATIM
)
