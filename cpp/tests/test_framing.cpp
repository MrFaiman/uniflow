#include "framing.h"
#include "unique_fd.h"

#include <catch2/catch_test_macros.hpp>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace {

struct SocketPair {
    uniflow_net::UniqueFd left;
    uniflow_net::UniqueFd right;
};

[[nodiscard]] SocketPair make_socket_pair() {
    std::array<int, 2> fds{-1, -1};
    REQUIRE(::socketpair(AF_UNIX, SOCK_STREAM, 0, fds.data()) == 0);
    return SocketPair{
        .left = uniflow_net::UniqueFd{fds[0]},
        .right = uniflow_net::UniqueFd{fds[1]},
    };
}

}  // namespace

TEST_CASE("frame round-trip over socketpair", "[framing]") {
    auto sockets = make_socket_pair();
    const std::string payload = "hello-uniflow";

    uniflow_net::write_frame(sockets.left, payload);
    const auto decoded = uniflow_net::read_frame(sockets.right);
    REQUIRE(decoded.has_value());
    REQUIRE(*decoded == payload);
}

TEST_CASE("read_frame returns nullopt on clean EOF", "[framing]") {
    auto sockets = make_socket_pair();
    sockets.left.reset();
    const auto decoded = uniflow_net::read_frame(sockets.right);
    REQUIRE_FALSE(decoded.has_value());
}

TEST_CASE("write_frame rejects empty and oversized payloads", "[framing]") {
    auto sockets = make_socket_pair();
    REQUIRE_THROWS_AS(uniflow_net::write_frame(sockets.left, ""), std::runtime_error);

    const std::string oversized(static_cast<std::size_t>(uniflow_net::kMaxFrameSize) + 1, 'x');
    REQUIRE_THROWS_AS(uniflow_net::write_frame(sockets.left, oversized), std::runtime_error);
}

TEST_CASE("read_frame rejects invalid length prefix", "[framing]") {
    auto sockets = make_socket_pair();
    const std::uint32_t network_size = htonl(0);
    REQUIRE(
        ::send(sockets.left.get(), &network_size, sizeof(network_size), 0) ==
        static_cast<ssize_t>(sizeof(network_size)));
    REQUIRE_THROWS_AS(uniflow_net::read_frame(sockets.right), std::runtime_error);
}

TEST_CASE("read_frame rejects truncated payload", "[framing]") {
    auto sockets = make_socket_pair();
    const std::uint32_t network_size = htonl(8);
    REQUIRE(
        ::send(sockets.left.get(), &network_size, sizeof(network_size), 0) ==
        static_cast<ssize_t>(sizeof(network_size)));
    REQUIRE(::send(sockets.left.get(), "abcd", 4, 0) == 4);
    sockets.left.reset();
    REQUIRE_THROWS_AS(uniflow_net::read_frame(sockets.right), std::runtime_error);
}

TEST_CASE("framing rejects invalid socket descriptors", "[framing]") {
    uniflow_net::UniqueFd invalid;
    REQUIRE_THROWS_AS(uniflow_net::read_frame(invalid), std::runtime_error);
    REQUIRE_THROWS_AS(uniflow_net::write_frame(invalid, "payload"), std::runtime_error);
}
