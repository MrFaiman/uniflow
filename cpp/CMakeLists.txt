cmake_minimum_required(VERSION 3.28)
project(uniflow_net LANGUAGES CXX)

option(UNIFLOW_BUILD_TESTS "Build C++ unit tests" ON)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# No C++ modules are used; do not require Clang's optional dependency scanner.
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

include(cmake/Dependencies.cmake)

find_package(Threads REQUIRED)
find_package(Protobuf CONFIG QUIET)
if(NOT Protobuf_FOUND)
    find_package(protobuf CONFIG QUIET)
endif()
if(NOT Protobuf_FOUND AND NOT protobuf_FOUND)
    find_package(Protobuf REQUIRED)
endif()

find_package(absl CONFIG QUIET)

set(PROTO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../proto")
cmake_path(ABSOLUTE_PATH PROTO_DIR NORMALIZE)
set(PROTO_FILE "${PROTO_DIR}/transfer.proto")
set(PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${PROTO_GEN_DIR}")

set(PROTO_SRCS "${PROTO_GEN_DIR}/transfer.pb.cc")
set(PROTO_HDRS "${PROTO_GEN_DIR}/transfer.pb.h")

if(NOT Protobuf_PROTOC_EXECUTABLE AND TARGET protobuf::protoc)
    get_target_property(Protobuf_PROTOC_EXECUTABLE protobuf::protoc LOCATION)
endif()
if(NOT Protobuf_PROTOC_EXECUTABLE)
    find_program(Protobuf_PROTOC_EXECUTABLE protoc REQUIRED)
endif()

add_custom_command(
    OUTPUT "${PROTO_SRCS}" "${PROTO_HDRS}"
    COMMAND "${Protobuf_PROTOC_EXECUTABLE}"
            --proto_path=${PROTO_DIR}
            --cpp_out=${PROTO_GEN_DIR}
            ${PROTO_FILE}
    DEPENDS "${PROTO_FILE}"
    COMMENT "Generating C++ protobuf sources from transfer.proto"
    VERBATIM
)

add_library(
    uniflow_net_core
    src/config.cpp
    src/framing.cpp
    src/log.cpp
    src/rate_limiter.cpp
    src/receiver.cpp
    src/sender.cpp
    src/sockets.cpp
    "${PROTO_SRCS}"
    "${PROTO_HDRS}"
)

target_include_directories(
    uniflow_net_core
    PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${PROTO_GEN_DIR}"
)

if(TARGET protobuf::libprotobuf)
    target_link_libraries(uniflow_net_core PUBLIC protobuf::libprotobuf Threads::Threads)
elseif(TARGET protobuf::protobuf)
    target_link_libraries(uniflow_net_core PUBLIC protobuf::protobuf Threads::Threads)
else()
    target_include_directories(uniflow_net_core PUBLIC ${Protobuf_INCLUDE_DIRS})
    target_link_libraries(uniflow_net_core PUBLIC ${Protobuf_LIBRARIES} Threads::Threads)
endif()

if(absl_FOUND)
    target_link_libraries(
        uniflow_net_core
        PUBLIC
        absl::base
        absl::log_internal_check_op
        absl::strings
        absl::synchronization
    )
endif()

target_compile_options(
    uniflow_net_core
    PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
)

add_executable(uniflow-net src/main.cpp)

target_link_libraries(
    uniflow-net
    PRIVATE
    uniflow_net_core
    argparse
)

target_compile_options(
    uniflow-net
    PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
)

if(UNIFLOW_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
