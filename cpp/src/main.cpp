#include "runtime.h"

#include <csignal>
#include <exception>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
#ifdef SIGPIPE
    std::signal(SIGPIPE, SIG_IGN);
#endif

    if (argc != 2) {
        std::cerr << "usage: uniflow-net <send|recv>\n";
        return 2;
    }

    try {
        const std::string mode = argv[1];
        if (mode == "send") {
            return uniflow_net::run_sender();
        }
        if (mode == "recv") {
            return uniflow_net::run_receiver();
        }

        std::cerr << "unknown mode: " << mode << "\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << "fatal: " << error.what() << "\n";
        return 1;
    }
}
