#pragma once

#include <chrono>
#include <cstddef>

namespace uniflow_net {

class RateLimiter {
public:
    explicit RateLimiter(double megabits_per_second) noexcept;

    void account(std::size_t bytes);

    [[nodiscard]] bool enabled() const noexcept {
        return mbps_ > 0.0;
    }

private:
    double mbps_ = 0.0;
    bool started_ = false;
    std::chrono::steady_clock::time_point next_send_time_{};
};

}  // namespace uniflow_net
