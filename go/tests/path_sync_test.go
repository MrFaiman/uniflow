package tests

import (
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/pb"
	"github.com/MrFaiman/uniflow/transfer"
	"google.golang.org/protobuf/proto"
)

func TestNestedFileRoundtrip(t *testing.T) {
	recvDir := t.TempDir()
	recv, conn := startTestReceiver(t, recvDir, 19200)
	defer recv.Close()
	defer conn.Close()

	content := []byte("nested payload")
	tmp := filepath.Join(t.TempDir(), "file.txt")
	if err := os.WriteFile(tmp, content, 0o644); err != nil {
		t.Fatal(err)
	}

	sender, err := transfer.NewSender([]int{19200})
	if err != nil {
		t.Fatal(err)
	}
	defer sender.Close()
	if err := sender.SetTarget("127.0.0.1", false); err != nil {
		t.Fatal(err)
	}
	if err := sender.SendFile(tmp, "sub/nested/file.txt", 1, false); err != nil {
		t.Fatal(err)
	}

	waitForFile(t, filepath.Join(recvDir, "sub", "nested", "file.txt"), content)
}

func TestPathOperationMkdir(t *testing.T) {
	recvDir := t.TempDir()
	recv, conn := startTestReceiver(t, recvDir, 19201)
	defer recv.Close()
	defer conn.Close()

	if err := sendPathOp(conn, &pb.PathOperation{
		Op:           pb.PathOperation_MKDIR,
		RelativePath: "new/nested/dir",
		IsDirectory:  true,
	}); err != nil {
		t.Fatal(err)
	}

	waitForDir(t, filepath.Join(recvDir, "new", "nested", "dir"))
}

func TestPathOperationRemoveFile(t *testing.T) {
	recvDir := t.TempDir()
	target := filepath.Join(recvDir, "remove-me.txt")
	if err := os.WriteFile(target, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	recv, conn := startTestReceiver(t, recvDir, 19202)
	defer recv.Close()
	defer conn.Close()

	if err := sendPathOp(conn, &pb.PathOperation{
		Op:           pb.PathOperation_REMOVE,
		RelativePath: "remove-me.txt",
	}); err != nil {
		t.Fatal(err)
	}

	waitUntilAbsent(t, target, 2*time.Second)
}

func TestPathOperationRemoveDirectoryRecursive(t *testing.T) {
	recvDir := t.TempDir()
	tree := filepath.Join(recvDir, "old", "tree")
	if err := os.MkdirAll(tree, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(tree, "leaf.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	recv, conn := startTestReceiver(t, recvDir, 19203)
	defer recv.Close()
	defer conn.Close()

	if err := sendPathOp(conn, &pb.PathOperation{
		Op:           pb.PathOperation_REMOVE,
		RelativePath: "old/tree",
		IsDirectory:  true,
	}); err != nil {
		t.Fatal(err)
	}

	waitUntilAbsent(t, tree, 2*time.Second)
}

func TestPathOperationRenameFile(t *testing.T) {
	recvDir := t.TempDir()
	src := filepath.Join(recvDir, "before.txt")
	dest := filepath.Join(recvDir, "after", "renamed.txt")
	if err := os.WriteFile(src, []byte("rename me"), 0o644); err != nil {
		t.Fatal(err)
	}

	recv, conn := startTestReceiver(t, recvDir, 19204)
	defer recv.Close()
	defer conn.Close()

	if err := sendPathOp(conn, &pb.PathOperation{
		Op:               pb.PathOperation_RENAME,
		RelativePath:     "before.txt",
		DestRelativePath: "after/renamed.txt",
	}); err != nil {
		t.Fatal(err)
	}

	waitForFile(t, dest, []byte("rename me"))
	waitUntilAbsent(t, src, 2*time.Second)
}

func TestPathOperationRenameDirectory(t *testing.T) {
	recvDir := t.TempDir()
	src := filepath.Join(recvDir, "dir-a")
	dest := filepath.Join(recvDir, "dir-b")
	if err := os.MkdirAll(filepath.Join(src, "child"), 0o755); err != nil {
		t.Fatal(err)
	}

	recv, conn := startTestReceiver(t, recvDir, 19205)
	defer recv.Close()
	defer conn.Close()

	if err := sendPathOp(conn, &pb.PathOperation{
		Op:               pb.PathOperation_RENAME,
		RelativePath:     "dir-a",
		DestRelativePath: "dir-b",
		IsDirectory:      true,
	}); err != nil {
		t.Fatal(err)
	}

	waitForDir(t, filepath.Join(dest, "child"))
	waitUntilAbsent(t, src, 2*time.Second)
}

func sendPathOp(conn *net.UDPConn, op *pb.PathOperation) error {
	datagram := &pb.UdpDatagram{
		Payload: &pb.UdpDatagram_PathOp{PathOp: op},
	}
	payload, err := proto.Marshal(datagram)
	if err != nil {
		return err
	}
	_, err = conn.Write(payload)
	return err
}

func waitUntilAbsent(t *testing.T, path string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("expected %s to be removed", path)
}

func waitForDir(t *testing.T, path string) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		info, err := os.Stat(path)
		if err == nil && info.IsDir() {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("directory %s not created", path)
}
