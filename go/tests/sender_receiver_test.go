package tests

import (
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/transfer"
)

func TestSenderReceiverRoundtrip(t *testing.T) {
	recvDir := t.TempDir()
	port := 19000

	t.Setenv("UNIFLOW_WORKER_COUNT", "1")
	t.Setenv("UNIFLOW_WORKER_INDEX", "0")
	t.Setenv("UNIFLOW_SESSION_ID", "99")

	recv, err := transfer.NewReceiver(port, recvDir)
	if err != nil {
		t.Fatal(err)
	}
	defer recv.Close()

	go func() {
		_ = recv.Run()
	}()

	sender, err := transfer.NewSender([]int{port})
	if err != nil {
		t.Fatal(err)
	}
	defer sender.Close()

	if err := sender.SetTarget("127.0.0.1", false); err != nil {
		t.Fatal(err)
	}

	tmp := filepath.Join(t.TempDir(), "payload.bin")
	content := []byte("uniflow roundtrip payload")
	if err := os.WriteFile(tmp, content, 0o644); err != nil {
		t.Fatal(err)
	}

	if err := sender.SendFile(tmp, "payload.bin", 1, false); err != nil {
		t.Fatal(err)
	}

	waitForFile(t, filepath.Join(recvDir, "payload.bin"), content)
}

func TestCoordinatedSenderReceiverRoundtrip(t *testing.T) {
	recvDir := t.TempDir()
	ports := []int{19010, 19011, 19012}

	t.Setenv("UNIFLOW_WORKER_COUNT", "3")
	t.Setenv("UNIFLOW_SESSION_ID", "42")

	receivers := make([]*transfer.Receiver, len(ports))
	for i, port := range ports {
		t.Setenv("UNIFLOW_WORKER_INDEX", strconv.Itoa(i))
		recv, err := transfer.NewReceiver(port, recvDir)
		if err != nil {
			t.Fatal(err)
		}
		receivers[i] = recv
		defer recv.Close()
		go func(r *transfer.Receiver) {
			_ = r.Run()
		}(recv)
	}

	senders := make([]*transfer.Sender, len(ports))
	for i := range ports {
		t.Setenv("UNIFLOW_WORKER_INDEX", strconv.Itoa(i))
		sender, err := transfer.NewSender(ports)
		if err != nil {
			t.Fatal(err)
		}
		senders[i] = sender
		defer sender.Close()
		if err := sender.SetTarget("127.0.0.1", true); err != nil {
			t.Fatal(err)
		}
	}

	tmp := filepath.Join(t.TempDir(), "payload.bin")
	content := []byte("coordinated chunk payload")
	if err := os.WriteFile(tmp, content, 0o644); err != nil {
		t.Fatal(err)
	}

	for _, sender := range senders {
		if err := sender.SendFile(tmp, "payload.bin", 1, true); err != nil {
			t.Fatal(err)
		}
	}

	waitForFile(t, filepath.Join(recvDir, "payload.bin"), content)
}

func waitForFile(t *testing.T, path string, want []byte) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		data, err := os.ReadFile(path)
		if err == nil && string(data) == string(want) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("file %s not received: %v", path, err)
	}
	t.Fatalf("file %s got %q want %q", path, data, want)
}
