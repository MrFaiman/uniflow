package tests

import (
	"bytes"
	"io"
	"net"
	"path/filepath"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/internal/ipc"
)

type memoryConn struct {
	r *bytes.Buffer
	w *bytes.Buffer
}

func (m *memoryConn) Read(p []byte) (int, error)  { return m.r.Read(p) }
func (m *memoryConn) Write(p []byte) (int, error) { return m.w.Write(p) }
func (m *memoryConn) Close() error                { return nil }
func (m *memoryConn) LocalAddr() net.Addr         { return nil }
func (m *memoryConn) RemoteAddr() net.Addr        { return nil }
func (m *memoryConn) SetDeadline(time.Time) error { return nil }
func (m *memoryConn) SetReadDeadline(time.Time) error  { return nil }
func (m *memoryConn) SetWriteDeadline(time.Time) error { return nil }

func TestWriteReadMessageRoundTrip(t *testing.T) {
	payload := []byte("hello protobuf framing")
	conn := &memoryConn{r: bytes.NewBuffer(nil), w: bytes.NewBuffer(nil)}

	if err := ipc.WriteMessage(conn, payload); err != nil {
		t.Fatalf("write: %v", err)
	}

	conn.r = bytes.NewBuffer(conn.w.Bytes())
	conn.w = bytes.NewBuffer(nil)

	got, err := ipc.ReadMessage(conn)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if !bytes.Equal(payload, got) {
		t.Fatalf("payload mismatch")
	}
}

func TestReadMessagePartialHeader(t *testing.T) {
	conn := &memoryConn{r: bytes.NewBuffer([]byte{0, 0, 0}), w: bytes.NewBuffer(nil)}
	if _, err := ipc.ReadMessage(conn); err == nil {
		t.Fatal("expected error for partial header")
	}
}

func TestReadMessageInvalidSize(t *testing.T) {
	conn := &memoryConn{r: bytes.NewBuffer([]byte{0, 0, 0, 0}), w: bytes.NewBuffer(nil)}
	if _, err := ipc.ReadMessage(conn); err == nil {
		t.Fatal("expected error for zero size")
	}
}

func TestReadMessageUsesExactLength(t *testing.T) {
	var buf bytes.Buffer
	connWriter := &memoryConn{r: bytes.NewBuffer(nil), w: &buf}
	payload := []byte("exact")
	if err := ipc.WriteMessage(connWriter, payload); err != nil {
		t.Fatalf("write: %v", err)
	}

	data := buf.Bytes()
	conn := &memoryConn{r: bytes.NewBuffer(data), w: bytes.NewBuffer(nil)}
	got, err := ipc.ReadMessage(conn)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if !bytes.Equal(payload, got) {
		t.Fatalf("payload mismatch")
	}
	if conn.r.Len() != 0 {
		t.Fatalf("expected no trailing bytes")
	}
}

func TestReadMessageEOF(t *testing.T) {
	conn := &memoryConn{r: bytes.NewBuffer(nil), w: bytes.NewBuffer(nil)}
	_, err := ipc.ReadMessage(conn)
	if err != io.EOF {
		t.Fatalf("expected EOF, got %v", err)
	}
}

func TestDialUnixWithRetryTimesOut(t *testing.T) {
	_, err := ipc.DialUnixWithRetry(
		"/tmp/uniflow-missing.sock",
		10*time.Millisecond,
		50*time.Millisecond,
	)
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestDialUnixWithRetrySucceeds(t *testing.T) {
	path := filepath.Join(t.TempDir(), "dial.sock")
	listener, err := ipc.ListenUnix(path)
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer func() { _ = listener.Close() }()

	go func() {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		_ = conn.Close()
	}()

	conn, err := ipc.DialUnixWithRetry(path, 10*time.Millisecond, time.Second)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	_ = conn.Close()
}
