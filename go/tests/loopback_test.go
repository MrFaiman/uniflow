package tests

import (
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"google.golang.org/protobuf/proto"

	"github.com/MrFaiman/uniflow/internal/chaos"
	"github.com/MrFaiman/uniflow/internal/config"
	"github.com/MrFaiman/uniflow/internal/ipc"
	"github.com/MrFaiman/uniflow/internal/packet"
	"github.com/MrFaiman/uniflow/internal/receiver"
	"github.com/MrFaiman/uniflow/internal/sender"
	"github.com/MrFaiman/uniflow/pb"
)

func TestLoopbackWithChaos(t *testing.T) {
	receiverBase := 29000
	routerBase := 29100
	tmp := t.TempDir()
	sessionPath := filepath.Join(tmp, "sess.sock")
	workerDir := filepath.Join(os.TempDir(), fmt.Sprintf("uf%d", os.Getpid()))

	if err := os.MkdirAll(workerDir, 0o755); err != nil {
		t.Fatalf("mkdir workers: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(workerDir) })

	t.Setenv("IPC_SOCKET_PATH", sessionPath)
	t.Setenv("UNIFLOW_WORKER_SOCKET_DIR", workerDir)
	t.Setenv("UNIFLOW_WORKERS", "3")
	t.Setenv("PORT", strconv.Itoa(receiverBase))
	t.Setenv("UNIFLOW_ROUTER_PORT", strconv.Itoa(routerBase))
	t.Setenv("UNIFLOW_ROUTER_HOST", "127.0.0.1")
	t.Setenv("UNIFLOW_SHARD_SIZE", "600")
	t.Setenv("UNIFLOW_PARITY_SHARDS", "2")
	t.Setenv("UNIFLOW_MAX_INFLIGHT_FRAMES", "4096")
	t.Setenv("UNIFLOW_FRAME_TTL_SEC", "5")
	t.Setenv("UNIFLOW_VERIFY_PACKET_HASH", "1")

	receiverPorts := []int{receiverBase, receiverBase + 1, receiverBase + 2}
	routerPorts := []int{routerBase, routerBase + 1, routerBase + 2}
	received := make(chan []byte, 256)
	var receivedMu sync.Mutex
	receivedSet := make(map[string]struct{})

	sessionListener, err := ipc.ListenUnix(sessionPath)
	if err != nil {
		t.Fatalf("session listen: %v", err)
	}
	defer func() {
		_ = sessionListener.Close()
		_ = os.RemoveAll(sessionPath)
	}()

	go func() {
		for {
			conn, err := sessionListener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()
				for {
					data, err := ipc.ReadMessage(c)
					if err != nil {
						return
					}
					received <- data
				}
			}(conn)
		}
	}()

	relay, err := chaos.NewRelay(chaos.Config{
		Loss:        0.03,
		BitFlip:     0.03,
		Misroute:    0.03,
		Seed:        42,
		ListenPorts: routerPorts,
		DestPorts:   receiverPorts,
		DestHost:    "127.0.0.1",
		ListenIP:    "127.0.0.1",
	})
	if err != nil {
		t.Fatalf("relay: %v", err)
	}
	defer relay.Close()

	if _, err := relay.Start(); err != nil {
		t.Fatalf("relay start: %v", err)
	}

	for i := 0; i < 3; i++ {
		idx := i
		go func() {
			if err := receiver.RunWorker(idx); err != nil {
				t.Errorf("receiver worker %d: %v", idx, err)
			}
		}()
	}

	for i := 0; i < 3; i++ {
		idx := i
		go func() {
			if err := sender.RunWorker(idx); err != nil {
				t.Errorf("sender worker %d: %v", idx, err)
			}
		}()
	}

	waitForWorkerSockets(t, 3, 10*time.Second)

	const total = 60
	sent := make([][]byte, 0, total)
	for i := 0; i < total; i++ {
		pkt := buildTestPacket(i)
		data, err := proto.MarshalOptions{Deterministic: true}.Marshal(pkt)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		hash, err := packet.CalculatePacketHash(pkt)
		if err != nil {
			t.Fatalf("hash: %v", err)
		}
		pkt.PacketHash = hash
		data, err = proto.MarshalOptions{Deterministic: true}.Marshal(pkt)
		if err != nil {
			t.Fatalf("marshal with hash: %v", err)
		}
		sent = append(sent, data)

		worker := int(pkt.TargetReceiver)
		conn, err := ipc.DialUnixWithRetry(config.WorkerSocketPath(worker), 50*time.Millisecond, 15*time.Second)
		if err != nil {
			t.Fatalf("dial sender worker: %v", err)
		}
		if err := ipc.WriteMessage(conn, data); err != nil {
			_ = conn.Close()
			t.Fatalf("write: %v", err)
		}
		_ = conn.Close()
	}

	deadline := time.Now().Add(15 * time.Second)
	for len(receivedSet) < total && time.Now().Before(deadline) {
		select {
		case data := <-received:
			ok, err := packet.VerifyPacketHash(data)
			if err != nil {
				t.Fatalf("verify delivered packet: %v", err)
			}
			if !ok {
				t.Fatal("delivered corrupted packet to session manager")
			}
			receivedMu.Lock()
			receivedSet[hex.EncodeToString(data)] = struct{}{}
			receivedMu.Unlock()
		case <-time.After(100 * time.Millisecond):
		}
	}

	receivedMu.Lock()
	delivered := len(receivedSet)
	receivedMu.Unlock()

	if delivered < int(float64(total)*0.95) {
		t.Fatalf("delivered %d/%d packets, expected at least 95%%", delivered, total)
	}
}

func waitForWorkerSockets(t *testing.T, workers int, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		ready := 0
		for i := 0; i < workers; i++ {
			if _, err := os.Stat(config.WorkerSocketPath(i)); err == nil {
				ready++
			}
		}
		if ready == workers {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("timed out waiting for sender worker sockets")
}

func buildTestPacket(index int) *pb.FilePacket {
	return &pb.FilePacket{
		FileId:         "loopback-file",
		FileName:       "loopback.bin",
		FileSize:       1024,
		FileHash:       strings.Repeat("b", 64),
		PacketIndex:    uint32(index),
		TotalPackets:   60,
		TargetReceiver: uint32(index % 3),
		Data:           bytesRepeat(index),
		BlockIndex:     0,
		TotalBlocks:    1,
		BlockSize:      1024,
		SymbolSize:     1400,
		BlockOffset:    0,
	}
}

func bytesRepeat(seed int) []byte {
	out := make([]byte, 1400)
	for i := range out {
		out[i] = byte(seed + i)
	}
	return out
}
