#pragma once

#include "unique_fd.h"

#include <netinet/in.h>

#include <chrono>
#include <string>
#include <string_view>

namespace uniflow_net {

inline constexpr int kDefaultUdpReceiveBufferBytes = 16 * 1024 * 1024;
inline constexpr int kUnixListenBacklog = 8;
inline constexpr int kDnsResolveAttempts = 100;
inline constexpr auto kRetryDelay = std::chrono::milliseconds{100};

[[nodiscard]] sockaddr_in resolve_udp_target(std::string_view host, int port);
[[nodiscard]] UniqueFd create_unix_server(std::string_view path);
[[nodiscard]] UniqueFd create_udp_listener(
    int port,
    int receive_buffer_bytes = kDefaultUdpReceiveBufferBytes);
[[nodiscard]] UniqueFd connect_unix_with_retry(std::string_view path);

}  // namespace uniflow_net
