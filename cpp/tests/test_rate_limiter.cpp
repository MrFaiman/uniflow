#include "rate_limiter.h"

#include <catch2/catch_test_macros.hpp>

#include <chrono>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

struct FakeTime {
    Clock::time_point now{10s};
    std::vector<Clock::time_point> deadlines;

    uniflow_net::RateLimiter limiter(double mbps) {
        return uniflow_net::RateLimiter(
            mbps, [this] { return now; },
            [this](Clock::time_point deadline) {
                deadlines.push_back(deadline);
                now = deadline;
            });
    }
};

}  // namespace

TEST_CASE("RateLimiter disabled for non-positive rates", "[rate_limiter]") {
    for (const double rate : {0.0, -1.0}) {
        uniflow_net::RateLimiter limiter(
            rate, []() -> Clock::time_point {
                FAIL("Disabled rate limiter must not read the clock");
                return {};
            },
            [](Clock::time_point) { FAIL("Disabled rate limiter must not sleep"); });
        REQUIRE_FALSE(limiter.enabled());
        limiter.account(1'000'000);
    }
}

TEST_CASE("RateLimiter reports enabled for positive rates", "[rate_limiter]") {
    uniflow_net::RateLimiter limiter(100.0);
    REQUIRE(limiter.enabled());
}

TEST_CASE("RateLimiter paces bytes at the configured megabit rate", "[rate_limiter]") {
    FakeTime time;
    auto limiter = time.limiter(8.0);

    limiter.account(125'000);

    REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms}});
}

TEST_CASE("RateLimiter keeps a cumulative schedule across calls", "[rate_limiter]") {
    FakeTime time;
    auto limiter = time.limiter(8.0);

    limiter.account(125'000);
    time.now += 50ms;
    limiter.account(250'000);
    limiter.account(125'000);

    REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms},
                                        Clock::time_point{10s + 375ms},
                                        Clock::time_point{10s + 500ms}});
}

TEST_CASE("RateLimiter zero-byte accounting adds no delay", "[rate_limiter]") {
    FakeTime time;
    auto limiter = time.limiter(8.0);

    limiter.account(0);
    REQUIRE(time.deadlines.empty());
    limiter.account(125'000);
    limiter.account(0);

    REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms}});
}

TEST_CASE("RateLimiter skips sleeping when the schedule is already past", "[rate_limiter]") {
    FakeTime time;
    auto limiter = time.limiter(8.0);

    limiter.account(125'000);
    time.now += 500ms;
    limiter.account(125'000);

    REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms}});
    REQUIRE(time.now == Clock::time_point{10s + 625ms});
}

TEST_CASE("RateLimiter resets its schedule only after more than one second idle", "[rate_limiter]") {
    FakeTime time;
    auto limiter = time.limiter(8.0);

    limiter.account(125'000);
    SECTION("Exactly one second preserves the accumulated schedule") {
        time.now += 1s;
        limiter.account(125'000);
        REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms}});
    }
    SECTION("More than one second starts pacing from the current time") {
        time.now += 1s + 1ns;
        limiter.account(125'000);
        REQUIRE(time.deadlines == std::vector{Clock::time_point{10s + 125ms},
                                            Clock::time_point{11s + 250ms + 1ns}});
    }
}
