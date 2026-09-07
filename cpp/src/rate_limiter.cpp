#include "rate_limiter.h"

#include <thread>

namespace uniflow_net {

RateLimiter::RateLimiter(double megabits_per_second) noexcept : mbps_(megabits_per_second) {}

void RateLimiter::account(std::size_t bytes) {
    if (mbps_ <= 0.0) {
        return;
    }

    const auto now = std::chrono::steady_clock::now();
    if (!started_ || now > next_send_time_ + std::chrono::seconds(1)) {
        next_send_time_ = now;
        started_ = true;
    }

    const double seconds = (static_cast<double>(bytes) * 8.0) / (mbps_ * 1'000'000.0);
    next_send_time_ += std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(seconds));

    const auto after_account = std::chrono::steady_clock::now();
    if (next_send_time_ > after_account) {
        std::this_thread::sleep_until(next_send_time_);
    }
}

}  // namespace uniflow_net
