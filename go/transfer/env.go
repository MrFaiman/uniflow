package transfer

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

func loadDotEnv() {
	dir, err := os.Getwd()
	if err != nil {
		return
	}
	for {
		envFile := filepath.Join(dir, ".env")
		example := filepath.Join(dir, ".env.example")
		if _, err := os.Stat(envFile); err == nil {
			_ = godotenv.Load(envFile)
			return
		}
		if _, err := os.Stat(example); err == nil {
			_ = godotenv.Load(example)
			return
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return
		}
		dir = parent
	}
}

func socketPath() string {
	path := os.Getenv("IPC_SOCKET_PATH")
	if path == "" {
		slog.Error("IPC_SOCKET_PATH is not set; add it to .env")
		os.Exit(1)
	}
	return path
}

func udpPort() int {
	name := "UDP_PORT"
	raw := os.Getenv(name)
	if raw == "" {
		name = "PORT"
		raw = os.Getenv(name)
	}
	if raw == "" {
		return 9000
	}
	port, err := strconv.Atoi(raw)
	if err != nil || port < 1 || port > 65535 {
		slog.Error("invalid env", "name", name, "value", raw)
		os.Exit(1)
	}
	return port
}

func udpPorts() []int {
	raw := os.Getenv("UDP_PORTS")
	if raw == "" {
		return []int{udpPort()}
	}
	parts := strings.Split(raw, ",")
	ports := make([]int, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		port, err := strconv.Atoi(part)
		if err != nil || port < 1 || port > 65535 {
			slog.Error("invalid UDP_PORTS entry", "value", part)
			os.Exit(1)
		}
		ports = append(ports, port)
	}
	return ports
}

func receiveDir() string {
	dir := os.Getenv("RECEIVE_DIR")
	if dir == "" {
		dir = "/tmp/uniflow-in"
	}
	return dir
}

func envUint64(name string, defaultVal uint64) uint64 {
	raw := os.Getenv(name)
	if raw == "" {
		return defaultVal
	}
	val, err := strconv.ParseUint(raw, 10, 64)
	if err != nil {
		slog.Error("invalid env", "name", name, "value", raw)
		os.Exit(1)
	}
	return val
}

func workerIndex() uint32 {
	return uint32(envInt("UNIFLOW_WORKER_INDEX", 0))
}

func workerCount() uint32 {
	count := uint32(envInt("UNIFLOW_WORKER_COUNT", 1))
	if count == 0 {
		return 1
	}
	return count
}

func sessionIDFromEnv() uint64 {
	return envUint64("UNIFLOW_SESSION_ID", 0)
}

func envInt(name string, defaultVal int) int {
	raw := os.Getenv(name)
	if raw == "" {
		return defaultVal
	}
	val, err := strconv.Atoi(raw)
	if err != nil {
		slog.Error("invalid env", "name", name, "value", raw)
		os.Exit(1)
	}
	return val
}

func mustMkdir(path string) {
	if err := os.MkdirAll(path, 0o755); err != nil {
		slog.Error("mkdir failed", "path", path, "err", err)
		os.Exit(1)
	}
}

func joinHostPort(host string, port int) string {
	return fmt.Sprintf("%s:%d", host, port)
}
