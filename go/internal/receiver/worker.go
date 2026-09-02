package receiver

import (
	"fmt"
	"log/slog"
	"net"
	"syscall"
	"time"

	"github.com/MrFaiman/uniflow/internal/config"
	"github.com/MrFaiman/uniflow/internal/ipc"
	"github.com/MrFaiman/uniflow/internal/packet"
	"github.com/MrFaiman/uniflow/internal/wire"
)

type Worker struct {
	index        int
	reassembler  *Reassembler
	verifyHash   bool
	sessionConn  net.Conn
}

func RunWorker(index int) error {
	config.LoadDotEnv()

	if err := waitForSessionManager(60 * time.Second); err != nil {
		return err
	}

	sessionConn, err := ipc.DialUnixWithRetry(config.SocketPath(), time.Second, 30*time.Second)
	if err != nil {
		return fmt.Errorf("connect session manager: %w", err)
	}
	defer func() { _ = sessionConn.Close() }()

	addr := &net.UDPAddr{
		IP:   net.IPv4zero,
		Port: config.PortForWorker(index),
	}
	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return fmt.Errorf("listen udp: %w", err)
	}
	defer func() { _ = conn.Close() }()

	if rcvBuf := config.UDPRcvBuf(); rcvBuf > 0 {
		if err := conn.SetReadBuffer(rcvBuf); err != nil {
			slog.Warn("set rcvbuf failed", "err", err)
		}
	}

	worker := &Worker{
		index:       index,
		reassembler: NewReassembler(config.MaxInflightFrames(), config.FrameTTL()),
		verifyHash:  config.VerifyPacketHash(),
		sessionConn: sessionConn,
	}

	slog.Info("receiver worker ready", "index", index, "port", config.PortForWorker(index))

	buf := make([]byte, 65535)
	for {
		n, _, err := conn.ReadFromUDP(buf)
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				continue
			}
			if err == syscall.EINTR {
				continue
			}
			return fmt.Errorf("read udp: %w", err)
		}
		if err := worker.handleDatagram(buf[:n]); err != nil {
			slog.Debug("datagram dropped", "index", index, "err", err)
		}
	}
}

func (w *Worker) handleDatagram(data []byte) error {
	shard, err := wire.UnmarshalShard(data)
	if err != nil {
		return fmt.Errorf("unmarshal shard: %w", err)
	}

	ok, err := wire.VerifyShardChecksum(shard)
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("checksum mismatch")
	}

	payload, ready, err := w.reassembler.AddAndReconstruct(shard, wire.ReconstructPayload)
	if err != nil {
		return err
	}
	if !ready {
		return nil
	}

	if w.verifyHash {
		valid, err := packet.VerifyPacketHash(payload)
		if err != nil {
			return err
		}
		if !valid {
			return fmt.Errorf("packet hash mismatch")
		}
	}

	return ipc.WriteMessage(w.sessionConn, payload)
}
