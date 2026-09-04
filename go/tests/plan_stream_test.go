package tests

import (
	"bytes"
	"crypto/sha256"
	"math/rand"
	"os"
	"path/filepath"
	"testing"

	"github.com/MrFaiman/uniflow/transfer"
)

// The Sender derives its layout from the file's size alone so it never has to
// hold a whole file in memory. That layout must stay identical to the
// in-memory one, or blocks would be cut at different offsets and the
// reassembled file would be corrupt.
func TestPlanFileBySizeMatchesPlanFile(t *testing.T) {
	sizes := []int{
		0,
		1,
		transfer.SymbolSize - 1,
		transfer.SymbolSize,
		transfer.MaxBlockBytes - 1,
		transfer.MaxBlockBytes,
		transfer.MaxBlockBytes + 1,
		3*transfer.MaxBlockBytes + 12345,
	}
	for _, size := range sizes {
		data := make([]byte, size)
		want := transfer.PlanFile(data)
		got := transfer.PlanFileBySize(size)

		if got.SourceBlocks != want.SourceBlocks {
			t.Fatalf("size %d: source blocks %d != %d",
				size, got.SourceBlocks, want.SourceBlocks)
		}
		if got.TotalSymbols != want.TotalSymbols {
			t.Fatalf("size %d: total symbols %d != %d",
				size, got.TotalSymbols, want.TotalSymbols)
		}
		if got.SymbolSize != want.SymbolSize {
			t.Fatalf("size %d: symbol size %d != %d",
				size, got.SymbolSize, want.SymbolSize)
		}
		if got.OriginalLength != want.OriginalLength {
			t.Fatalf("size %d: original length %d != %d",
				size, got.OriginalLength, want.OriginalLength)
		}
		for i := uint32(0); i < want.SourceBlocks; i++ {
			if transfer.BlockByteLength(got, i) != transfer.BlockByteLength(want, i) {
				t.Fatalf("size %d: block %d length differs", size, i)
			}
		}
	}
}

// Reading each block by offset must reproduce exactly the bytes the in-memory
// planner would have handed to the encoder.
func TestStreamedBlocksMatchInMemoryBlocks(t *testing.T) {
	rng := rand.New(rand.NewSource(1))
	data := make([]byte, 3*transfer.MaxBlockBytes+9999)
	rng.Read(data)

	path := filepath.Join(t.TempDir(), "payload.bin")
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = file.Close() }()

	want := transfer.PlanFile(data)
	got := transfer.PlanFileBySize(len(data))
	buf := make([]byte, transfer.MaxBlockBytes)

	for i := uint32(0); i < got.SourceBlocks; i++ {
		blockLen := transfer.BlockByteLength(got, i)
		offset := int64(i) * int64(transfer.MaxBlockBytes)
		if _, err := file.ReadAt(buf[:blockLen], offset); err != nil {
			t.Fatalf("block %d: %v", i, err)
		}
		if !bytes.Equal(buf[:blockLen], want.Blocks[i].Data) {
			t.Fatalf("block %d bytes differ from in-memory plan", i)
		}
	}
}

func TestStreamChecksumMatchesWholeFileChecksum(t *testing.T) {
	rng := rand.New(rand.NewSource(2))
	data := make([]byte, transfer.MaxBlockBytes+4321)
	rng.Read(data)

	path := filepath.Join(t.TempDir(), "payload.bin")
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = file.Close() }()

	got, err := transfer.StreamChecksum(file)
	if err != nil {
		t.Fatal(err)
	}
	want := sha256.Sum256(data)
	if !bytes.Equal(got, want[:]) {
		t.Fatalf("stream checksum %x != %x", got, want)
	}

	// StreamChecksum must rewind, or the first block read would start at EOF.
	head := make([]byte, 16)
	if _, err := file.Read(head); err != nil {
		t.Fatalf("file not rewound: %v", err)
	}
	if !bytes.Equal(head, data[:16]) {
		t.Fatal("file not rewound to start")
	}
}

// A block must carry enough repair symbols to survive the loss the router is
// specified to inject; too thin a margin makes large transfers intermittent.
func TestRepairMarginSurvivesSpecifiedLoss(t *testing.T) {
	const sourceSymbols = 1000
	total := transfer.RepairSymbolCount(sourceSymbols)
	margin := float64(total-sourceSymbols) / float64(sourceSymbols)
	if margin < 0.10 {
		t.Fatalf("repair margin %.1f%% too thin for ~9%% combined loss",
			margin*100)
	}
	if transfer.RepairSymbolCount(1) <= 1 {
		t.Fatal("a single-symbol block must still get a repair symbol")
	}
}
