#include "common.h"
#include "runtime.h"
#include "transfer.pb.h"

#include <arpa/inet.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

namespace uniflow_net {
namespace {

int create_udp_listener(int port) {
    const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        throw std::runtime_error(std::string("UDP socket failed: ") + std::strerror(errno));
    }

    int enabled = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));

    int receive_buffer = 16 * 1024 * 1024;
    ::setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &receive_buffer, sizeof(receive_buffer));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(static_cast<std::uint16_t>(port));

    if (::bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        const std::string message = std::strerror(errno);
        ::close(fd);
        throw std::runtime_error("UDP bind failed: " + message);
    }

    return fd;
}

void forward_with_reconnect(
    int& manager_fd,
    const std::string& manager_socket,
    const std::string& payload) {
    for (int attempt = 0; attempt < 2; ++attempt) {
        if (manager_fd < 0) {
            manager_fd = connect_unix_with_retry(manager_socket);
        }

        try {
            write_frame(manager_fd, payload);
            return;
        } catch (const std::exception&) {
            ::close(manager_fd);
            manager_fd = -1;
        }
    }

    throw std::runtime_error("could not forward packet to Session Manager");
}

}  // namespace

int run_receiver() {
    const std::string manager_socket = env_string("IPC_SOCKET_PATH");
    const int udp_port = env_int("UDP_PORT", 9000);
    const int worker = env_int("UNIFLOW_WORKER_INDEX", 0);

    if (manager_socket.empty()) {
        throw std::runtime_error("IPC_SOCKET_PATH is required");
    }

    const int udp_fd = create_udp_listener(udp_port);
    int manager_fd = connect_unix_with_retry(manager_socket);

    std::cerr << "Receiver " << worker << " listening on UDP " << udp_port
              << " and forwarding to " << manager_socket << '\n';

    std::array<char, 65535> buffer{};
    std::uint64_t received = 0;
    std::uint64_t rejected = 0;

    while (true) {
        const ssize_t size = ::recvfrom(udp_fd, buffer.data(), buffer.size(), 0, nullptr, nullptr);
        if (size < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("UDP receive failed: ") + std::strerror(errno));
        }

        std::string payload(buffer.data(), static_cast<std::size_t>(size));
        uniflow::FilePacket packet;
        if (!packet.ParseFromString(payload)) {
            ++rejected;
            continue;
        }

        // Intentionally do NOT reject based on packet.target_receiver().
        // A router misroute is still useful because all Receivers forward to
        // the same Session Manager, which groups packets by file/block IDs.
        forward_with_reconnect(manager_fd, manager_socket, payload);
        ++received;

        if (received % 1000 == 0) {
            std::cerr << "Receiver " << worker << " forwarded " << received
                      << " packets; rejected=" << rejected
                      << " current_file=" << packet.file_id() << '\n';
        }
    }
}

}  // namespace uniflow_net
