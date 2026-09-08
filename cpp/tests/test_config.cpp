#include "config.h"

#include <catch2/catch_test_macros.hpp>

#include <cstdlib>
#include <stdexcept>
#include <string>

namespace {

class EnvGuard {
public:
    EnvGuard(std::string name, std::string value) : name_(std::move(name)) {
        if (const char* previous = std::getenv(name_.c_str()); previous != nullptr) {
            previous_ = previous;
            had_previous_ = true;
        }
        REQUIRE(::setenv(name_.c_str(), value.c_str(), 1) == 0);
    }

    ~EnvGuard() {
        if (had_previous_) {
            ::setenv(name_.c_str(), previous_.c_str(), 1);
        } else {
            ::unsetenv(name_.c_str());
        }
    }

    EnvGuard(const EnvGuard&) = delete;
    EnvGuard& operator=(const EnvGuard&) = delete;

private:
    std::string name_;
    std::string previous_;
    bool had_previous_ = false;
};

class EnvClearGuard {
public:
    explicit EnvClearGuard(std::string name) : name_(std::move(name)) {
        if (const char* previous = std::getenv(name_.c_str()); previous != nullptr) {
            previous_ = previous;
            had_previous_ = true;
        }
        REQUIRE(::unsetenv(name_.c_str()) == 0);
    }

    ~EnvClearGuard() {
        if (had_previous_) {
            ::setenv(name_.c_str(), previous_.c_str(), 1);
        }
    }

    EnvClearGuard(const EnvClearGuard&) = delete;
    EnvClearGuard& operator=(const EnvClearGuard&) = delete;

private:
    std::string name_;
    std::string previous_;
    bool had_previous_ = false;
};

}  // namespace

TEST_CASE("env helpers parse values and defaults", "[config]") {
    {
        EnvClearGuard clear("UNIFLOW_TEST_STRING");
        REQUIRE(uniflow_net::env_string("UNIFLOW_TEST_STRING", "fallback") == "fallback");
    }
    {
        EnvGuard set("UNIFLOW_TEST_STRING", "value");
        REQUIRE(uniflow_net::env_string("UNIFLOW_TEST_STRING", "fallback") == "value");
    }
    {
        EnvClearGuard clear("UNIFLOW_TEST_INT");
        REQUIRE(uniflow_net::env_int("UNIFLOW_TEST_INT", 42) == 42);
    }
    {
        EnvGuard set("UNIFLOW_TEST_INT", "7");
        REQUIRE(uniflow_net::env_int("UNIFLOW_TEST_INT", 42) == 7);
    }
    {
        EnvGuard set("UNIFLOW_TEST_INT", "not-an-int");
        REQUIRE_THROWS_AS(uniflow_net::env_int("UNIFLOW_TEST_INT", 42), std::runtime_error);
    }
}

TEST_CASE("SenderConfig validates environment", "[config]") {
    EnvGuard socket("IPC_SOCKET_PATH", "/tmp/uniflow-test.sock");
    EnvGuard host("ROUTER_HOST", "127.0.0.1");
    EnvGuard port("UDP_PORT", "9100");
    EnvGuard worker("UNIFLOW_WORKER_INDEX", "2");
    EnvGuard rate("UNIFLOW_SEND_RATE_MBPS", "12.5");

    const auto config = uniflow_net::SenderConfig::from_environment();
    REQUIRE(config.ipc_socket_path == "/tmp/uniflow-test.sock");
    REQUIRE(config.router_host == "127.0.0.1");
    REQUIRE(config.udp_port == 9100);
    REQUIRE(config.worker_index == 2);
    REQUIRE(config.send_rate_mbps == 12.5);
}

TEST_CASE("SenderConfig rejects invalid values", "[config]") {
    EnvGuard socket("IPC_SOCKET_PATH", "/tmp/uniflow-test.sock");
    EnvGuard bad_port("UDP_PORT", "70000");
    REQUIRE_THROWS_AS(uniflow_net::SenderConfig::from_environment(), std::runtime_error);
}

TEST_CASE("worker configs default to role-specific IPC paths", "[config]") {
    EnvClearGuard clear_socket("IPC_SOCKET_PATH");
    EnvGuard port("UDP_PORT", "9000");
    EnvGuard rate("UNIFLOW_SEND_RATE_MBPS", "0");
    for (int index = 0; index < 3; ++index) {
        EnvGuard worker("UNIFLOW_WORKER_INDEX", std::to_string(index));
        const auto sender = uniflow_net::SenderConfig::from_environment();
        CHECK(sender.ipc_socket_path == "/tmp/uniflow/send.sock.sender." + std::to_string(index));
        CHECK(uniflow_net::ReceiverConfig::from_environment().ipc_socket_path ==
              "/tmp/uniflow/recv.sock");
    }
}

TEST_CASE("ReceiverConfig validates environment", "[config]") {
    EnvGuard socket("IPC_SOCKET_PATH", "/tmp/uniflow-rx.sock");
    EnvGuard port("UDP_PORT", "9200");
    EnvGuard worker("UNIFLOW_WORKER_INDEX", "1");

    const auto config = uniflow_net::ReceiverConfig::from_environment();
    REQUIRE(config.ipc_socket_path == "/tmp/uniflow-rx.sock");
    REQUIRE(config.udp_port == 9200);
    REQUIRE(config.worker_index == 1);
}

TEST_CASE("configuration rejects trailing garbage and nonfinite rates", "[config]") {
    EnvGuard socket("IPC_SOCKET_PATH", "/tmp/uniflow-rx.sock");
    SECTION("trailing port characters") {
        EnvGuard value("UDP_PORT", "9000garbage");
        REQUIRE_THROWS_AS(uniflow_net::SenderConfig::from_environment(), std::runtime_error);
    }
    SECTION("invalid worker") {
        EnvGuard value("UNIFLOW_WORKER_INDEX", "3");
        REQUIRE_THROWS_AS(uniflow_net::ReceiverConfig::from_environment(), std::runtime_error);
    }
    for (const auto* value : {"nan", "inf", "1mbps"}) {
        EnvGuard rate("UNIFLOW_SEND_RATE_MBPS", value);
        REQUIRE_THROWS_AS(uniflow_net::SenderConfig::from_environment(), std::runtime_error);
    }
}
