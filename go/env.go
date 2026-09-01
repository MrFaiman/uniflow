package main

import (
	"log/slog"
	"os"
	"path/filepath"

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
