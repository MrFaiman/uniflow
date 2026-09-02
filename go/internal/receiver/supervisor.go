package receiver

import (
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/MrFaiman/uniflow/internal/child"
	"github.com/MrFaiman/uniflow/internal/config"
)

func RunSupervisor() error {
	config.LoadDotEnv()
	workers := config.Workers()

	specs := make([]child.Spec, workers)
	for i := 0; i < workers; i++ {
		specs[i] = child.Spec{
			Name:    fmt.Sprintf("receiver-%d", i),
			Args:    []string{"receiver", "--index", fmt.Sprintf("%d", i)},
			Restart: true,
		}
	}

	supervisor, err := child.NewSupervisor(specs)
	if err != nil {
		return err
	}

	slog.Info("receiver supervisor starting", "workers", workers)
	return supervisor.Run()
}

func waitForSessionManager(timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	path := config.SocketPath()
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("timed out waiting for session manager socket at %s", path)
}
