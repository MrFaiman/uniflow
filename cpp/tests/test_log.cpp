#include "log.h"

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

TEST_CASE("logger mirrors messages to a file", "[log]") {
    const auto path =
        std::filesystem::temp_directory_path() / "uniflow-log-test.txt";
    std::filesystem::remove(path);

    uniflow_net::set_log_level(uniflow_net::LogLevel::info);
    uniflow_net::set_log_file(path.string());
    REQUIRE(uniflow_net::log_file_enabled());

    uniflow_net::log_info("hello from test {}", 42);
    uniflow_net::log_warn("warn line");

    uniflow_net::set_log_file("");
    REQUIRE_FALSE(uniflow_net::log_file_enabled());

    std::ifstream input(path);
    REQUIRE(input);
    std::ostringstream contents;
    contents << input.rdbuf();
    const std::string text = contents.str();

    REQUIRE(text.find("[INFO] hello from test 42") != std::string::npos);
    REQUIRE(text.find("[WARN] warn line") != std::string::npos);

    std::filesystem::remove(path);
}

TEST_CASE("logger filters below the configured minimum severity", "[log]") {
    const auto path =
        std::filesystem::temp_directory_path() / "uniflow-log-filter-test.txt";
    std::filesystem::remove(path);

    uniflow_net::set_log_level(uniflow_net::LogLevel::warn);
    uniflow_net::set_log_file(path.string());

    uniflow_net::log_debug("debug should be dropped");
    uniflow_net::log_info("info should be dropped");
    uniflow_net::log_warn("warn should appear");
    uniflow_net::log_error("error should appear");

    uniflow_net::set_log_file("");
    uniflow_net::set_log_level(uniflow_net::LogLevel::info);

    std::ifstream input(path);
    REQUIRE(input);
    std::ostringstream contents;
    contents << input.rdbuf();
    const std::string text = contents.str();

    REQUIRE(text.find("debug should be dropped") == std::string::npos);
    REQUIRE(text.find("info should be dropped") == std::string::npos);
    REQUIRE(text.find("[WARN] warn should appear") != std::string::npos);
    REQUIRE(text.find("[ERROR] error should appear") != std::string::npos);

    std::filesystem::remove(path);
}
