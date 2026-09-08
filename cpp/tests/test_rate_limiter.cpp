#include "rate_limiter.h"

#include <catch2/catch_test_macros.hpp>

#include <chrono>

TEST_CASE("RateLimiter disabled for non-positive rates", "[rate_limiter]") {
    uniflow_net::RateLimiter limiter(0.0);
    REQUIRE_FALSE(limiter.enabled());

    const auto start = std::chrono::steady_clock::now();
    limiter.account(1'000'000);
    const auto elapsed = std::chrono::steady_clock::now() - start;
    REQUIRE(elapsed < std::chrono::milliseconds(50));
}

TEST_CASE("RateLimiter reports enabled for positive rates", "[rate_limiter]") {
    uniflow_net::RateLimiter limiter(100.0);
    REQUIRE(limiter.enabled());
}
