package transfer

import (
	"fmt"
	"log/slog"
	"net"
	"os"

	"github.com/MrFaiman/uniflow/pb"
)

// sessionManagerSocket returns the Unix Domain Socket the local Session
// Manager listens on, or "" when none is configured (in which case the
// Receiver falls back to assembling files itself, which keeps the Go
// package usable standalone and in unit tests).
func sessionManagerSocket() string {
	return os.Getenv("UNIFLOW_SESSION_SOCKET")
}

// reportBlock tells the local Session Manager that one source block has been
// decoded and staged. This is the RX-side IPC hop: Receivers never reconstruct
// files themselves, because only the Session Manager sees the reports from all
// three Receiver processes and can therefore know when an object is complete.
//
// This is strictly local IPC (Unix Domain Socket) on the RX machine. It is not
// an acknowledgement to TX and never crosses the network.
func reportBlock(socket string, report *pb.BlockReport) error {
	conn, err := net.Dial("unix", socket)
	if err != nil {
		return fmt.Errorf("dial session manager: %w", err)
	}
	defer func() { _ = conn.Close() }()

	if err := WriteProto(conn, report); err != nil {
		return fmt.Errorf("write block report: %w", err)
	}

	var resp pb.IPCResponse
	if err := ReadProto(conn, &resp); err != nil {
		return fmt.Errorf("read block report response: %w", err)
	}
	if !resp.Success {
		return fmt.Errorf("session manager rejected report: %s", resp.Message)
	}
	return nil
}

func (r *Receiver) reportBlockStaged(
	fdt *pb.FileDeliveryTable,
	blockIndex uint32,
	stagingPath string,
) {
	socket := sessionManagerSocket()
	if socket == "" {
		return
	}
	report := &pb.BlockReport{
		SessionId:    fdt.GetSessionId(),
		ObjectId:     fdt.GetObjectId(),
		WorkerIndex:  r.workerIndex,
		FileName:     fdt.GetFileName(),
		FileSize:     fdt.GetFileSize(),
		SourceBlocks: fdt.GetFecParams().GetSourceBlocks(),
		SymbolSize:   fdt.GetFecParams().GetSymbolSize(),
		Checksum:     fdt.GetChecksum(),
		BlockIndex:   blockIndex,
		StagingPath:  stagingPath,
	}
	if err := reportBlock(socket, report); err != nil {
		slog.Error(
			"block report failed",
			"object", fdt.GetObjectId(),
			"block", blockIndex,
			"err", err,
		)
	}
}
