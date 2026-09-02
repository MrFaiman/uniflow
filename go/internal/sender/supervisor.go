package sender

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/MrFaiman/uniflow/internal/child"
	"github.com/MrFaiman/uniflow/internal/config"
	"github.com/MrFaiman/uniflow/internal/ipc"
	"github.com/MrFaiman/uniflow/internal/packet"
)

func RunSupervisor() error {
	config.LoadDotEnv()
	workers := config.Workers()
	socketDir := config.WorkerSocketDir()
	if err := os.MkdirAll(socketDir, 0o755); err != nil {
		return fmt.Errorf("mkdir worker sockets: %w", err)
	}

	specs := make([]child.Spec, workers)
	for i := 0; i < workers; i++ {
		specs[i] = child.Spec{
			Name:    fmt.Sprintf("sender-%d", i),
			Args:    []string{"sender", "--index", fmt.Sprintf("%d", i)},
			Restart: true,
		}
	}

	supervisor, err := child.NewSupervisor(specs)
	if err != nil {
		return err
	}

	go func() {
		if err := supervisor.Run(); err != nil {
			slog.Error("sender supervisor failed", "err", err)
		}
	}()

	if err := waitForWorkerSockets(workers, 30*time.Second); err != nil {
		supervisor.Stop()
		return err
	}

	listener, err := ipc.ListenUnix(config.SocketPath())
	if err != nil {
		supervisor.Stop()
		return fmt.Errorf("listen ipc: %w", err)
	}
	defer func() {
		_ = listener.Close()
		_ = os.RemoveAll(config.SocketPath())
	}()

	slog.Info("sender supervisor listening", "path", config.SocketPath(), "workers", workers)

	conns := make([]net.Conn, workers)
	var connsMu sync.Mutex
	defer func() {
		connsMu.Lock()
		defer connsMu.Unlock()
		for _, conn := range conns {
			if conn != nil {
				_ = conn.Close()
			}
		}
	}()

	for {
		conn, err := listener.Accept()
		if err != nil {
			slog.Warn("accept failed", "err", err)
			continue
		}

		go handleClient(conn, workers, conns, &connsMu)
	}
}

func waitForWorkerSockets(workers int, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		ready := 0
		for i := 0; i < workers; i++ {
			if _, err := os.Stat(config.WorkerSocketPath(i)); err == nil {
				ready++
			}
		}
		if ready == workers {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("timed out waiting for worker sockets in %s", config.WorkerSocketDir())
}

func handleClient(client net.Conn, workers int, conns []net.Conn, connsMu *sync.Mutex) {
	defer func() { _ = client.Close() }()

	for {
		data, err := ipc.ReadMessage(client)
		if err != nil {
			return
		}

		target, err := packet.TargetReceiver(data)
		if err != nil {
			slog.Warn("invalid packet", "err", err)
			continue
		}
		worker := int(target) % workers

		conn, err := ensureWorkerConn(worker, conns, connsMu)
		if err != nil {
			slog.Warn("worker connection failed", "worker", worker, "err", err)
			continue
		}

		if err := ipc.WriteMessage(conn, data); err != nil {
			slog.Warn("forward failed", "worker", worker, "err", err)
			connsMu.Lock()
			_ = conn.Close()
			conns[worker] = nil
			connsMu.Unlock()
		}
	}
}

func ensureWorkerConn(worker int, conns []net.Conn, connsMu *sync.Mutex) (net.Conn, error) {
	connsMu.Lock()
	if conns[worker] != nil {
		conn := conns[worker]
		connsMu.Unlock()
		return conn, nil
	}
	connsMu.Unlock()

	path := config.WorkerSocketPath(worker)
	conn, err := ipc.DialUnixWithRetry(path, 100*time.Millisecond, 30*time.Second)
	if err != nil {
		return nil, err
	}

	connsMu.Lock()
	defer connsMu.Unlock()
	if existing := conns[worker]; existing != nil {
		_ = conn.Close()
		return existing, nil
	}
	conns[worker] = conn
	return conn, nil
}

func CleanupWorkerSockets() {
	for i := 0; i < config.Workers(); i++ {
		_ = os.RemoveAll(config.WorkerSocketPath(i))
	}
	_ = os.RemoveAll(filepath.Dir(config.WorkerSocketPath(0)))
}
