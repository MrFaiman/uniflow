#include "config.h"
#include "framing.h"
#include "log.h"
#include "runtime.h"
#include "sockets.h"
#include "unique_fd.h"

#include <sys/socket.h>

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <string_view>

namespace uniflow_net {
namespace {

void forward_with_reconnect(
    UniqueFd& manager_fd,
    std::string_view manager_socket,
    std::string_view payload) {
    for (int attempt = 0; attempt < 2; ++attempt) {
        if (!manager_fd) {
            manager_fd = connect_unix_with_retry(manager_socket);
        }

        try {
            write_frame(manager_fd, payload);
            return;
        } catch (const std::exception& error) {
            log_warn("forward to Session Manager failed: {}", error.what());
            manager_fd.reset();
        }
    }

    throw std::runtime_error("could not forward packet to Session Manager");
}

}  // namespace

[[noreturn]] void run_receiver() {
    const ReceiverConfig config = ReceiverConfig::from_environment();

    UniqueFd udp_fd = create_udp_listener(config.udp_port);
    UniqueFd manager_fd = connect_unix_with_retry(config.ipc_socket_path);

    log_info(
        "Receiver {} listening on UDP {} and forwarding to {}",
        config.worker_index,
        config.udp_port,
        config.ipc_socket_path);

    std::array<char, 65535> buffer{};
    std::uint64_t received = 0;

    while (true) {
        const ssize_t size =
            ::recvfrom(udp_fd.get(), buffer.data(), buffer.size(), 0, nullptr, nullptr);
        if (size < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("UDP receive failed: ") + std::strerror(errno));
        }
        if (size == 0) {
            continue;
        }

        // Forward raw UDP bytes. Do not parse Protobuf here: bit-flip chaos can
        // corrupt string fields and libprotobuf would spam UTF-8 errors. The
        // Session Manager validates hashes and drops bad packets. Misrouted
        // packets are still useful because every Receiver shares one manager.
        const std::string_view payload(buffer.data(), static_cast<std::size_t>(size));
        forward_with_reconnect(manager_fd, config.ipc_socket_path, payload);
        ++received;

        if (received % 1000 == 0) {
            log_info(
                "Receiver {} forwarded {} packets",
                config.worker_index,
                received);
        }
    }
}

}  // namespace uniflow_net
