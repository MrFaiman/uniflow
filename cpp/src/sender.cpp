#include "common.h"
#include "runtime.h"
#include "transfer.pb.h"

#include <netdb.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace uniflow_net {
namespace {

class RateLimiter {
public:
    explicit RateLimiter(double megabits_per_second) : mbps_(megabits_per_second) {}

    void account(std::size_t bytes) {
        if (mbps_ <= 0) {
            return;
        }

        const auto now = std::chrono::steady_clock::now();
        if (!started_ || now > next_send_time_ + std::chrono::seconds(1)) {
            next_send_time_ = now;
            started_ = true;
        }

        const double seconds =
            (static_cast<double>(bytes) * 8.0) / (mbps_ * 1'000'000.0);
        next_send_time_ += std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            std::chrono::duration<double>(seconds));

        const auto after_account = std::chrono::steady_clock::now();
        if (next_send_time_ > after_account) {
            std::this_thread::sleep_until(next_send_time_);
        }
    }

private:
    double mbps_ = 0;
    bool started_ = false;
    std::chrono::steady_clock::time_point next_send_time_{};
};

sockaddr_in resolve_udp_target(const std::string& host, int port) {
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;

    addrinfo* result = nullptr;
    const std::string port_text = std::to_string(port);

    for (int attempt = 0; attempt < 100; ++attempt) {
        const int code = ::getaddrinfo(host.c_str(), port_text.c_str(), &hints, &result);
        if (code == 0 && result != nullptr) {
            const auto address = *reinterpret_cast<sockaddr_in*>(result->ai_addr);
            ::freeaddrinfo(result);
            return address;
        }

        if (result != nullptr) {
            ::freeaddrinfo(result);
            result = nullptr;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    throw std::runtime_error("could not resolve router host: " + host);
}

int create_unix_server(const std::string& path) {
    if (path.empty()) {
        throw std::runtime_error("IPC_SOCKET_PATH is required");
    }

    ::unlink(path.c_str());

    const int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        throw std::runtime_error(std::string("Unix socket creation failed: ") + std::strerror(errno));
    }

    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (path.size() >= sizeof(address.sun_path)) {
        ::close(fd);
        throw std::runtime_error("Unix socket path is too long");
    }
    std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);

    if (::bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        const std::string message = std::strerror(errno);
        ::close(fd);
        throw std::runtime_error("Unix bind failed: " + message);
    }

    if (::listen(fd, 8) < 0) {
        const std::string message = std::strerror(errno);
        ::close(fd);
        throw std::runtime_error("Unix listen failed: " + message);
    }

    return fd;
}

}  // namespace

int run_sender() {
    const std::string socket_path = env_string("IPC_SOCKET_PATH");
    const std::string router_host = env_string("ROUTER_HOST", "router");
    const int udp_port = env_int("UDP_PORT", 9000);
    const int worker = env_int("UNIFLOW_WORKER_INDEX", 0);
    const double rate_mbps = env_double("UNIFLOW_SEND_RATE_MBPS", 0.0);

    const sockaddr_in target = resolve_udp_target(router_host, udp_port);

    const int udp_fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_fd < 0) {
        throw std::runtime_error(std::string("UDP socket failed: ") + std::strerror(errno));
    }

    const int server_fd = create_unix_server(socket_path);
    std::cerr << "Sender " << worker << " ready: socket=" << socket_path
              << " router=" << router_host << ':' << udp_port << '\n';

    RateLimiter limiter(rate_mbps);
    std::uint64_t packet_count = 0;

    while (true) {
        const int connection = ::accept(server_fd, nullptr, nullptr);
        if (connection < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("accept failed: ") + std::strerror(errno));
        }

        try {
            std::string payload;
            while (read_frame(connection, payload)) {
                uniflow::FilePacket packet;
                if (!packet.ParseFromString(payload)) {
                    std::cerr << "Sender " << worker << " rejected invalid Protobuf\n";
                    continue;
                }

                if (packet.target_receiver() != static_cast<std::uint32_t>(worker)) {
                    std::cerr << "Sender " << worker << " rejected packet routed to worker "
                              << packet.target_receiver() << '\n';
                    continue;
                }

                const ssize_t written = ::sendto(
                    udp_fd,
                    payload.data(),
                    payload.size(),
                    0,
                    reinterpret_cast<const sockaddr*>(&target),
                    sizeof(target));

                if (written < 0 || static_cast<std::size_t>(written) != payload.size()) {
                    throw std::runtime_error(std::string("UDP send failed: ") + std::strerror(errno));
                }

                ++packet_count;
                limiter.account(payload.size());

                if (packet_count % 1000 == 0) {
                    std::cerr << "Sender " << worker << " sent " << packet_count
                              << " packets; current_file=" << packet.file_id() << '\n';
                }
            }
        } catch (const std::exception& error) {
            std::cerr << "Sender " << worker << " connection error: " << error.what() << '\n';
        }

        ::close(connection);
    }
}

}  // namespace uniflow_net
