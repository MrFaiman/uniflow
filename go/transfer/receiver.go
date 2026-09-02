package transfer

import (
	"encoding/hex"
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"

	"github.com/MrFaiman/uniflow/pb"
	"google.golang.org/protobuf/proto"
)

type blockState struct {
	symbols map[uint32][]byte
}

type Receiver struct {
	conn        *net.UDPConn
	receiveDir  string
	workerIndex uint32
	workerCount uint32
	objectMeta  map[uint64]*pb.FileDeliveryTable
	blocks      map[uint64]map[uint32]*blockState
	assembled   map[uint64]bool
}

func NewReceiver(port int, receiveDir string) (*Receiver, error) {
	if err := os.MkdirAll(receiveDir, 0o755); err != nil {
		return nil, fmt.Errorf("mkdir receive dir: %w", err)
	}
	addr := &net.UDPAddr{IP: net.IPv4zero, Port: port}
	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return nil, fmt.Errorf("listen udp %d: %w", port, err)
	}
	return &Receiver{
		conn:        conn,
		receiveDir:  receiveDir,
		workerIndex: workerIndex(),
		workerCount: workerCount(),
		objectMeta:  make(map[uint64]*pb.FileDeliveryTable),
		blocks:      make(map[uint64]map[uint32]*blockState),
		assembled:   make(map[uint64]bool),
	}, nil
}

func (r *Receiver) Close() {
	if r.conn != nil {
		_ = r.conn.Close()
	}
}

func (r *Receiver) Run() error {
	buf := make([]byte, 65535)
	for {
		n, _, err := r.conn.ReadFromUDP(buf)
		if err != nil {
			return fmt.Errorf("read udp: %w", err)
		}
		var datagram pb.UdpDatagram
		if err := proto.Unmarshal(buf[:n], &datagram); err != nil {
			slog.Warn("bad datagram", "err", err)
			continue
		}
		switch payload := datagram.Payload.(type) {
		case *pb.UdpDatagram_Fdt:
			r.handleFDT(payload.Fdt)
		case *pb.UdpDatagram_Data:
			r.handleData(payload.Data)
		case *pb.UdpDatagram_PathOp:
			r.handlePathOperation(payload.PathOp)
		}
	}
}

func (r *Receiver) shouldApplyPathOps() bool {
	if r.workerCount <= 1 {
		return true
	}
	return r.workerIndex == 0
}

func (r *Receiver) handlePathOperation(op *pb.PathOperation) {
	if op == nil || !r.shouldApplyPathOps() {
		return
	}

	target, err := SafeJoin(r.receiveDir, op.RelativePath)
	if err != nil {
		slog.Error("invalid path operation", "op", op.Op.String(), "path", op.RelativePath, "err", err)
		return
	}

	switch op.Op {
	case pb.PathOperation_MKDIR:
		if err := os.MkdirAll(target, 0o755); err != nil {
			slog.Error("mkdir failed", "path", target, "err", err)
			return
		}
		slog.Info("mkdir", "path", target)
	case pb.PathOperation_REMOVE:
		if op.IsDirectory {
			if err := os.RemoveAll(target); err != nil && !os.IsNotExist(err) {
				slog.Error("remove dir failed", "path", target, "err", err)
				return
			}
		} else if err := os.Remove(target); err != nil && !os.IsNotExist(err) {
			slog.Error("remove file failed", "path", target, "err", err)
			return
		}
		slog.Info("removed", "path", target, "is_directory", op.IsDirectory)
	case pb.PathOperation_RENAME:
		dest, err := SafeJoin(r.receiveDir, op.DestRelativePath)
		if err != nil {
			slog.Error("invalid rename dest", "dest", op.DestRelativePath, "err", err)
			return
		}
		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
			slog.Error("rename mkdir failed", "path", filepath.Dir(dest), "err", err)
			return
		}
		if err := os.Rename(target, dest); err != nil {
			slog.Error("rename failed", "from", target, "to", dest, "err", err)
			return
		}
		slog.Info("renamed", "from", target, "to", dest, "is_directory", op.IsDirectory)
	default:
		slog.Warn("unknown path operation", "op", op.Op.String())
	}
}

func (r *Receiver) stagingDir(objectID uint64) string {
	return filepath.Join(r.receiveDir, ".uniflow", "staging", fmt.Sprintf("%d", objectID))
}

func (r *Receiver) blockStagingPath(objectID uint64, blockIndex uint32) string {
	return filepath.Join(
		r.stagingDir(objectID),
		fmt.Sprintf("block_%d", blockIndex),
	)
}

func (r *Receiver) handleFDT(fdt *pb.FileDeliveryTable) {
	if fdt == nil || fdt.FecParams == nil {
		return
	}
	r.objectMeta[fdt.ObjectId] = fdt
	slog.Info(
		"fdt",
		"session", fdt.SessionId,
		"object", fdt.ObjectId,
		"file", fdt.FileName,
		"size", fdt.FileSize,
	)
	if fdt.FileSize == 0 {
		r.tryAssemble(fdt.ObjectId, fdt.GetCoordinated())
	}
}

func (r *Receiver) shouldHandleBlock(
	blockIndex uint32,
	coordinated bool,
) bool {
	if !coordinated {
		return true
	}
	return OwnsBlock(blockIndex, r.workerIndex, r.workerCount)
}

