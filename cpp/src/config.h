#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace uniflow_net {

[[nodiscard]] std::string env_string(std::string_view name, std::string_view fallback = "");
[[nodiscard]] int env_int(std::string_view name, int fallback);
[[nodiscard]] double env_double(std::string_view name, double fallback);

struct SenderConfig {
    std::string ipc_socket_path;
    std::string router_host = "router";
    int udp_port = 9000;
    int worker_index = 0;
    double send_rate_mbps = 0.0;

    [[nodiscard]] static SenderConfig from_environment();
};

struct ReceiverConfig {
    std::string ipc_socket_path;
    int udp_port = 9000;
    int worker_index = 0;

    [[nodiscard]] static ReceiverConfig from_environment();
};

}  // namespace uniflow_net
