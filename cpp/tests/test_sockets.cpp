#include "sockets.h"

#include <catch2/catch_test_macros.hpp>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>

TEST_CASE("Unix server refuses to replace regular files", "[sockets]") {
    const auto path = std::filesystem::temp_directory_path() /
        ("uniflow-regular-" + std::to_string(::getpid()));
    std::ofstream(path) << "keep";
    CHECK_THROWS(uniflow_net::create_unix_server(path.string()));
    CHECK(std::filesystem::is_regular_file(path));
    std::filesystem::remove(path);
}

TEST_CASE("create_unix_server accepts a local connection", "[sockets]") {
    const auto path =
        (std::filesystem::temp_directory_path() / "uniflow-test-unix-server.sock").string();
    ::unlink(path.c_str());

    auto server = uniflow_net::create_unix_server(path);
    REQUIRE(server);

    std::thread client([&] {
        const int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
        REQUIRE(fd >= 0);

        sockaddr_un address{};
        address.sun_family = AF_UNIX;
        REQUIRE(path.size() < sizeof(address.sun_path));
        std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
        REQUIRE(::connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0);
        ::close(fd);
    });

    const int connection = ::accept(server.get(), nullptr, nullptr);
    REQUIRE(connection >= 0);
    ::close(connection);
    client.join();
    ::unlink(path.c_str());
}

TEST_CASE("create_udp_listener binds an ephemeral localhost port", "[sockets]") {
    auto listener = uniflow_net::create_udp_listener(0, 256 * 1024);
    REQUIRE(listener);

    sockaddr_in bound{};
    socklen_t length = sizeof(bound);
    REQUIRE(::getsockname(listener.get(), reinterpret_cast<sockaddr*>(&bound), &length) == 0);
    REQUIRE(ntohs(bound.sin_port) != 0);
}

TEST_CASE("resolve_udp_target resolves localhost", "[sockets]") {
    const sockaddr_in address = uniflow_net::resolve_udp_target("127.0.0.1", 9000);
    REQUIRE(address.sin_family == AF_INET);
    REQUIRE(ntohs(address.sin_port) == 9000);
    REQUIRE(address.sin_addr.s_addr == htonl(INADDR_LOOPBACK));
}

TEST_CASE("connect_unix_with_retry connects once server is ready", "[sockets]") {
    const auto path =
        (std::filesystem::temp_directory_path() / "uniflow-test-unix-connect.sock").string();
    ::unlink(path.c_str());

    std::thread server([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        auto listener = uniflow_net::create_unix_server(path);
        const int connection = ::accept(listener.get(), nullptr, nullptr);
        REQUIRE(connection >= 0);
        ::close(connection);
    });

    auto client = uniflow_net::connect_unix_with_retry(path);
    REQUIRE(client);
    server.join();
    ::unlink(path.c_str());
}
