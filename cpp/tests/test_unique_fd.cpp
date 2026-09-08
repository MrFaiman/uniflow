#include "unique_fd.h"

#include <catch2/catch_test_macros.hpp>

#include <fcntl.h>
#include <unistd.h>

#include <cerrno>
#include <utility>

TEST_CASE("UniqueFd closes on destruction", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    uniflow_net::UniqueFd write_end{fds[1]};

    {
        uniflow_net::UniqueFd owned{fds[0]};
        REQUIRE(owned);
        REQUIRE(owned.get() == fds[0]);
        REQUIRE(::fcntl(fds[0], F_GETFD) != -1);
    }

    errno = 0;
    REQUIRE(::fcntl(fds[0], F_GETFD) == -1);
    REQUIRE(errno == EBADF);
    REQUIRE(::fcntl(write_end.get(), F_GETFD) != -1);
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
    REQUIRE(::fcntl(raw, F_GETFD) != -1);

    second.reset();
    REQUIRE_FALSE(second);
    errno = 0;
    REQUIRE(::fcntl(raw, F_GETFD) == -1);
    REQUIRE(errno == EBADF);
}

TEST_CASE("UniqueFd release yields ownership", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    ::close(fds[1]);

    uniflow_net::UniqueFd owned{fds[0]};
    const int raw = owned.release();
    uniflow_net::UniqueFd released{raw};
    REQUIRE(raw == fds[0]);
    REQUIRE_FALSE(owned);
    owned.reset();
    REQUIRE(::fcntl(raw, F_GETFD) != -1);
}

TEST_CASE("UniqueFd move assignment closes the replaced descriptor", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    uniflow_net::UniqueFd source{fds[0]};
    uniflow_net::UniqueFd destination{fds[1]};

    destination = std::move(source);

    REQUIRE_FALSE(source);
    REQUIRE(source.get() == -1);
    REQUIRE(destination.get() == fds[0]);
    REQUIRE(::fcntl(fds[0], F_GETFD) != -1);
    errno = 0;
    REQUIRE(::fcntl(fds[1], F_GETFD) == -1);
    REQUIRE(errno == EBADF);

    source.reset();
    REQUIRE(::fcntl(fds[0], F_GETFD) != -1);
    destination.reset();
    errno = 0;
    REQUIRE(::fcntl(fds[0], F_GETFD) == -1);
    REQUIRE(errno == EBADF);
}

TEST_CASE("UniqueFd self move assignment preserves the descriptor", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    uniflow_net::UniqueFd owned{fds[0]};
    uniflow_net::UniqueFd peer{fds[1]};
    auto& alias = owned;

    owned = std::move(alias);

    REQUIRE(owned.get() == fds[0]);
    REQUIRE(::fcntl(fds[0], F_GETFD) != -1);
}

TEST_CASE("UniqueFd reset closes the old descriptor and adopts the replacement", "[unique_fd]") {
    int fds[2] = {-1, -1};
    REQUIRE(::pipe(fds) == 0);
    uniflow_net::UniqueFd owned{fds[0]};
    uniflow_net::UniqueFd replacement{fds[1]};

    owned.reset(replacement.release());

    REQUIRE(owned.get() == fds[1]);
    REQUIRE(::fcntl(fds[1], F_GETFD) != -1);
    errno = 0;
    REQUIRE(::fcntl(fds[0], F_GETFD) == -1);
    REQUIRE(errno == EBADF);

    owned.reset();
    REQUIRE_FALSE(owned);
    REQUIRE(owned.get() == -1);
    errno = 0;
    REQUIRE(::fcntl(fds[1], F_GETFD) == -1);
    REQUIRE(errno == EBADF);
}
