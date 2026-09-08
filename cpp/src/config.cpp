#include "config.h"

#include <cstdlib>
#include <cmath>
#include <stdexcept>
#include <string>

namespace uniflow_net {
namespace {

void validate_port(int port) {
    if (port < 1 || port > 65535) {
        throw std::runtime_error("UDP_PORT must be in range [1, 65535]");
    }
}

void validate_worker_index(int worker_index) {
    if (worker_index < 0 || worker_index >= 3) {
        throw std::runtime_error("UNIFLOW_WORKER_INDEX must be in range [0, 2]");
    }
}

void validate_rate(double rate_mbps) {
    if (!std::isfinite(rate_mbps) || rate_mbps < 0.0) {
        throw std::runtime_error("UNIFLOW_SEND_RATE_MBPS must be finite and non-negative");
    }
}

}  // namespace

std::string env_string(std::string_view name, std::string_view fallback) {
    const std::string name_owned{name};
    const char* value = std::getenv(name_owned.c_str());
    if (value == nullptr || *value == '\0') {
        return std::string{fallback};
    }
    return value;
}

int env_int(std::string_view name, int fallback) {
    const std::string raw = env_string(name);
    if (raw.empty()) {
        return fallback;
    }
    try {
        std::size_t end = 0;
        const int value = std::stoi(raw, &end);
        if (end != raw.size()) {
            throw std::runtime_error("trailing characters");
        }
        return value;
    } catch (const std::exception&) {
        throw std::runtime_error("invalid integer environment variable: " + std::string{name});
    }
}

double env_double(std::string_view name, double fallback) {
    const std::string raw = env_string(name);
    if (raw.empty()) {
        return fallback;
    }
    try {
        std::size_t end = 0;
        const double value = std::stod(raw, &end);
        if (end != raw.size() || !std::isfinite(value)) {
            throw std::runtime_error("invalid number");
        }
        return value;
    } catch (const std::exception&) {
        throw std::runtime_error("invalid numeric environment variable: " + std::string{name});
    }
}

SenderConfig SenderConfig::from_environment() {
    const int worker_index = env_int("UNIFLOW_WORKER_INDEX", 0);
    SenderConfig config{
        .ipc_socket_path = env_string(
            "IPC_SOCKET_PATH", "/tmp/uniflow/send.sock.sender." + std::to_string(worker_index)),
        .router_host = env_string("ROUTER_HOST", "router"),
        .udp_port = env_int("UDP_PORT", 9000),
        .worker_index = worker_index,
        .send_rate_mbps = env_double("UNIFLOW_SEND_RATE_MBPS", 0.0),
    };

    validate_port(config.udp_port);
    validate_worker_index(config.worker_index);
    validate_rate(config.send_rate_mbps);

    if (config.router_host.empty()) {
        throw std::runtime_error("ROUTER_HOST must not be empty");
    }

    return config;
}

ReceiverConfig ReceiverConfig::from_environment() {
    ReceiverConfig config{
        .ipc_socket_path = env_string("IPC_SOCKET_PATH", "/tmp/uniflow/recv.sock"),
        .udp_port = env_int("UDP_PORT", 9000),
        .worker_index = env_int("UNIFLOW_WORKER_INDEX", 0),
    };

    validate_port(config.udp_port);
    validate_worker_index(config.worker_index);
    return config;
}

}  // namespace uniflow_net
