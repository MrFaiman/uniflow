cmake_minimum_required(VERSION 3.28)

add_executable(
    uniflow_net_tests
    test_config.cpp
    test_framing.cpp
    test_log.cpp
    test_rate_limiter.cpp
    test_sockets.cpp
    test_unique_fd.cpp
)

target_link_libraries(
    uniflow_net_tests
    PRIVATE
    uniflow_net_core
    Catch2::Catch2WithMain
)

target_compile_options(
    uniflow_net_tests
    PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
)

include(Catch)
catch_discover_tests(uniflow_net_tests)
