#include "config.h"
#include "framing.h"
#include "log.h"
#include "rate_limiter.h"
#include "runtime.h"
#include "sockets.h"
#include "transfer.pb.h"
#include "unique_fd.h"

#include <sys/socket.h>
#include <poll.h>

#include <cerrno>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

namespace uniflow_net {

[[noreturn]] void run_sender() {
    const SenderConfig config = SenderConfig::from_environment();
    const sockaddr_in target = resolve_udp_target(config.router_host, config.udp_port);

    UniqueFd udp_fd{::socket(AF_INET, SOCK_DGRAM, 0)};
    if (!udp_fd) {
        throw std::runtime_error(std::string("UDP socket failed: ") + std::strerror(errno));
    }

    UniqueFd server_fd = create_unix_server(config.ipc_socket_path);
    make_socket_nonblocking(server_fd.get());
    log_info(
        "Sender {} ready: socket={} router={}:{}",
        config.worker_index,
        config.ipc_socket_path,
        config.router_host,
        config.udp_port);

    RateLimiter limiter(config.send_rate_mbps);
    std::uint64_t packet_count = 0;

    while (true) {
        wait_for_socket(server_fd.get(), POLLIN);
        const int connection = ::accept(server_fd.get(), nullptr, nullptr);
        if (connection < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                continue;
            }
            throw std::runtime_error(std::string("accept failed: ") + std::strerror(errno));
        }

        UniqueFd connection_fd{connection};
        try {
            while (const auto payload = read_frame(connection_fd)) {
                uniflow::FilePacket packet;
                if (!packet.ParseFromString(*payload)) {
                    log_warn("Sender {} rejected invalid Protobuf", config.worker_index);
                    continue;
                }

                if (packet.target_receiver() != static_cast<std::uint32_t>(config.worker_index)) {
                    log_warn(
                        "Sender {} rejected packet routed to worker {}",
                        config.worker_index,
                        packet.target_receiver());
                    continue;
                }

                ssize_t written;
                while (true) {
                    wait_for_socket(udp_fd.get(), POLLOUT);
                    written = ::sendto(
                        udp_fd.get(),
                        payload->data(),
                        payload->size(),
                        MSG_DONTWAIT,
                        reinterpret_cast<const sockaddr*>(&target),
                        sizeof(target));
                    if (written >= 0 || (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)) {
                        break;
                    }
                }

                if (written < 0 || static_cast<std::size_t>(written) != payload->size()) {
                    throw std::runtime_error(
                        std::string("UDP send failed: ") + std::strerror(errno));
                }

                ++packet_count;
                limiter.account(payload->size());

                if (packet_count % 1000 == 0) {
                    log_info(
                        "Sender {} sent {} packets; current_file={}",
                        config.worker_index,
                        packet_count,
                        packet.file_id());
                }
            }
        } catch (const ShutdownRequested&) {
            throw;
        } catch (const std::exception& error) {
            log_warn("Sender {} connection error: {}", config.worker_index, error.what());
        }
    }
}

}  // namespace uniflow_net
