package transfer

import (
	"fmt"
	"log/slog"
	"net"
	"os"

	"github.com/MrFaiman/uniflow/pb"
)

func StartIPCServer(sender *Sender) {
	loadDotEnv()
	path := socketPath()
	_ = os.RemoveAll(path)
	listener, err := net.Listen("unix", path)
	if err != nil {
		slog.Error("listen failed", "path", path, "err", err)
		os.Exit(1)
	}
	defer func() { _ = listener.Close() }()

	slog.Info("ipc listening", "path", path)

	for {
		conn, err := listener.Accept()
		if err != nil {
			slog.Warn("accept failed", "err", err)
			continue
		}

		go func(c net.Conn) {
			defer func() { _ = c.Close() }()
			if err := handleIPCConn(c, sender); err != nil {
				slog.Error("ipc request failed", "err", err)
			}
		}(conn)
	}
}

func handleIPCConn(conn net.Conn, sender *Sender) error {
	var req pb.IPCRequest
	if err := ReadProto(conn, &req); err != nil {
		return fmt.Errorf("read request: %w", err)
	}

	slog.Info(
		"ipc command",
		"command", req.Command,
		"target_ip", req.TargetIp,
		"object_id", req.ObjectId,
		"coordinated", req.Coordinated,
	)

	resp := &pb.IPCResponse{Success: true, Message: fmt.Sprintf("handled %s", req.Command)}

	if req.TargetIp != "" {
		if err := sender.SetTarget(req.TargetIp, req.Coordinated); err != nil {
			resp.Success = false
			resp.Message = err.Error()
		}
	}

	if resp.Success {
		if err := sender.handleIPCCommand(
			req.Command,
			req.Data,
			req.ObjectId,
			req.Coordinated,
		); err != nil {
			resp.Success = false
			resp.Message = err.Error()
		}
	}

	if err := WriteProto(conn, resp); err != nil {
		return fmt.Errorf("write response: %w", err)
	}
	return nil
}
