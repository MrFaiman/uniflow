package sender

import (
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/MrFaiman/uniflow/internal/config"
	"github.com/MrFaiman/uniflow/internal/ipc"
	"github.com/MrFaiman/uniflow/internal/wire"
)

type Worker struct {
	index     int
	frameID   atomic.Uint64
	udpConn   *net.UDPConn
	dest      *net.UDPAddr
	shardSize int
	parity    int
	sendPPS   int
}

func RunWorker(index int) error {
	config.LoadDotEnv()

	path := config.WorkerSocketPath(index)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("mkdir worker socket dir: %w", err)
	}
	if err := os.RemoveAll(path); err != nil {
		return fmt.Errorf("remove old socket: %w", err)
	}

	listener, err := ipc.ListenUnix(path)
	if err != nil {
		return fmt.Errorf("listen worker socket: %w", err)
	}
	defer func() {
		_ = listener.Close()
		_ = os.RemoveAll(path)
	}()

	dest, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", config.RouterHost(), config.RouterPortForWorker(index)))
	if err != nil {
		return fmt.Errorf("resolve router: %w", err)
	}

	udpConn, err := net.DialUDP("udp", nil, dest)
	if err != nil {
		return fmt.Errorf("dial udp: %w", err)
	}
	defer func() { _ = udpConn.Close() }()

	worker := &Worker{
		index:     index,
		udpConn:   udpConn,
		dest:      dest,
		shardSize: config.ShardSize(),
		parity:    config.ParityShards(),
		sendPPS:   config.SendPPS(),
	}

	slog.Info("sender worker ready", "index", index, "socket", path, "dest", dest.String())

	for {
		conn, err := listener.Accept()
		if err != nil {
			slog.Warn("accept failed", "index", index, "err", err)
			continue
		}
		go worker.handleConn(conn)
	}
}

func (w *Worker) handleConn(conn net.Conn) {
	defer func() { _ = conn.Close() }()

	var pace <-chan time.Time
	if w.sendPPS > 0 {
		ticker := time.NewTicker(time.Second / time.Duration(w.sendPPS))
		defer ticker.Stop()
		pace = ticker.C
	}

	for {
		payload, err := ipc.ReadMessage(conn)
		if err != nil {
			return
		}
		if err := w.sendPayload(payload); err != nil {
			slog.Warn("send payload failed", "index", w.index, "err", err)
		}
		if pace != nil {
			<-pace
		}
	}
}

func (w *Worker) sendPayload(payload []byte) error {
	frameID := w.frameID.Add(1)
	shards, err := wire.ShardPayload(payload, frameID, uint32(w.index), w.shardSize, w.parity)
	if err != nil {
		return err
	}

	for _, shard := range shards {
		data, err := wire.MarshalShard(shard)
		if err != nil {
			return err
		}
		if _, err := w.udpConn.Write(data); err != nil {
			return err
		}
	}
	return nil
}
