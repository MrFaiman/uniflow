#include "runtime.h"

#include <poll.h>
#include <signal.h>
#include <fcntl.h>

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>

namespace uniflow_net {
namespace {

volatile sig_atomic_t shutdown_requested = 0;

void request_shutdown(int) {
    shutdown_requested = 1;
}

}  // namespace

void install_shutdown_handlers() {
    struct sigaction action {};
    action.sa_handler = request_shutdown;
    sigemptyset(&action.sa_mask);
    for (const int signal : {SIGTERM, SIGINT}) {
        if (::sigaction(signal, &action, nullptr) < 0) {
            throw std::runtime_error(std::string("sigaction failed: ") + std::strerror(errno));
        }
    }
}

void throw_if_shutdown_requested() {
    if (shutdown_requested != 0) {
        throw ShutdownRequested{};
    }
}

void wait_for_socket(int fd, short events) {
    if (fd < 0) {
        throw std::runtime_error("invalid socket descriptor");
    }
    struct pollfd descriptor {fd, events, 0};
    while (true) {
        throw_if_shutdown_requested();
        // A finite timeout also handles a signal arriving just before poll().
        const int result = ::poll(&descriptor, 1, 100);
        if (result > 0) {
            throw_if_shutdown_requested();
            return;
        }
        if (result < 0 && errno != EINTR) {
            throw std::runtime_error(std::string("poll failed: ") + std::strerror(errno));
        }
    }
}

void make_socket_nonblocking(int fd) {
    const int flags = ::fcntl(fd, F_GETFL);
    if (flags < 0 || ::fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        throw std::runtime_error(std::string("fcntl failed: ") + std::strerror(errno));
    }
}

void sleep_until(std::chrono::steady_clock::time_point deadline) {
    while (true) {
        throw_if_shutdown_requested();
        const auto remaining = deadline - std::chrono::steady_clock::now();
        if (remaining <= std::chrono::steady_clock::duration::zero()) {
            return;
        }
        const auto milliseconds = std::chrono::ceil<std::chrono::milliseconds>(remaining);
        const int timeout = static_cast<int>(
            std::min(milliseconds, std::chrono::milliseconds{100}).count());
        if (::poll(nullptr, 0, timeout) < 0 && errno != EINTR) {
            throw std::runtime_error(std::string("sleep poll failed: ") + std::strerror(errno));
        }
    }
}

}  // namespace uniflow_net
