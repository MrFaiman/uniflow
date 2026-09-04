package transfer

import (
	"fmt"
	"log/slog"
	"mime"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/MrFaiman/uniflow/pb"
)

// There is no ACK channel, so the Sender has no backpressure signal at all:
// it cannot discover that anything downstream is falling behind. The send
// rate must therefore be chosen to suit the *slowest* element of the path,
// not the fastest. Three unpaced Senders will outrun both the Receivers'
// decode loops and any intermediate hop, overflowing kernel UDP buffers and
// dropping far more than the FEC margin can repair — reproduced on loopback
// with zero injected loss.
//
// Defaults are deliberately conservative because the reference path includes
// a single-threaded Python router forwarding every packet of every worker.
// Tune with UNIFLOW_PACING_BATCH / UNIFLOW_PACING_DELAY_US on a faster path.
var (
	dataPacingBatch = envInt("UNIFLOW_PACING_BATCH", 16)
	dataPacingDelay = time.Duration(
		envInt("UNIFLOW_PACING_DELAY_US", 1000),
	) * time.Microsecond
)

// How often each worker repeats the object announcement while transmitting.
const fdtRepeatEveryPackets = 32

type Sender struct {
	conn      *net.UDPConn
	destAddrs []*net.UDPAddr
	dataAddr  *net.UDPAddr
	// SetTarget mutates destAddrs/dataAddr, and the IPC server handles each
	// connection on its own goroutine, so concurrent commands would otherwise
	// clobber each other's destination mid-transfer. Serializing per Sender
	// process costs nothing: one process is one worker, and the parallelism
	// that matters is across the three Sender processes.
	mu          sync.Mutex
	sessionID   uint64
	workerIndex uint32
	workerCount uint32
	destPorts   []int
}

func NewSender(destPorts []int) (*Sender, error) {
	conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		return nil, fmt.Errorf("listen udp: %w", err)
	}

	sessionID := sessionIDFromEnv()
	if sessionID == 0 {
		slog.Warn("UNIFLOW_SESSION_ID not set; transfers may not coordinate across workers")
	}

	return &Sender{
		conn:        conn,
		destPorts:   destPorts,
		sessionID:   sessionID,
		workerIndex: workerIndex(),
		workerCount: workerCount(),
	}, nil
}

func (s *Sender) Close() {
	if s.conn != nil {
		_ = s.conn.Close()
	}
}

// SetTarget resolves two destinations for this worker:
//   - destAddrs: broadcast to every receiver port. Used only for the small,
//     infrequent FileDeliveryTable so every Receiver process (which each hold
//     independent objectMeta state) learns the object's FEC parameters,
//     regardless of which worker happens to assemble the file.
//   - dataAddr: this worker's own matching port only. Used for the bulk
//     FluteDataPacket stream. Broadcasting data symbols to all receiver
//     ports (as opposed to just the owning one) would triple real network
//     and UDP-recv-buffer load for coordinated transfers with no benefit,
//     since a non-owning Receiver discards them anyway (see OwnsBlock).
func (s *Sender) SetTarget(host string, coordinated bool) error {
	host = strings.TrimSpace(host)
	if host == "" {
		return fmt.Errorf("target_ip is empty")
	}
	if int(s.workerIndex) >= len(s.destPorts) {
		return fmt.Errorf("worker index %d out of range for ports", s.workerIndex)
	}

	broadcastPorts := s.destPorts
	if !coordinated {
		broadcastPorts = []int{s.destPorts[s.workerIndex]}
	}

	addrs := make([]*net.UDPAddr, 0, len(broadcastPorts))
	for _, port := range broadcastPorts {
		addr, err := net.ResolveUDPAddr("udp", joinHostPort(host, port))
		if err != nil {
			return fmt.Errorf("resolve %s:%d: %w", host, port, err)
		}
		addrs = append(addrs, addr)
	}
	s.destAddrs = addrs

	dataAddr, err := net.ResolveUDPAddr("udp", joinHostPort(host, s.destPorts[s.workerIndex]))
	if err != nil {
		return fmt.Errorf("resolve %s:%d: %w", host, s.destPorts[s.workerIndex], err)
	}
	s.dataAddr = dataAddr
	return nil
}

func (s *Sender) sendDatagram(datagram *pb.UdpDatagram) error {
	if len(s.destAddrs) == 0 {
		return fmt.Errorf("no destination addresses configured")
	}
	payload, err := MarshalEnvelope(datagram)
	if err != nil {
		return err
	}
	for _, addr := range s.destAddrs {
		if _, err := s.conn.WriteToUDP(payload, addr); err != nil {
			return fmt.Errorf("write udp to %s: %w", addr, err)
		}
	}
	return nil
}

