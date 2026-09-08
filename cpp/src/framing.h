#pragma once

#include "unique_fd.h"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>

namespace uniflow_net {

inline constexpr std::uint32_t kMaxFrameSize = 2 * 1024 * 1024;

[[nodiscard]] bool read_exact(UniqueFd& fd, std::span<std::byte> buffer);
void write_all(UniqueFd& fd, std::span<const std::byte> buffer);

// Returns nullopt on clean EOF before a full frame is available.
[[nodiscard]] std::optional<std::string> read_frame(UniqueFd& fd);
void write_frame(UniqueFd& fd, std::string_view payload);

}  // namespace uniflow_net
