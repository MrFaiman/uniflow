#pragma once

#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace uniflow_net {

constexpr std::uint32_t kMaxFrameSize = 2 * 1024 * 1024;

inline std::string env_string(const char* name, const std::string& fallback = "") {
    const char* value = std::getenv(name);
    if (value == nullptr || *value == '\0') {
        return fallback;
    }
    return value;
}

inline int env_int(const char* name, int fallback) {
    const std::string raw = env_string(name);
    if (raw.empty()) {
        return fallback;
    }
    try {
        return std::stoi(raw);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("invalid integer environment variable: ") + name);
    }
}

inline double env_double(const char* name, double fallback) {
    const std::string raw = env_string(name);
    if (raw.empty()) {
        return fallback;
    }
    try {
        return std::stod(raw);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("invalid numeric environment variable: ") + name);
    }
}

inline bool read_exact(int fd, void* buffer, std::size_t size) {
    auto* out = static_cast<unsigned char*>(buffer);
    std::size_t received = 0;

    while (received < size) {
        const ssize_t result = ::recv(fd, out + received, size - received, 0);
        if (result == 0) {
            return false;
        }
        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("recv failed: ") + std::strerror(errno));
        }
        received += static_cast<std::size_t>(result);
    }
    return true;
}

inline bool read_frame(int fd, std::string& payload) {
    std::uint32_t network_size = 0;
    if (!read_exact(fd, &network_size, sizeof(network_size))) {
        return false;
    }

    const std::uint32_t size = ntohl(network_size);
    if (size == 0 || size > kMaxFrameSize) {
        throw std::runtime_error("invalid IPC frame size");
    }

    payload.resize(size);
    return read_exact(fd, payload.data(), size);
}

inline void write_all(int fd, const void* buffer, std::size_t size) {
    const auto* data = static_cast<const unsigned char*>(buffer);
    std::size_t sent = 0;

    while (sent < size) {
        const ssize_t result = ::send(
            fd,
            data + sent,
            size - sent,
#ifdef MSG_NOSIGNAL
            MSG_NOSIGNAL
#else
            0
#endif
        );
        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("send failed: ") + std::strerror(errno));
        }
        sent += static_cast<std::size_t>(result);
    }
}

inline void write_frame(int fd, const std::string& payload) {
    if (payload.empty() || payload.size() > kMaxFrameSize) {
        throw std::runtime_error("invalid IPC frame size");
    }

    const std::uint32_t network_size = htonl(static_cast<std::uint32_t>(payload.size()));
    write_all(fd, &network_size, sizeof(network_size));
    write_all(fd, payload.data(), payload.size());
}

inline int connect_unix_with_retry(const std::string& path) {
    while (true) {
        const int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd < 0) {
            throw std::runtime_error(std::string("socket(AF_UNIX) failed: ") + std::strerror(errno));
        }

        sockaddr_un address{};
        address.sun_family = AF_UNIX;
        if (path.size() >= sizeof(address.sun_path)) {
            ::close(fd);
            throw std::runtime_error("Unix socket path is too long");
        }
        std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);

        if (::connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0) {
            return fd;
        }

        const int saved_errno = errno;
        ::close(fd);

        if (saved_errno != ENOENT && saved_errno != ECONNREFUSED) {
            std::cerr << "Unix socket connect failed: " << std::strerror(saved_errno)
                      << "; retrying\n";
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

}  // namespace uniflow_net
