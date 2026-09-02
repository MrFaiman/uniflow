package ipc

import (
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"os"
	"time"
)

const MaxMessageSize = 2 * 1024 * 1024

func WriteMessage(conn net.Conn, data []byte) error {
	if len(data) > MaxMessageSize {
		return fmt.Errorf("message too large: %d", len(data))
	}

	header := make([]byte, 4)
	binary.BigEndian.PutUint32(header, uint32(len(data)))

	if _, err := conn.Write(header); err != nil {
		return err
	}
	_, err := conn.Write(data)
	return err
}

func ReadMessage(conn net.Conn) ([]byte, error) {
	header := make([]byte, 4)
	if _, err := io.ReadFull(conn, header); err != nil {
		return nil, err
	}

	size := binary.BigEndian.Uint32(header)
	if size == 0 || size > MaxMessageSize {
		return nil, fmt.Errorf("invalid message size: %d", size)
	}

	data := make([]byte, size)
	if _, err := io.ReadFull(conn, data); err != nil {
		return nil, err
	}
	return data, nil
}

func ListenUnix(path string) (net.Listener, error) {
	if err := os.RemoveAll(path); err != nil {
		return nil, err
	}
	return net.Listen("unix", path)
}

func DialUnixWithRetry(path string, interval, timeout time.Duration) (net.Conn, error) {
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	if timeout <= 0 {
		timeout = 30 * time.Second
	}

	deadline := time.Now().Add(timeout)
	var lastErr error
	for time.Now().Before(deadline) {
		conn, err := net.Dial("unix", path)
		if err == nil {
			return conn, nil
		}
		lastErr = err
		time.Sleep(interval)
	}
	return nil, fmt.Errorf("dial unix %s: timed out after %s: %w", path, timeout, lastErr)
}