func (s *Sender) sendDataDatagram(datagram *pb.UdpDatagram) error {
	if s.dataAddr == nil {
		return fmt.Errorf("no data destination configured")
	}
	payload, err := MarshalEnvelope(datagram)
	if err != nil {
		return err
	}
	if _, err := s.conn.WriteToUDP(payload, s.dataAddr); err != nil {
		return fmt.Errorf("write udp to %s: %w", s.dataAddr, err)
	}
	return nil
}

func (s *Sender) sendPathOperation(
	op pb.PathOperation_Op,
	relPath string,
	destRelPath string,
	isDirectory bool,
) error {
	if _, err := NormalizeRelativePath(relPath); err != nil {
		return fmt.Errorf("invalid relative path: %w", err)
	}
	if op == pb.PathOperation_RENAME {
		if _, err := NormalizeRelativePath(destRelPath); err != nil {
			return fmt.Errorf("invalid dest relative path: %w", err)
		}
	}
	pathOp := &pb.PathOperation{
		SessionId:        s.sessionID,
		Op:               op,
		RelativePath:     relPath,
		DestRelativePath: destRelPath,
		IsDirectory:      isDirectory,
	}
	if err := s.sendDatagram(&pb.UdpDatagram{
		Payload: &pb.UdpDatagram_PathOp{PathOp: pathOp},
	}); err != nil {
		return err
	}
	slog.Info(
		"sent path operation",
		"op", op.String(),
		"path", relPath,
		"dest", destRelPath,
		"is_directory", isDirectory,
	)
	return nil
}

