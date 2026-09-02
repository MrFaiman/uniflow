package main

import (
	"fmt"
	"log/slog"
	"os"

	"github.com/akamensky/argparse"

	"github.com/MrFaiman/uniflow/transfer"
)

//go:generate protoc --go_out=. --go_opt=module=github.com/MrFaiman/uniflow -I../schemas ../schemas/message.proto ../schemas/flute.proto

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))

	parser := argparse.NewParser("uniflow", "unidirectional file transfer")
	sendCmd := parser.NewCommand("send", "send files")
	recvCmd := parser.NewCommand("recv", "receive files")
	recvDir := recvCmd.StringPositional(&argparse.Options{
		Help: "directory for received files",
	})

	if err := parser.Parse(os.Args); err != nil {
		fmt.Fprint(os.Stderr, parser.Usage(err))
		os.Exit(1)
	}

	switch {
	case sendCmd.Happened():
		transfer.RunSend()
	case recvCmd.Happened():
		transfer.RunRecv(*recvDir)
	}
}
