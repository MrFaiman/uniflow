#include "log.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>

namespace uniflow_net {
namespace {

std::mutex& log_mutex() {
    static std::mutex mutex;
    return mutex;
}

LogLevel& level_storage() noexcept {
    static LogLevel level = LogLevel::info;
    return level;
}

std::ofstream& log_file_stream() {
    static std::ofstream stream;
    return stream;
}

bool& file_enabled_flag() noexcept {
    static bool enabled = false;
    return enabled;
}

[[nodiscard]] std::string_view level_name(LogLevel level) noexcept {
    switch (level) {
        case LogLevel::debug:
            return "DEBUG";
        case LogLevel::info:
            return "INFO";
        case LogLevel::warn:
            return "WARN";
        case LogLevel::error:
            return "ERROR";
    }
    return "INFO";
}

}  // namespace

void set_log_level(LogLevel level) noexcept {
    level_storage() = level;
}

LogLevel current_log_level() noexcept {
    return level_storage();
}

void set_log_file(std::string_view path) {
    const std::lock_guard lock(log_mutex());
    auto& stream = log_file_stream();

    if (stream.is_open()) {
        stream.flush();
        stream.close();
    }
    file_enabled_flag() = false;

    if (path.empty()) {
        return;
    }

    const std::filesystem::path file_path{path};
    if (const auto parent = file_path.parent_path(); !parent.empty()) {
        std::filesystem::create_directories(parent);
    }

    stream.open(file_path, std::ios::out | std::ios::app);
    if (!stream) {
        throw std::runtime_error("failed to open log file: " + std::string{path});
    }

    stream.exceptions(std::ios::badbit);
    file_enabled_flag() = true;
}

bool log_file_enabled() noexcept {
    return file_enabled_flag();
}

void log_message(LogLevel level, std::string_view message) {
    if (level < current_log_level()) {
        return;
    }

    const std::lock_guard lock(log_mutex());
    const auto name = level_name(level);

    std::cerr << '[' << name << "] " << message << '\n';

    if (file_enabled_flag()) {
        auto& stream = log_file_stream();
        stream << '[' << name << "] " << message << '\n';
        stream.flush();
    }
}

}  // namespace uniflow_net
