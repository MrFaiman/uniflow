#include "sockets.h"

#include "log.h"

#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>

namespace uniflow_net {
namespace {

[[nodiscard]] sockaddr_un make_unix_address(std::string_view path) {
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (path.size() >= sizeof(address.sun_path)) {
        throw std::runtime_error("Unix socket path is too long");
    }
    std::memcpy(address.sun_path, path.data(), path.size());
    address.sun_path[path.size()] = '\0';
    return address;
}

}  // namespace

sockaddr_in resolve_udp_target(std::string_view host, int port) {
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;

    const std::string host_owned{host};
    const std::string port_text = std::to_string(port);
    addrinfo* result = nullptr;

    for (int attempt = 0; attempt < kDnsResolveAttempts; ++attempt) {
        const int code = ::getaddrinfo(host_owned.c_str(), port_text.c_str(), &hints, &result);
        if (code == 0 && result != nullptr) {
            const auto address = *reinterpret_cast<sockaddr_in*>(result->ai_addr);
            ::freeaddrinfo(result);
            return address;
        }

        if (result != nullptr) {
            ::freeaddrinfo(result);
            result = nullptr;
        }
        std::this_thread::sleep_for(kRetryDelay);
    }

    throw std::runtime_error("could not resolve router host: " + host_owned);
}

UniqueFd create_unix_server(std::string_view path) {
    if (path.empty()) {
        throw std::runtime_error("IPC_SOCKET_PATH is required");
    }

    const std::string path_owned{path};
    ::unlink(path_owned.c_str());

    UniqueFd fd{::socket(AF_UNIX, SOCK_STREAM, 0)};
    if (!fd) {
        throw std::runtime_error(std::string("Unix socket creation failed: ") + std::strerror(errno));
    }

    const sockaddr_un address = make_unix_address(path);
    if (::bind(fd.get(), reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) {
        throw std::runtime_error(std::string("Unix bind failed: ") + std::strerror(errno));
    }

    if (::listen(fd.get(), kUnixListenBacklog) < 0) {
        throw std::runtime_error(std::string("Unix listen failed: ") + std::strerror(errno));
    }

    return fd;
}

UniqueFd create_udp_listener(int port, int receive_buffer_bytes) {
    UniqueFd fd{::socket(AF_INET, SOCK_DGRAM, 0)};
    if (!fd) {
        throw std::runtime_error(std::string("UDP socket failed: ") + std::strerror(errno));
    }

    int enabled = 1;
    if (::setsockopt(fd.get(), SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled)) < 0) {
        throw std::runtime_error(std::string("SO_REUSEADDR failed: ") + std::strerror(errno));
    }

    if (::setsockopt(
            fd.get(),
            SOL_SOCKET,
            SO_RCVBUF,
            &receive_buffer_bytes,
            sizeof(receive_buffer_bytes)) < 0) {
        throw std::runtime_error(std::string("SO_RCVBUF failed: ") + std::strerror(errno));
    }

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(static_cast<std::uint16_t>(port));

    if (::bind(fd.get(), reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) {
        throw std::runtime_error(std::string("UDP bind failed: ") + std::strerror(errno));
    }

    return fd;
}

UniqueFd connect_unix_with_retry(std::string_view path) {
    const std::string path_owned{path};

    while (true) {
        UniqueFd fd{::socket(AF_UNIX, SOCK_STREAM, 0)};
        if (!fd) {
            throw std::runtime_error(std::string("socket(AF_UNIX) failed: ") + std::strerror(errno));
        }

        const sockaddr_un address = make_unix_address(path);
        if (::connect(fd.get(), reinterpret_cast<const sockaddr*>(&address), sizeof(address)) == 0) {
            return fd;
        }

        const int saved_errno = errno;
        if (saved_errno != ENOENT && saved_errno != ECONNREFUSED) {
            log_warn("Unix socket connect failed: {}; retrying", std::strerror(saved_errno));
        }
        std::this_thread::sleep_for(kRetryDelay);
    }
}

}  // namespace uniflow_net
