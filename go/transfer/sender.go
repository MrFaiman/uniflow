package transfer

import (
	"fmt"
	"log/slog"
	"mime"
	"net"
	"os"
	"path/filepath"
	"strings"

	"github.com/MrFaiman/uniflow/pb"
	"google.golang.org/protobuf/proto"
)

type Sender struct {
	conn        *net.UDPConn
	destAddrs   []*net.UDPAddr
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

func (s *Sender) SetTarget(host string, coordinated bool) error {
	host = strings.TrimSpace(host)
	if host == "" {
		return fmt.Errorf("target_ip is empty")
	}

	ports := s.destPorts
	if !coordinated {
		if int(s.workerIndex) >= len(s.destPorts) {
			return fmt.Errorf("worker index %d out of range for ports", s.workerIndex)
		}
		ports = []int{s.destPorts[s.workerIndex]}
	}

	addrs := make([]*net.UDPAddr, 0, len(ports))
	for _, port := range ports {
		addr, err := net.ResolveUDPAddr("udp", joinHostPort(host, port))
		if err != nil {
			return fmt.Errorf("resolve %s:%d: %w", host, port, err)
		}
		addrs = append(addrs, addr)
	}
	s.destAddrs = addrs
	return nil
}

func (s *Sender) sendDatagram(datagram *pb.UdpDatagram) error {
	if len(s.destAddrs) == 0 {
		return fmt.Errorf("no destination addresses configured")
	}
	payload, err := proto.Marshal(datagram)
	if err != nil {
		return fmt.Errorf("marshal datagram: %w", err)
	}
	for _, addr := range s.destAddrs {
		if _, err := s.conn.WriteToUDP(payload, addr); err != nil {
			return fmt.Errorf("write udp to %s: %w", addr, err)
		}
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

	data, err := os.ReadFile(absPath)
	if err != nil {
		return fmt.Errorf("read file: %w", err)
	}

	plan := PlanFile(data)
	checksum := FileChecksum(data)

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

	if coordinated && s.workerIndex != 0 {
		// non-leader workers skip FDT in coordinated mode
	} else {
		if err := s.sendDatagram(&pb.UdpDatagram{
			Payload: &pb.UdpDatagram_Fdt{Fdt: fdt},
		}); err != nil {
			return err
		}
	}

	packetCount := 0
	for _, block := range plan.Blocks {
		if !OwnsBlock(block.Index, sendWorkerIndex, sendWorkerCount) {
			continue
		}
		enc, baseSymbols, err := EncodeBlock(block)
		if err != nil {
			return err
		}
		totalSymbols := RepairSymbolCount(baseSymbols)
		for esi := uint32(0); esi < totalSymbols; esi++ {
			symbol := enc.GenSymbol(esi)
			pkt := &pb.FluteDataPacket{
				SessionId:         s.sessionID,
				ObjectId:          objectID,
				SourceBlockNumber: block.Index,
				EncodingSymbolId:  esi,
				Payload:           symbol,
			}
			if err := s.sendDatagram(&pb.UdpDatagram{
				Payload: &pb.UdpDatagram_Data{Data: pkt},
			}); err != nil {
				return err
			}
			packetCount++
			if coordinated && packetCount%32 == 0 && s.workerIndex == 0 {
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
