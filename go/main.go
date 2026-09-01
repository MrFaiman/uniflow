package main

import (
	"fmt"
	"log/slog"
	"net"
	"os"

	"github.com/MrFaiman/uniflow/pb"
)

//go:generate protoc --go_out=. --go_opt=module=github.com/MrFaiman/uniflow -I../schemas ../schemas/message.proto

func startServer() {
	loadDotEnv()
	path := socketPath()
	os.RemoveAll(path)
	listener, err := net.Listen("unix", path)
	if err != nil {
		slog.Error("listen failed", "path", path, "err", err)
		os.Exit(1)
	}
	defer listener.Close()

	slog.Info("server listening", "path", path)

	for {
		conn, err := listener.Accept()
		if err != nil {
			slog.Warn("accept failed", "err", err)
			continue
		}

		go func(c net.Conn) {
			defer c.Close()
			var req pb.IPCRequest

			if err := ReadProto(c, &req); err != nil {
				slog.Error("read request failed", "err", err)
				return
			}

			slog.Info("received command", "command", req.Command)

			resp := &pb.IPCResponse{
				Success: true,
				Message: fmt.Sprintf("handled %s", req.Command),
			}
			if err := WriteProto(c, resp); err != nil {
				slog.Error("write response failed", "err", err)
			}
		}(conn)
	}
}

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	startServer()
}
