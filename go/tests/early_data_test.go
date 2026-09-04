package tests

import (
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/pb"
	"github.com/MrFaiman/uniflow/transfer"
)

// A Receiver cannot decode a symbol for an object it has not been told about,
// and with no ACK channel that symbol is never retransmitted. Sending the
// data ahead of the announcement must therefore still reconstruct the file:
// the symbols have to be held and replayed once the FDT arrives, not dropped.
//
// This reproduces the failure that made large coordinated transfers stall:
// the announcement reached the Receivers hundreds of milliseconds after the
// other workers had already started transmitting.
func TestDataArrivingBeforeFDTIsNotLost(t *testing.T) {
	recvDir := t.TempDir()
	const port = 19100

	t.Setenv("UNIFLOW_WORKER_COUNT", "1")
	t.Setenv("UNIFLOW_WORKER_INDEX", "0")
	t.Setenv("UNIFLOW_SESSION_ID", "5150")

	recv, err := transfer.NewReceiver(port, recvDir)
	if err != nil {
		t.Fatal(err)
	}
	defer recv.Close()
	go func() { _ = recv.Run() }()

	content := []byte("symbols that arrive before the announcement")
	plan := transfer.PlanFile(content)
	block := plan.Blocks[0]
	enc, base, err := transfer.EncodeBlock(block)
	if err != nil {
		t.Fatal(err)
	}

	conn, err := net.Dial("udp", net.JoinHostPort("127.0.0.1", "19100"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()

	send := func(datagram *pb.UdpDatagram) {
		payload, err := transfer.MarshalEnvelope(datagram)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := conn.Write(payload); err != nil {
			t.Fatal(err)
		}
	}

	// Every data symbol first, with no announcement at all.
	for esi := uint32(0); esi < transfer.RepairSymbolCount(base); esi++ {
		send(&pb.UdpDatagram{
			Payload: &pb.UdpDatagram_Data{Data: &pb.FluteDataPacket{
				SessionId:         5150,
				ObjectId:          77,
				SourceBlockNumber: block.Index,
				EncodingSymbolId:  esi,
				Payload:           enc.GenSymbol(esi),
			}},
		})
	}

	// Give the Receiver time to process them before the FDT shows up, so the
	// test genuinely exercises the out-of-order path.
	time.Sleep(200 * time.Millisecond)

	send(&pb.UdpDatagram{
		Payload: &pb.UdpDatagram_Fdt{Fdt: &pb.FileDeliveryTable{
			SessionId:   5150,
			ObjectId:    77,
			FileName:    "late-fdt.bin",
			FileSize:    uint64(len(content)),
			ContentType: "application/octet-stream",
			Checksum:    transfer.FileChecksum(content),
			FecParams: &pb.FileDeliveryTable_RaptorQParameters{
				SymbolSize:   plan.SymbolSize,
				NumSymbols:   plan.TotalSymbols,
				SourceBlocks: plan.SourceBlocks,
			},
		}},
	})

	waitForFile(t, filepath.Join(recvDir, "late-fdt.bin"), content)
}

// Symbols held for an object that is never announced must not accumulate
// without bound, or a stream of unknown object IDs would exhaust memory.
func TestPendingSymbolsAreBounded(t *testing.T) {
	recvDir := t.TempDir()
	const port = 19101

	t.Setenv("UNIFLOW_WORKER_COUNT", "1")
	t.Setenv("UNIFLOW_WORKER_INDEX", "0")

	recv, err := transfer.NewReceiver(port, recvDir)
	if err != nil {
		t.Fatal(err)
	}
	defer recv.Close()
	go func() { _ = recv.Run() }()

	conn, err := net.Dial("udp", net.JoinHostPort("127.0.0.1", "19101"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()

	payload := make([]byte, 512)
	for i := 0; i < 6000; i++ {
		datagram := &pb.UdpDatagram{
			Payload: &pb.UdpDatagram_Data{Data: &pb.FluteDataPacket{
				ObjectId:         999,
				EncodingSymbolId: uint32(i),
				Payload:          payload,
			}},
		}
		raw, err := transfer.MarshalEnvelope(datagram)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := conn.Write(raw); err != nil {
			t.Fatal(err)
		}
	}

	// Nothing should have been written for an object that was never
	// announced, and the process must still be healthy.
	time.Sleep(300 * time.Millisecond)
	entries, err := os.ReadDir(recvDir)
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		if entry.Name() != ".uniflow" {
			t.Fatalf("unexpected output %q for unannounced object", entry.Name())
		}
	}
}

// The announcement is the one packet FEC cannot protect: repair symbols
// rebuild data blocks, but nothing rebuilds a lost FDT, and without it every
// symbol for the object is unusable. Small files transmit too few packets to
// reach the periodic repeat, so a single corrupted announcement used to lose
// the whole file — seen as a 1-byte file vanishing under bit-flip injection.
// It must therefore be transmitted redundantly.
func TestSmallFileAnnouncedRedundantly(t *testing.T) {
	const port = 19102

	t.Setenv("UNIFLOW_WORKER_COUNT", "1")
	t.Setenv("UNIFLOW_WORKER_INDEX", "0")
	t.Setenv("UNIFLOW_SESSION_ID", "8080")

	conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: port})
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()

	fdtSeen := make(chan struct{}, 64)
	go func() {
		buf := make([]byte, 65535)
		for {
			n, _, err := conn.ReadFromUDP(buf)
			if err != nil {
				return
			}
			datagram, err := transfer.UnmarshalEnvelope(buf[:n])
			if err != nil {
				continue
			}
			if datagram.GetFdt() != nil {
				select {
				case fdtSeen <- struct{}{}:
				default:
				}
			}
		}
	}()

	sender, err := transfer.NewSender([]int{port})
	if err != nil {
		t.Fatal(err)
	}
	defer sender.Close()
	if err := sender.SetTarget("127.0.0.1", false); err != nil {
		t.Fatal(err)
	}

	tmp := filepath.Join(t.TempDir(), "one-byte.bin")
	if err := os.WriteFile(tmp, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := sender.SendFile(tmp, "one-byte.bin", 1, false); err != nil {
		t.Fatal(err)
	}

	time.Sleep(300 * time.Millisecond)
	if len(fdtSeen) < 3 {
		t.Fatalf(
			"a 1-byte file produced only %d announcements; "+
				"one lost packet would lose the file",
			len(fdtSeen),
		)
	}
}
