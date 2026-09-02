package transfer

import (
	"log/slog"
	"os"
)

func RunSend() {
	loadDotEnv()
	destPorts := udpPorts()
	sender, err := NewSender(destPorts)
	if err != nil {
		slog.Error("sender init failed", "err", err)
		os.Exit(1)
	}
	defer sender.Close()
	slog.Info("sender ready", "dest_ports", destPorts)
	StartIPCServer(sender)
}

func RunRecv(dir string) {
	loadDotEnv()
	if dir == "" {
		dir = receiveDir()
	}
	port := udpPort()
	mustMkdir(dir)
	recv, err := NewReceiver(port, dir)
	if err != nil {
		slog.Error("receiver init failed", "err", err)
		os.Exit(1)
	}
	defer recv.Close()
	slog.Info("receiver listening", "port", port, "dir", dir)
	recvErr := recv.Run()
	slog.Error("receiver stopped", "err", recvErr)
	os.Exit(1)
}
