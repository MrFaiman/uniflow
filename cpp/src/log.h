#pragma once

#include <format>
#include <string>
#include <string_view>
#include <utility>

namespace uniflow_net {

// Ordered by increasing severity. set_log_level(L) keeps messages with level >= L.
enum class LogLevel {
    debug,
    info,
    warn,
    error,
};

void set_log_level(LogLevel level) noexcept;
[[nodiscard]] LogLevel current_log_level() noexcept;

// Mirror log lines to a file in addition to stderr.
// Pass an empty path to disable file logging.
// Creates parent directories when needed. Throws on open failure.
void set_log_file(std::string_view path);
[[nodiscard]] bool log_file_enabled() noexcept;

void log_message(LogLevel level, std::string_view message);

template <typename... Args>
void log_debug(std::format_string<Args...> fmt, Args&&... args) {
    // Same predicate as log_message: drop below the configured minimum severity.
    if (LogLevel::debug < current_log_level()) {
        return;
    }
    log_message(LogLevel::debug, std::format(fmt, std::forward<Args>(args)...));
}

template <typename... Args>
void log_info(std::format_string<Args...> fmt, Args&&... args) {
    if (LogLevel::info < current_log_level()) {
        return;
    }
    log_message(LogLevel::info, std::format(fmt, std::forward<Args>(args)...));
}

template <typename... Args>
void log_warn(std::format_string<Args...> fmt, Args&&... args) {
    if (LogLevel::warn < current_log_level()) {
        return;
    }
    log_message(LogLevel::warn, std::format(fmt, std::forward<Args>(args)...));
}

template <typename... Args>
void log_error(std::format_string<Args...> fmt, Args&&... args) {
    if (LogLevel::error < current_log_level()) {
        return;
    }
    log_message(LogLevel::error, std::format(fmt, std::forward<Args>(args)...));
}

}  // namespace uniflow_net