func (s *Sender) SendFile(absPath, relPath string, objectID uint64, coordinated bool) error {
	if objectID == 0 {
		return fmt.Errorf("object_id is required")
	}
	if relPath == "" {
		return fmt.Errorf("relative_path is required")
	}
	if _, err := NormalizeRelativePath(relPath); err != nil {
		return fmt.Errorf("invalid relative path: %w", err)
	}

	// Stream rather than load. All three Senders open the same file at the
	// same time for a coordinated transfer, so reading it whole would cost
	// three times the file size in RAM across the machine; a 1 GB transfer
	// would need ~3 GB. Each worker instead reads only the blocks it owns,
	// one MaxBlockBytes block at a time.
	file, err := os.Open(absPath)
	if err != nil {
		return fmt.Errorf("open file: %w", err)
	}
	defer func() { _ = file.Close() }()

	info, err := file.Stat()
	if err != nil {
		return fmt.Errorf("stat file: %w", err)
	}

	checksum, err := StreamChecksum(file)
	if err != nil {
		return fmt.Errorf("checksum file: %w", err)
	}

	plan := PlanFileBySize(int(info.Size()))

	fdt := &pb.FileDeliveryTable{
		SessionId:   s.sessionID,
		ObjectId:    objectID,
		FileName:    relPath,
		FileSize:    uint64(plan.OriginalLength),
		ContentType: mime.TypeByExtension(filepath.Ext(absPath)),
		Coordinated: coordinated,
		Checksum:    checksum,
		FecParams: &pb.FileDeliveryTable_RaptorQParameters{
			SymbolSize:   plan.SymbolSize,
			NumSymbols:   plan.TotalSymbols,
			SourceBlocks: plan.SourceBlocks,
		},
	}
	if fdt.ContentType == "" {
		fdt.ContentType = "application/octet-stream"
	}

	sendWorkerIndex := s.workerIndex
	sendWorkerCount := s.workerCount
	if !coordinated {
		sendWorkerIndex = 0
		sendWorkerCount = 1
	}

	if plan.OriginalLength == 0 {
		if coordinated && s.workerIndex != 0 {
			return nil
		}
		if err := s.sendDatagram(&pb.UdpDatagram{
			Payload: &pb.UdpDatagram_Fdt{Fdt: fdt},
		}); err != nil {
			return err
		}
		slog.Info(
			"sent empty file",
			"path", absPath,
			"relative_path", relPath,
			"object_id", objectID,
			"coordinated", coordinated,
		)
		return nil
	}

	// Every worker announces the object before sending any of its data, and
	// broadcasts that announcement to all Receiver ports.
	//
	// A Receiver cannot use a data packet for an object it has never heard of
	// (it has no FEC parameters or file length for it), so it discards those
	// packets — and with no ACK they are never sent again. Previously only
	// worker 0 announced, so every symbol workers 1 and 2 sent before that
	// single announcement propagated was lost outright, and if it failed to
	// reach a Receiver at all that Receiver discarded its entire share.
	// The FDT is small and idempotent, so announcing from each worker is far
	// cheaper than losing a block permanently.
	if err := s.sendDatagram(&pb.UdpDatagram{
		Payload: &pb.UdpDatagram_Fdt{Fdt: fdt},
	}); err != nil {
		return err
	}

	packetCount := 0
	// Reused across blocks so the working set stays one block, not one file.
	blockBuf := make([]byte, MaxBlockBytes)
	for blockIndex := uint32(0); blockIndex < plan.SourceBlocks; blockIndex++ {
		if !OwnsBlock(blockIndex, sendWorkerIndex, sendWorkerCount) {
			continue
		}
		blockLen := BlockByteLength(plan, blockIndex)
		if blockLen == 0 {
			continue
		}
		offset := int64(blockIndex) * int64(MaxBlockBytes)
		if _, err := file.ReadAt(blockBuf[:blockLen], offset); err != nil {
			return fmt.Errorf("read block %d: %w", blockIndex, err)
		}
		enc, baseSymbols, err := EncodeBlock(BlockPlan{
			Index:    blockIndex,
			Data:     blockBuf[:blockLen],
			SymbolsK: uint32((blockLen + SymbolSize - 1) / SymbolSize),
		})
		if err != nil {
			return err
		}
		totalSymbols := RepairSymbolCount(baseSymbols)
		for esi := uint32(0); esi < totalSymbols; esi++ {
			symbol := enc.GenSymbol(esi)
			pkt := &pb.FluteDataPacket{
				SessionId:         s.sessionID,
				ObjectId:          objectID,
				SourceBlockNumber: blockIndex,
				EncodingSymbolId:  esi,
				Payload:           symbol,
			}
			if err := s.sendDataDatagram(&pb.UdpDatagram{
				Payload: &pb.UdpDatagram_Data{Data: pkt},
			}); err != nil {
				return err
			}
			packetCount++
			if packetCount%dataPacingBatch == 0 {
				time.Sleep(dataPacingDelay)
			}
			// Repeat the announcement periodically, from every worker. The
			// FDT carries no payload data, so a lost one cannot be repaired
			// by FEC; repetition is the only way a Receiver that missed it
			// can still learn the object exists.
			if packetCount%fdtRepeatEveryPackets == 0 {
				if err := s.sendDatagram(&pb.UdpDatagram{
					Payload: &pb.UdpDatagram_Fdt{Fdt: fdt},
				}); err != nil {
					return err
				}
			}
		}
	}

	slog.Info(
		"sent file chunks",
		"path", absPath,
		"relative_path", relPath,
		"object_id", objectID,
		"worker", s.workerIndex,
		"coordinated", coordinated,
		"blocks", plan.SourceBlocks,
		"size", plan.OriginalLength,
	)
	return nil
}

type ipcCommand struct {
	command          string
	data             []byte
	objectID         uint64
	coordinated      bool
	relativePath     string
	destRelativePath string
	isDirectory      bool
}

func (s *Sender) handleIPCCommand(req ipcCommand) error {
	switch req.command {
	case "created":
		if req.isDirectory {
			return s.sendPathOperation(pb.PathOperation_MKDIR, req.relativePath, "", true)
		}
		return s.SendFile(string(req.data), req.relativePath, req.objectID, req.coordinated)
	case "modified":
		if req.isDirectory {
			return nil
		}
		return s.SendFile(string(req.data), req.relativePath, req.objectID, req.coordinated)
	case "deleted":
		return s.sendPathOperation(pb.PathOperation_REMOVE, req.relativePath, "", req.isDirectory)
	case "moved":
		if err := s.sendPathOperation(
			pb.PathOperation_RENAME,
			req.relativePath,
			req.destRelativePath,
			req.isDirectory,
		); err != nil {
			return err
		}
		if req.isDirectory {
			return nil
		}
		parts := strings.SplitN(string(req.data), "\n", 2)
		if len(parts) != 2 {
			return fmt.Errorf("moved event missing dest path")
		}
		destAbs := parts[1]
		if _, err := os.Stat(destAbs); err != nil {
			return nil
		}
		return s.SendFile(destAbs, req.destRelativePath, req.objectID, req.coordinated)
	default:
		return fmt.Errorf("unknown command %q", req.command)
	}
}
