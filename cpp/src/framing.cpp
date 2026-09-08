#include "framing.h"
#include "runtime.h"

#include <arpa/inet.h>
#include <poll.h>
#include <sys/socket.h>

#include <cerrno>
#include <cstring>
#include <span>
#include <stdexcept>
#include <string>

namespace uniflow_net {

bool read_exact(UniqueFd& fd, std::span<std::byte> buffer) {
    std::size_t received = 0;

    while (received < buffer.size()) {
        wait_for_socket(fd.get(), POLLIN);
        const ssize_t result = ::recv(
            fd.get(),
            buffer.data() + received,
            buffer.size() - received,
            MSG_DONTWAIT);
        if (result == 0) {
            return false;
        }
        if (result < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                continue;
            }
            throw std::runtime_error(std::string("recv failed: ") + std::strerror(errno));
        }
        received += static_cast<std::size_t>(result);
    }
    return true;
}

void write_all(UniqueFd& fd, std::span<const std::byte> buffer) {
    std::size_t sent = 0;

    while (sent < buffer.size()) {
        wait_for_socket(fd.get(), POLLOUT);
        const ssize_t result = ::send(
            fd.get(),
            buffer.data() + sent,
            buffer.size() - sent,
#ifdef MSG_NOSIGNAL
            MSG_NOSIGNAL | MSG_DONTWAIT
#else
            MSG_DONTWAIT
#endif
        );
        if (result < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                continue;
            }
            throw std::runtime_error(std::string("send failed: ") + std::strerror(errno));
        }
        sent += static_cast<std::size_t>(result);
    }
}

std::optional<std::string> read_frame(UniqueFd& fd) {
    std::uint32_t network_size = 0;
    auto size_bytes = std::as_writable_bytes(std::span{&network_size, 1});
    if (!read_exact(fd, size_bytes)) {
        return std::nullopt;
    }

    const std::uint32_t size = ntohl(network_size);
    if (size == 0 || size > kMaxFrameSize) {
        throw std::runtime_error("invalid IPC frame size");
    }

    std::string payload(size, '\0');
    auto payload_bytes = std::as_writable_bytes(std::span{payload.data(), payload.size()});
    if (!read_exact(fd, payload_bytes)) {
        throw std::runtime_error("unexpected EOF while reading IPC frame payload");
    }
    return payload;
}

void write_frame(UniqueFd& fd, std::string_view payload) {
    if (payload.empty() || payload.size() > kMaxFrameSize) {
        throw std::runtime_error("invalid IPC frame size");
    }

    const std::uint32_t network_size = htonl(static_cast<std::uint32_t>(payload.size()));
    write_all(fd, std::as_bytes(std::span{&network_size, 1}));
    write_all(fd, std::as_bytes(std::span{payload.data(), payload.size()}));
}

}  // namespace uniflow_net
