package main

import (
	"log/slog"
	"os"

	"github.com/MrFaiman/uniflow/transfer"
)

//go:generate protoc --go_out=. --go_opt=module=github.com/MrFaiman/uniflow -I../schemas ../schemas/message.proto ../schemas/flute.proto

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))

	if len(os.Args) < 2 {
		slog.Error("usage: uniflow send | recv [dir]")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "send":
		transfer.RunSend()
	case "recv":
		dir := ""
		if len(os.Args) >= 3 {
			dir = os.Args[2]
		}
		transfer.RunRecv(dir)
	default:
		slog.Error("unknown command", "cmd", os.Args[1])
		os.Exit(1)
	}
}
