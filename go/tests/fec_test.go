package tests

import (
	"testing"

	"github.com/MrFaiman/uniflow/transfer"
)

func TestPlanFilePartitions(t *testing.T) {
	data := make([]byte, transfer.SymbolSize*transfer.MaxSymbolsPerBlock+100)
	plan := transfer.PlanFile(data)
	if plan.SourceBlocks != 2 {
		t.Fatalf("expected 2 blocks, got %d", plan.SourceBlocks)
	}
	if plan.TotalSymbols != transfer.MaxSymbolsPerBlock+1 {
		t.Fatalf("unexpected total symbols %d", plan.TotalSymbols)
	}
}

func TestEncodeDecodeBlockWithLoss(t *testing.T) {
	data := []byte("hello flute fec test payload")
	block := transfer.BlockPlan{Index: 0, Data: data, SymbolsK: 1}
	enc, base, err := transfer.EncodeBlock(block)
	if err != nil {
		t.Fatal(err)
	}
	total := transfer.RepairSymbolCount(base)
	symbols := make(map[uint32][]byte)
	for esi := uint32(0); esi < total; esi++ {
		if esi == 1 && total > 2 {
			continue
		}
		symbols[esi] = enc.GenSymbol(esi)
	}
	got, err := transfer.DecodeBlock(len(data), symbols)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(data) {
		t.Fatalf("got %q want %q", got, data)
	}
}

func TestDecodeBlockEmpty(t *testing.T) {
	block := transfer.BlockPlan{Index: 0, Data: []byte{}, SymbolsK: 1}
	enc, base, err := transfer.EncodeBlock(block)
	if err != nil {
		t.Fatal(err)
	}
	symbols := map[uint32][]byte{0: enc.GenSymbol(0)}
	if base != 0 {
		t.Fatalf("expected base 0 for empty block, got %d", base)
	}
	got, err := transfer.DecodeBlock(0, symbols)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty block, got len %d", len(got))
	}
}
