package tests

import (
	"bytes"
	"crypto/sha256"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/pb"
	"github.com/MrFaiman/uniflow/transfer"
	"google.golang.org/protobuf/proto"
)

func TestFileChecksum(t *testing.T) {
	got := transfer.FileChecksum([]byte("uniflow roundtrip payload"))
	want := transfer.FileChecksum([]byte("uniflow roundtrip payload"))
	if !bytes.Equal(got, want) {
		t.Fatalf("checksum not stable")
	}
	if len(got) != sha256.Size {
		t.Fatalf("expected %d bytes, got %d", sha256.Size, len(got))
	}
}

func TestFileChecksumEmpty(t *testing.T) {
	got := transfer.FileChecksum(nil)
	if len(got) != sha256.Size {
		t.Fatalf("expected %d bytes, got %d", sha256.Size, len(got))
	}
}

func TestTryAssembleChecksumMismatch(t *testing.T) {
	recvDir := t.TempDir()
	recv, conn := startTestReceiver(t, recvDir, 19100)
	defer recv.Close()
	defer conn.Close()

	objectID := uint64(7)
	data := []byte("payload for checksum test")
	plan := transfer.PlanFile(data)
	fdt := &pb.FileDeliveryTable{
		ObjectId: objectID,
		FileName: "mismatch.bin",
		FileSize: uint64(len(data)),
		Checksum: transfer.FileChecksum([]byte("wrong payload")),
		FecParams: &pb.FileDeliveryTable_RaptorQParameters{
			SymbolSize:   plan.SymbolSize,
			NumSymbols:   plan.TotalSymbols,
			SourceBlocks: plan.SourceBlocks,
		},
	}
	if err := sendFDT(conn, fdt); err != nil {
		t.Fatal(err)
	}
	if err := sendBlockSymbols(conn, fdt, 0, data); err != nil {
		t.Fatal(err)
	}

	outPath := filepath.Join(recvDir, "mismatch.bin")
	waitForAbsentFile(t, outPath, 2*time.Second)
}

func TestTryAssembleEmptyFile(t *testing.T) {
	recvDir := t.TempDir()
	recv, conn := startTestReceiver(t, recvDir, 19101)
	defer recv.Close()
	defer conn.Close()

	objectID := uint64(8)
	fdt := &pb.FileDeliveryTable{
		ObjectId: objectID,
		FileName: "empty.bin",
		FileSize: 0,
		Checksum: transfer.FileChecksum(nil),
		FecParams: &pb.FileDeliveryTable_RaptorQParameters{
			SymbolSize:   transfer.SymbolSize,
			NumSymbols:   1,
			SourceBlocks: 1,
		},
	}
	if err := sendFDT(conn, fdt); err != nil {
		t.Fatal(err)
	}

	waitForFile(t, filepath.Join(recvDir, "empty.bin"), nil)
}

func TestTryAssembleMissingChecksum(t *testing.T) {
	recvDir := t.TempDir()
	recv, conn := startTestReceiver(t, recvDir, 19102)
	defer recv.Close()
	defer conn.Close()

	objectID := uint64(9)
	data := []byte("no checksum")
	plan := transfer.PlanFile(data)
	fdt := &pb.FileDeliveryTable{
		ObjectId: objectID,
		FileName: "missing.bin",
		FileSize: uint64(len(data)),
		FecParams: &pb.FileDeliveryTable_RaptorQParameters{
			SymbolSize:   plan.SymbolSize,
			NumSymbols:   plan.TotalSymbols,
			SourceBlocks: plan.SourceBlocks,
		},
	}
	if err := sendFDT(conn, fdt); err != nil {
		t.Fatal(err)
	}
	if err := sendBlockSymbols(conn, fdt, 0, data); err != nil {
		t.Fatal(err)
	}

	outPath := filepath.Join(recvDir, "missing.bin")
	waitForAbsentFile(t, outPath, 2*time.Second)
}

func startTestReceiver(t *testing.T, recvDir string, port int) (*transfer.Receiver, *net.UDPConn) {
	t.Helper()

	t.Setenv("UNIFLOW_WORKER_COUNT", "1")
	t.Setenv("UNIFLOW_WORKER_INDEX", "0")

	recv, err := transfer.NewReceiver(port, recvDir)
	if err != nil {
		t.Fatal(err)
	}
	go func() {
		_ = recv.Run()
	}()

	addr := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: port}

	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		t.Fatal(err)
	}

	return recv, conn
}

func sendFDT(conn *net.UDPConn, fdt *pb.FileDeliveryTable) error {
	datagram := &pb.UdpDatagram{
		Payload: &pb.UdpDatagram_Fdt{Fdt: fdt},
	}
	payload, err := proto.Marshal(datagram)
	if err != nil {
		return err
	}
	_, err = conn.Write(payload)
	return err
}

func sendBlockSymbols(
	conn *net.UDPConn,
	fdt *pb.FileDeliveryTable,
	blockIndex uint32,
	data []byte,
) error {
	block := transfer.BlockPlan{Index: blockIndex, Data: data, SymbolsK: 1}
	enc, baseSymbols, err := transfer.EncodeBlock(block)
	if err != nil {
		return err
	}
	total := transfer.RepairSymbolCount(baseSymbols)
	for esi := uint32(0); esi < total; esi++ {
		pkt := &pb.FluteDataPacket{
			ObjectId:          fdt.ObjectId,
			SourceBlockNumber: blockIndex,
			EncodingSymbolId:  esi,
			Payload:           enc.GenSymbol(esi),
		}
		datagram := &pb.UdpDatagram{
			Payload: &pb.UdpDatagram_Data{Data: pkt},
		}
		payload, err := proto.Marshal(datagram)
		if err != nil {
			return err
		}
		if _, err := conn.Write(payload); err != nil {
			return err
		}
	}
	return nil
}

func waitForAbsentFile(t *testing.T, path string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			t.Fatalf("expected file %s to be absent", path)
		}
		time.Sleep(50 * time.Millisecond)
	}
}
