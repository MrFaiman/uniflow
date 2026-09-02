package tests

import (
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"google.golang.org/protobuf/proto"

	"github.com/MrFaiman/uniflow/internal/config"
	"github.com/MrFaiman/uniflow/internal/ipc"
	"github.com/MrFaiman/uniflow/pb"
)

func TestDemuxByTargetReceiver(t *testing.T) {
	t.Setenv("UNIFLOW_WORKER_SOCKET_DIR", t.TempDir())
	t.Setenv("UNIFLOW_WORKERS", "3")

	workers := config.Workers()
	received := make([][][]byte, workers)
	var mu sync.Mutex

	servers := make([]net.Listener, workers)
	for i := 0; i < workers; i++ {
		path := config.WorkerSocketPath(i)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("mkdir: %v", err)
		}
		ln, err := ipc.ListenUnix(path)
		if err != nil {
			t.Fatalf("listen worker %d: %v", i, err)
		}
		servers[i] = ln

		go func(idx int, listener net.Listener) {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			defer func() { _ = conn.Close() }()
			data, err := ipc.ReadMessage(conn)
			if err != nil {
				return
			}
			mu.Lock()
			received[idx] = append(received[idx], data)
			mu.Unlock()
		}(i, ln)
	}
	defer func() {
		for _, ln := range servers {
			_ = ln.Close()
		}
	}()

	for target := uint32(0); target < 3; target++ {
		packet := &pb.FilePacket{
			FileId:         "id",
			FileName:       "name",
			FileSize:       1,
			FileHash:       "a",
			PacketIndex:    target,
			TotalPackets:   1,
			TargetReceiver: target,
			Data:           []byte("x"),
			BlockIndex:     0,
			TotalBlocks:    1,
			BlockSize:      1,
			SymbolSize:     1,
		}
		data, err := proto.Marshal(packet)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}

		path := config.WorkerSocketPath(int(target))
		var conn net.Conn
		deadline := time.Now().Add(2 * time.Second)
		for time.Now().Before(deadline) {
			conn, err = net.Dial("unix", path)
			if err == nil {
				break
			}
			time.Sleep(10 * time.Millisecond)
		}
		if conn == nil {
			t.Fatalf("dial worker %d: %v", target, err)
		}
		if err := ipc.WriteMessage(conn, data); err != nil {
			t.Fatalf("write: %v", err)
		}
		_ = conn.Close()
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		total := 0
		for _, batch := range received {
			total += len(batch)
		}
		mu.Unlock()
		if total == 3 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	mu.Lock()
	defer mu.Unlock()
	for i := 0; i < workers; i++ {
		if len(received[i]) != 1 {
			t.Fatalf("worker %d got %d messages, want 1", i, len(received[i]))
		}
	}
}
