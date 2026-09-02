package child

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

type Spec struct {
	Name    string
	Args    []string
	Restart bool
}

type Supervisor struct {
	executable string
	specs      []Spec
	mu         sync.Mutex
	children   map[string]*exec.Cmd
	cancel     context.CancelFunc
}

func NewSupervisor(specs []Spec) (*Supervisor, error) {
	executable, err := os.Executable()
	if err != nil {
		return nil, fmt.Errorf("resolve executable: %w", err)
	}
	return &Supervisor{
		executable: executable,
		specs:      specs,
		children:   make(map[string]*exec.Cmd),
	}, nil
}

func (s *Supervisor) Run() error {
	ctx, cancel := context.WithCancel(context.Background())
	s.cancel = cancel

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	var wg sync.WaitGroup
	for _, spec := range s.specs {
		wg.Add(1)
		go func(spec Spec) {
			defer wg.Done()
			s.runChildLoop(ctx, spec)
		}(spec)
	}

	select {
	case <-sigCh:
		cancel()
	case <-ctx.Done():
	}

	s.stopAll()
	wg.Wait()
	return nil
}

func (s *Supervisor) runChildLoop(ctx context.Context, spec Spec) {
	backoff := time.Second
	for {
		if ctx.Err() != nil {
			return
		}

		cmd := exec.CommandContext(ctx, s.executable, spec.Args...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.Env = os.Environ()

		s.mu.Lock()
		s.children[spec.Name] = cmd
		s.mu.Unlock()

		slog.Info("starting child", "name", spec.Name, "args", spec.Args)
		err := cmd.Run()

		s.mu.Lock()
		delete(s.children, spec.Name)
		s.mu.Unlock()

		if ctx.Err() != nil {
			return
		}
		if !spec.Restart {
			slog.Error("child exited", "name", spec.Name, "err", err)
			return
		}

		slog.Warn("child exited, restarting", "name", spec.Name, "err", err, "backoff", backoff)
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
		if backoff < 30*time.Second {
			backoff *= 2
		}
	}
}

func (s *Supervisor) stopAll() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for name, cmd := range s.children {
		if cmd.Process != nil {
			slog.Info("stopping child", "name", name, "pid", cmd.Process.Pid)
			_ = cmd.Process.Signal(syscall.SIGTERM)
		}
	}
}

func (s *Supervisor) Stop() {
	if s.cancel != nil {
		s.cancel()
	}
}
