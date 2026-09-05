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

// This queue absorbs temporary bursts.
//
// IMPORTANT:
// The UDP receive loop must never wait for Python / RaptorQ.
// If it waits, the Linux UDP buffer can overflow and silently
// throw packets away.
constexpr std::size_t kForwardQueueMaxBytes =
    128ULL * 1024ULL * 1024ULL;


class PacketQueue {
public:
    bool try_push(std::string payload) {
        const std::size_t payload_size = payload.size();

        {
            std::lock_guard<std::mutex> lock(mutex_);

            if (
                queued_bytes_ + payload_size
                > kForwardQueueMaxBytes
            ) {
                return false;
            }

            queued_bytes_ += payload_size;

            packets_.push_back(
                std::move(payload)
            );

            if (
                queued_bytes_
                > highest_queued_bytes_
            ) {
                highest_queued_bytes_ =
                    queued_bytes_;
            }
        }

        not_empty_.notify_one();

        return true;
    }


    std::string pop() {
        std::unique_lock<std::mutex> lock(
            mutex_
        );

        not_empty_.wait(
            lock,
            [&] {
                return !packets_.empty();
            }
        );

        std::string payload =
            std::move(
                packets_.front()
            );

        packets_.pop_front();

        queued_bytes_ -=
            payload.size();

        return payload;
    }


    std::size_t queued_bytes() const {
        std::lock_guard<std::mutex> lock(
            mutex_
        );

        return queued_bytes_;
    }


    std::size_t highest_queued_bytes() const {
        std::lock_guard<std::mutex> lock(
            mutex_
        );

        return highest_queued_bytes_;
    }


private:
    mutable std::mutex mutex_;

    std::condition_variable not_empty_;

    std::deque<std::string> packets_;

    std::size_t queued_bytes_ = 0;
    std::size_t highest_queued_bytes_ = 0;
};


int create_udp_listener(int port) {
    const int fd = ::socket(
        AF_INET,
        SOCK_DGRAM,
        0
    );

    if (fd < 0) {
        throw std::runtime_error(
            std::string(
                "UDP socket failed: "
            )
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

    // Request a large kernel UDP buffer.
    //
    // Linux may give us less depending on system limits,
    // so we read it back and print the real value.
    int requested_buffer =
        64 * 1024 * 1024;

    ::setsockopt(
        fd,
        SOL_SOCKET,
        SO_RCVBUF,
        &requested_buffer,
        sizeof(requested_buffer)
    );

    int actual_buffer = 0;
    socklen_t buffer_length =
        sizeof(actual_buffer);

    ::getsockopt(
        fd,
        SOL_SOCKET,
        SO_RCVBUF,
        &actual_buffer,
        &buffer_length
    );

    std::cerr
        << "UDP receive buffer requested="
        << requested_buffer
        << " actual="
        << actual_buffer
        << '\n';

    sockaddr_in address{};

    address.sin_family = AF_INET;

    address.sin_addr.s_addr =
        htonl(INADDR_ANY);

    address.sin_port =
        htons(
            static_cast<std::uint16_t>(
                port
            )
        );

    if (
        ::bind(
            fd,
            reinterpret_cast<sockaddr*>(
                &address
            ),
            sizeof(address)
        ) < 0
    ) {
        const std::string message =
            std::strerror(errno);

        ::close(fd);

        throw std::runtime_error(
            "UDP bind failed: "
            + message
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
        }
        catch (const std::exception&) {
            ::close(manager_fd);

            manager_fd = -1;

            std::this_thread::sleep_for(
                std::chrono::milliseconds(
                    50
                )
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

    // One thread ONLY receives UDP.
    //
    // Another thread sends packets to Python.
    //
    // This is the important separation learned from Claude's
    // implementation.
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
    std::uint64_t queued = 0;
    std::uint64_t invalid = 0;
    std::uint64_t queue_overrun = 0;

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

        ++received;

        std::string payload(
            buffer.data(),
            static_cast<std::size_t>(
                size
            )
        );

        uniflow::FilePacket packet;

        if (
            !packet.ParseFromString(
                payload
            )
        ) {
            ++invalid;
            continue;
        }

        // Do NOT reject packets because target_receiver
        // does not match this worker.
        //
        // The project router may intentionally misroute
        // packets. Every Receiver eventually reaches the
        // same Session Manager.
        if (
            !forward_queue.try_push(
                std::move(payload)
            )
        ) {
            // This is MUCH better than silently blocking
            // recvfrom().
            //
            // RaptorQ may recover a small number of these,
            // and most importantly we can now SEE whether
            // our own program is dropping data.
            ++queue_overrun;

            if (
                queue_overrun == 1
                || queue_overrun % 1000 == 0
            ) {
                std::cerr
                    << "WARNING: Receiver "
                    << worker
                    << " processing queue full. "
                    << "Local dropped packets="
                    << queue_overrun
                    << '\n';
            }

            continue;
        }

        ++queued;

        if (received % 1000 == 0) {
            std::cerr
                << "Receiver "
                << worker
                << " received="
                << received
                << " queued="
                << queued
                << " invalid="
                << invalid
                << " local_drops="
                << queue_overrun
                << " queue_bytes="
                << forward_queue.queued_bytes()
                << " queue_highest="
                << forward_queue.highest_queued_bytes()
                << " current_file="
                << packet.file_id()
                << '\n';
        }
    }
}

}  // namespace uniflow_net