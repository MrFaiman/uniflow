#include "log.h"
#include "runtime.h"

#include <argparse/argparse.hpp>

#include <cstdlib>
#include <csignal>
#include <exception>
#include <iostream>
#include <string>

namespace {

[[nodiscard]] int dispatch(const argparse::ArgumentParser& program) {
    if (program.is_subcommand_used("send")) {
        uniflow_net::run_sender();
    }
    if (program.is_subcommand_used("recv")) {
        uniflow_net::run_receiver();
    }

    std::cerr << program;
    return 2;
}

void configure_logging(const argparse::ArgumentParser& program) {
    if (program.get<bool>("--verbose")) {
        uniflow_net::set_log_level(uniflow_net::LogLevel::debug);
    }

    std::string log_file;
    if (program.is_used("--log-file")) {
        log_file = program.get<std::string>("--log-file");
    } else if (const char* from_env = std::getenv("UNIFLOW_LOG_FILE");
               from_env != nullptr && *from_env != '\0') {
        log_file = from_env;
    }

    if (!log_file.empty()) {
        uniflow_net::set_log_file(log_file);
        uniflow_net::log_info("logging to file {}", log_file);
    }
}

}  // namespace

int main(int argc, char** argv) {
#ifdef SIGPIPE
    std::signal(SIGPIPE, SIG_IGN);
#endif

    argparse::ArgumentParser program("uniflow-net", "1.0.0");
    program.add_description(
        "UniFlow network workers. Configuration is provided via environment variables.");

    program.add_argument("--verbose")
        .help("enable debug logging")
        .default_value(false)
        .implicit_value(true);

    program.add_argument("--log-file")
        .help("also write logs to this file (overrides UNIFLOW_LOG_FILE)")
        .nargs(1);

    argparse::ArgumentParser send_command("send");
    send_command.add_description("Run a sender worker (Unix IPC -> UDP)");

    argparse::ArgumentParser recv_command("recv");
    recv_command.add_description("Run a receiver worker (UDP -> Unix IPC)");

    program.add_subparser(send_command);
    program.add_subparser(recv_command);

    try {
        program.parse_args(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        std::cerr << program;
        return 2;
    }

    try {
        uniflow_net::install_shutdown_handlers();
        configure_logging(program);
        return dispatch(program);
    } catch (const uniflow_net::ShutdownRequested&) {
        return 0;
    } catch (const std::exception& error) {
        uniflow_net::log_error("fatal: {}", error.what());
        return 1;
    }
}
