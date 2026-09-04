#include "common.h"
#include "runtime.h"
#include "transfer.pb.h"

#include <arpa/inet.h>

#include <array>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace uniflow_net {
namespace {

constexpr std::size_t kForwardQueueMaxBytes =
    64ULL * 1024ULL * 1024ULL;


class PacketQueue {
public:
    void push(std::string payload) {
        const std::size_t payload_size = payload.size();

        std::unique_lock<std::mutex> lock(mutex_);

        not_full_.wait(
            lock,
            [&] {
                return queued_bytes_ + payload_size
                    <= kForwardQueueMaxBytes;
            });

        queued_bytes_ += payload_size;
        packets_.push_back(std::move(payload));

        lock.unlock();
        not_empty_.notify_one();
    }


    std::string pop() {
        std::unique_lock<std::mutex> lock(mutex_);

        not_empty_.wait(
            lock,
            [&] {
                return !packets_.empty();
            });

        std::string payload =
            std::move(packets_.front());

        packets_.pop_front();
        queued_bytes_ -= payload.size();

        lock.unlock();
        not_full_.notify_one();

        return payload;
    }


private:
    std::mutex mutex_;

    std::condition_variable not_empty_;
    std::condition_variable not_full_;

    std::deque<std::string> packets_;

    std::size_t queued_bytes_ = 0;
};


int create_udp_listener(int port) {
    const int fd = ::socket(
        AF_INET,
        SOCK_DGRAM,
        0
    );

    if (fd < 0) {
        throw std::runtime_error(
            std::string("UDP socket failed: ")
            + std::strerror(errno)
        );
    }

    int enabled = 1;

    ::setsockopt(
        fd,
        SOL_SOCKET,
        SO_REUSEADDR,
        &enabled,
        sizeof(enabled)
    );

    int receive_buffer =
        32 * 1024 * 1024;

    ::setsockopt(
        fd,
        SOL_SOCKET,
        SO_RCVBUF,
        &receive_buffer,
        sizeof(receive_buffer)
    );

    sockaddr_in address{};

    address.sin_family = AF_INET;
    address.sin_addr.s_addr =
        htonl(INADDR_ANY);

    address.sin_port = htons(
        static_cast<std::uint16_t>(port)
    );

    if (
        ::bind(
            fd,
            reinterpret_cast<sockaddr*>(&address),
            sizeof(address)
        ) < 0
    ) {
        const std::string message =
            std::strerror(errno);

        ::close(fd);

        throw std::runtime_error(
            "UDP bind failed: " + message
        );
    }

    return fd;
}


void forward_with_reconnect(
    int& manager_fd,
    const std::string& manager_socket,
    const std::string& payload
) {
    while (true) {
        if (manager_fd < 0) {
            manager_fd =
                connect_unix_with_retry(
                    manager_socket
                );
        }

        try {
            write_frame(
                manager_fd,
                payload
            );

            return;

        } catch (const std::exception&) {
            ::close(manager_fd);
            manager_fd = -1;

            std::this_thread::sleep_for(
                std::chrono::milliseconds(50)
            );
        }
    }
}


void forward_packets(
    PacketQueue& queue,
    const std::string& manager_socket
) {
    int manager_fd = -1;

    while (true) {
        std::string payload =
            queue.pop();

        forward_with_reconnect(
            manager_fd,
            manager_socket,
            payload
        );
    }
}

}  // namespace


int run_receiver() {
    const std::string manager_socket =
        env_string(
            "IPC_SOCKET_PATH"
        );

    const int udp_port =
        env_int(
            "UDP_PORT",
            9000
        );

    const int worker =
        env_int(
            "UNIFLOW_WORKER_INDEX",
            0
        );

    if (manager_socket.empty()) {
        throw std::runtime_error(
            "IPC_SOCKET_PATH is required"
        );
    }

    const int udp_fd =
        create_udp_listener(
            udp_port
        );

    PacketQueue forward_queue;

    // The UDP receive loop and the UDS forwarding loop are deliberately
    // separated. Python/RaptorQ may pause while decoding a block, but the
    // Receiver should continue draining UDP into this in-memory queue.
    std::thread writer(
        forward_packets,
        std::ref(forward_queue),
        manager_socket
    );

    writer.detach();

    std::cerr
        << "Receiver "
        << worker
        << " listening on UDP "
        << udp_port
        << " and buffering packets for "
        << manager_socket
        << '\n';

    std::array<char, 65535> buffer{};

    std::uint64_t received = 0;
    std::uint64_t rejected = 0;

    while (true) {
        const ssize_t size =
            ::recvfrom(
                udp_fd,
                buffer.data(),
                buffer.size(),
                0,
                nullptr,
                nullptr
            );

        if (size < 0) {
            if (errno == EINTR) {
                continue;
            }

            throw std::runtime_error(
                std::string(
                    "UDP receive failed: "
                )
                + std::strerror(errno)
            );
        }

        std::string payload(
            buffer.data(),
            static_cast<std::size_t>(size)
        );

        uniflow::FilePacket packet;

        if (
            !packet.ParseFromString(
                payload
            )
        ) {
            ++rejected;
            continue;
        }

        // Intentionally do NOT reject based on target_receiver().
        // A router misroute is still useful because every Receiver ultimately
        // forwards valid packets to the same Session Manager.
        forward_queue.push(
            std::move(payload)
        );

        ++received;

        if (received % 1000 == 0) {
            std::cerr
                << "Receiver "
                << worker
                << " queued "
                << received
                << " packets; rejected="
                << rejected
                << " current_file="
                << packet.file_id()
                << '\n';
        }
    }
}

}  // namespace uniflow_net
