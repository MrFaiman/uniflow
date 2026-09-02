package main

import (
	"fmt"
	"log/slog"
	"os"

	"github.com/akamensky/argparse"

	"github.com/MrFaiman/uniflow/internal/receiver"
	"github.com/MrFaiman/uniflow/internal/sender"
)

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))

	parser := argparse.NewParser("uniflow", "Unidirectional file transfer network layer")
	sendCmd := parser.NewCommand("send", "Run TX supervisor and sender workers")
	sendFolder := sendCmd.StringPositional(&argparse.Options{
		Help: "Outgoing folder (used by Python File Monitor; ignored by Go senders)",
	})
	sendRouter := sendCmd.StringPositional(&argparse.Options{
		Help: "Router hostname for UDP destination (sets UNIFLOW_ROUTER_HOST)",
	})
	senderCmd := parser.NewCommand("sender", "Run a single sender worker")
	recvCmd := parser.NewCommand("recv", "Run RX supervisor and receiver workers")
	receiveCmd := parser.NewCommand("receive", "Run RX supervisor and receiver workers")
	recvFolder := recvCmd.StringPositional(&argparse.Options{
		Help: "Receive folder (used by Python Session Manager; ignored by Go receivers)",
	})
	receiveFolder := receiveCmd.StringPositional(&argparse.Options{
		Help: "Receive folder (used by Python Session Manager; ignored by Go receivers)",
	})
	receiverCmd := parser.NewCommand("receiver", "Run a single receiver worker")

	senderIndex := senderCmd.Int("", "index", &argparse.Options{Required: true, Help: "Sender worker index"})
	receiverIndex := receiverCmd.Int("", "index", &argparse.Options{Required: true, Help: "Receiver worker index"})

	if err := parser.Parse(os.Args); err != nil {
		fmt.Fprint(os.Stderr, parser.Usage(err))
		os.Exit(1)
	}

	var runErr error
	switch {
	case sendCmd.Happened():
		if sendFolder != nil && *sendFolder != "" {
			slog.Info("watch folder is handled by Python File Monitor", "folder", *sendFolder)
		}
		if sendRouter != nil && *sendRouter != "" {
			if err := os.Setenv("UNIFLOW_ROUTER_HOST", *sendRouter); err != nil {
				runErr = fmt.Errorf("set router host: %w", err)
				break
			}
			slog.Info("router host configured", "host", *sendRouter)
		}
		runErr = sender.RunSupervisor()
	case senderCmd.Happened():
		runErr = sender.RunWorker(*senderIndex)
	case recvCmd.Happened(), receiveCmd.Happened():
		folder := recvFolder
		if receiveCmd.Happened() {
			folder = receiveFolder
		}
		if folder != nil && *folder != "" {
			slog.Info("receive folder is handled by Python Session Manager", "folder", *folder)
		}
		runErr = receiver.RunSupervisor()
	case receiverCmd.Happened():
		runErr = receiver.RunWorker(*receiverIndex)
	default:
		fmt.Fprint(os.Stderr, parser.Usage(nil))
		os.Exit(1)
	}

	if runErr != nil {
		slog.Error("uniflow failed", "err", runErr)
		os.Exit(1)
	}
}
