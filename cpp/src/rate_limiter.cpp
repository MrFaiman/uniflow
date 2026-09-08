#include "rate_limiter.h"
#include "runtime.h"

#include <utility>

namespace uniflow_net {

RateLimiter::RateLimiter(double megabits_per_second) noexcept
    : RateLimiter(megabits_per_second, &Clock::now, &uniflow_net::sleep_until) {}

RateLimiter::RateLimiter(double megabits_per_second, Now now, SleepUntil sleep_until)
    : mbps_(megabits_per_second), now_(std::move(now)), sleep_until_(std::move(sleep_until)) {}

void RateLimiter::account(std::size_t bytes) {
    if (mbps_ <= 0.0) {
        return;
    }

    const auto now = now_();
    if (!started_ || now > next_send_time_ + std::chrono::seconds(1)) {
        next_send_time_ = now;
        started_ = true;
    }

    const double seconds = (static_cast<double>(bytes) * 8.0) / (mbps_ * 1'000'000.0);
    next_send_time_ += std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(seconds));

    const auto after_account = now_();
    if (next_send_time_ > after_account) {
        sleep_until_(next_send_time_);
    }
}

}  // namespace uniflow_net
