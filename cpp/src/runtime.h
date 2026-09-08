#pragma once

#include <chrono>
#include <exception>

namespace uniflow_net {

class ShutdownRequested final : public std::exception {
public:
    [[nodiscard]] const char* what() const noexcept override {
        return "shutdown requested";
    }
};

void install_shutdown_handlers();
void throw_if_shutdown_requested();
void make_socket_nonblocking(int fd);
void wait_for_socket(int fd, short events);
void sleep_until(std::chrono::steady_clock::time_point deadline);

[[noreturn]] void run_sender();
[[noreturn]] void run_receiver();

}  // namespace uniflow_net
