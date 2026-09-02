package config

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

const (
	DefaultSocketPath       = "/tmp/proto_ipc.sock"
	DefaultWorkers          = 3
	DefaultPort             = 9000
	DefaultRouterHost       = "router"
	DefaultWorkerSocketDir  = "/tmp/uniflow"
	DefaultShardSize        = 600
	DefaultParityShards     = 2
	DefaultMaxInflight      = 4096
	DefaultFrameTTL         = 5 * time.Second
	DefaultUDPRcvBuf        = 8 * 1024 * 1024
	DefaultSendPPS          = 0
	DefaultVerifyPacketHash = true
)

func LoadDotEnv() {
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

func SocketPath() string {
	return envString("IPC_SOCKET_PATH", DefaultSocketPath)
}

func Workers() int {
	return envInt("UNIFLOW_WORKERS", DefaultWorkers)
}

func BasePort() int {
	if raw := os.Getenv("PORT"); raw != "" {
		return envInt("PORT", DefaultPort)
	}
	return envInt("UDP_PORT", DefaultPort)
}

func RouterBasePort() int {
	if raw := os.Getenv("UNIFLOW_ROUTER_PORT"); raw != "" {
		return envInt("UNIFLOW_ROUTER_PORT", DefaultPort)
	}
	return BasePort()
}

func RouterPortForWorker(index int) int {
	return RouterBasePort() + index
}

func PortForWorker(index int) int {
	return BasePort() + index
}

func RouterHost() string {
	return envString("UNIFLOW_ROUTER_HOST", DefaultRouterHost)
}

func WorkerSocketDir() string {
	return envString("UNIFLOW_WORKER_SOCKET_DIR", DefaultWorkerSocketDir)
}

func WorkerSocketPath(index int) string {
	return filepath.Join(WorkerSocketDir(), fmt.Sprintf("s%d.sock", index))
}

func ShardSize() int {
	return envInt("UNIFLOW_SHARD_SIZE", DefaultShardSize)
}

func ParityShards() int {
	return envInt("UNIFLOW_PARITY_SHARDS", DefaultParityShards)
}

func MaxInflightFrames() int {
	return envInt("UNIFLOW_MAX_INFLIGHT_FRAMES", DefaultMaxInflight)
}

func FrameTTL() time.Duration {
	seconds := envInt("UNIFLOW_FRAME_TTL_SEC", int(DefaultFrameTTL/time.Second))
	if seconds <= 0 {
		return DefaultFrameTTL
	}
	return time.Duration(seconds) * time.Second
}

func UDPRcvBuf() int {
	return envInt("UNIFLOW_UDP_RCVBUF", DefaultUDPRcvBuf)
}

func SendPPS() int {
	return envInt("UNIFLOW_SEND_PPS", DefaultSendPPS)
}

func VerifyPacketHash() bool {
	return envBool("UNIFLOW_VERIFY_PACKET_HASH", DefaultVerifyPacketHash)
}

func envString(name, defaultVal string) string {
	if raw := os.Getenv(name); raw != "" {
		return raw
	}
	return defaultVal
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

func envBool(name string, defaultVal bool) bool {
	raw := os.Getenv(name)
	if raw == "" {
		return defaultVal
	}
	val, err := strconv.ParseBool(raw)
	if err != nil {
		slog.Error("invalid env", "name", name, "value", raw)
		os.Exit(1)
	}
	return val
}
