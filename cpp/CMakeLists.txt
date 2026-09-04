cmake_minimum_required(VERSION 3.16)
project(uniflow_net LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(Protobuf_USE_STATIC_LIBS ON)
find_package(Protobuf REQUIRED)
find_package(Threads REQUIRED)

set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../proto/transfer.proto")
protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS "${PROTO_FILE}")

add_executable(
    uniflow-net
    src/main.cpp
    src/sender.cpp
    src/receiver.cpp
    ${PROTO_SRCS}
    ${PROTO_HDRS}
)

target_include_directories(
    uniflow-net
    PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}"
    "${Protobuf_INCLUDE_DIRS}"
)

target_link_libraries(uniflow-net PRIVATE protobuf::libprotobuf Threads::Threads)

target_compile_options(
    uniflow-net
    PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)
