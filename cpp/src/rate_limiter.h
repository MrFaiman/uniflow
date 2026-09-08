#pragma once

#include <chrono>
#include <cstddef>
#include <functional>

namespace uniflow_net {

class RateLimiter {
public:
    using Clock = std::chrono::steady_clock;
    using Now = std::function<Clock::time_point()>;
    using SleepUntil = std::function<void(Clock::time_point)>;

    explicit RateLimiter(double megabits_per_second) noexcept;
    RateLimiter(double megabits_per_second, Now now, SleepUntil sleep_until);

    void account(std::size_t bytes);

    [[nodiscard]] bool enabled() const noexcept {
        return mbps_ > 0.0;
    }

private:
    double mbps_ = 0.0;
    Now now_;
    SleepUntil sleep_until_;
    bool started_ = false;
    std::chrono::steady_clock::time_point next_send_time_{};
};

}  // namespace uniflow_net
