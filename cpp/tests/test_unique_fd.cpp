#include "unique_fd.h"

#include <catch2/catch_test_macros.hpp>

#include <unistd.h>

#include <utility>

TEST_CASE("UniqueFd closes on destruction", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);

    {
        uniflow_net::UniqueFd owned{fds[0]};
        REQUIRE(owned);
        REQUIRE(owned.get() == fds[0]);
        fds[0] = -1;
    }

    // Writing to the closed read end should fail once the peer is also closed,
    // but close() of the owned fd is verified by releasing/moving below.
    uniflow_net::UniqueFd write_end{fds[1]};
    REQUIRE(write_end);
}

TEST_CASE("UniqueFd move transfers ownership", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    ::close(fds[1]);

    uniflow_net::UniqueFd first{fds[0]};
    const int raw = first.get();
    uniflow_net::UniqueFd second = std::move(first);

    REQUIRE_FALSE(first);
    REQUIRE(first.get() == -1);
    REQUIRE(second);
    REQUIRE(second.get() == raw);

    second.reset();
    REQUIRE_FALSE(second);
}

TEST_CASE("UniqueFd release yields ownership", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    ::close(fds[1]);

    uniflow_net::UniqueFd owned{fds[0]};
    const int raw = owned.release();
    REQUIRE(raw == fds[0]);
    REQUIRE_FALSE(owned);
    REQUIRE(::close(raw) == 0);
}