func (r *Receiver) shouldAssemble(coordinated bool) bool {
	if !coordinated {
		return true
	}
	return r.workerIndex == 0
}

func (r *Receiver) blockStateFor(objectID uint64, blockIndex uint32) *blockState {
	byObject, ok := r.blocks[objectID]
	if !ok {
		byObject = make(map[uint32]*blockState)
		r.blocks[objectID] = byObject
	}
	block, ok := byObject[blockIndex]
	if !ok {
		block = &blockState{symbols: make(map[uint32][]byte)}
		byObject[blockIndex] = block
	}
	return block
}

func (r *Receiver) handleData(pkt *pb.FluteDataPacket) {
	if pkt == nil {
		return
	}
	fdt := r.objectMeta[pkt.ObjectId]
	if fdt == nil {
		return
	}
	if !r.shouldHandleBlock(pkt.SourceBlockNumber, fdt.GetCoordinated()) {
		return
	}

	block := r.blockStateFor(pkt.ObjectId, pkt.SourceBlockNumber)
	block.symbols[pkt.EncodingSymbolId] = pkt.Payload

	plan := FilePlan{
		SourceBlocks:   fdt.FecParams.GetSourceBlocks(),
		SymbolSize:     fdt.FecParams.GetSymbolSize(),
		OriginalLength: int(fdt.FileSize),
	}
	blockLen := BlockByteLength(plan, pkt.SourceBlockNumber)
	result, err := DecodeBlock(blockLen, block.symbols)
	if err != nil {
		return
	}

	stagingPath := r.blockStagingPath(pkt.ObjectId, pkt.SourceBlockNumber)
	if err := os.MkdirAll(filepath.Dir(stagingPath), 0o755); err != nil {
		slog.Error("staging mkdir failed", "err", err)
		return
	}
	if err := os.WriteFile(stagingPath, result, 0o644); err != nil {
		slog.Error("staging write failed", "path", stagingPath, "err", err)
		return
	}

	slog.Info(
		"block staged",
		"object", pkt.ObjectId,
		"block", pkt.SourceBlockNumber,
		"worker", r.workerIndex,
	)

	if r.shouldAssemble(fdt.GetCoordinated()) {
		r.tryAssemble(pkt.ObjectId, fdt.GetCoordinated())
	}
}

func (r *Receiver) tryAssemble(objectID uint64, coordinated bool) {
	if !r.shouldAssemble(coordinated) || r.assembled[objectID] {
		return
	}
	fdt := r.objectMeta[objectID]
	if fdt == nil || fdt.FecParams == nil {
		return
	}

	sourceBlocks := fdt.FecParams.GetSourceBlocks()
	if sourceBlocks == 0 {
		sourceBlocks = 1
	}

	plan := FilePlan{
		SourceBlocks:   sourceBlocks,
		SymbolSize:     fdt.FecParams.GetSymbolSize(),
		OriginalLength: int(fdt.FileSize),
	}

	var full []byte
	staging := r.stagingDir(objectID)

	if plan.OriginalLength == 0 {
		full = []byte{}
	} else {
		for i := uint32(0); i < sourceBlocks; i++ {
			path := r.blockStagingPath(objectID, i)
			if _, err := os.Stat(path); err != nil {
				return
			}
		}

		parts := make([][]byte, 0, sourceBlocks)
		for i := uint32(0); i < sourceBlocks; i++ {
			path := r.blockStagingPath(objectID, i)
			data, err := os.ReadFile(path)
			if err != nil {
				slog.Error("read staging block failed", "path", path, "err", err)
				return
			}
			want := BlockByteLength(plan, i)
			if len(data) > want {
				data = data[:want]
			}
			parts = append(parts, data)
		}

		full = make([]byte, 0, plan.OriginalLength)
		for _, part := range parts {
			full = append(full, part...)
		}
		if len(full) > plan.OriginalLength {
			full = full[:plan.OriginalLength]
		}
	}

	if len(fdt.Checksum) != sha256Size {
		slog.Error(
			"checksum missing or invalid",
			"object", objectID,
			"file", fdt.FileName,
			"checksum_len", len(fdt.Checksum),
		)
		r.assembled[objectID] = true
		return
	}
	if !checksumMatches(full, fdt.Checksum) {
		slog.Error(
			"checksum mismatch",
			"object", objectID,
			"file", fdt.FileName,
			"expected", hex.EncodeToString(fdt.Checksum),
			"got", hex.EncodeToString(FileChecksum(full)),
		)
		r.assembled[objectID] = true
		return
	}

	outPath, err := SafeJoin(r.receiveDir, fdt.FileName)
	if err != nil {
		slog.Error("invalid output path", "file", fdt.FileName, "err", err)
		r.assembled[objectID] = true
		return
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		slog.Error("mkdir failed", "path", filepath.Dir(outPath), "err", err)
		return
	}
	if err := os.WriteFile(outPath, full, 0o644); err != nil {
		slog.Error("write file failed", "path", outPath, "err", err)
		return
	}
	r.assembled[objectID] = true
	if plan.OriginalLength > 0 {
		if err := os.RemoveAll(staging); err != nil {
			slog.Warn("staging cleanup failed", "path", staging, "err", err)
		}
	}
	delete(r.objectMeta, objectID)
	delete(r.blocks, objectID)

	slog.Info(
		"file assembled",
		"path", outPath,
		"object", objectID,
		"size", len(full),
	)
}
