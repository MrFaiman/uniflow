package tests

import (
	"bytes"
	"testing"
	"time"

	"github.com/MrFaiman/uniflow/internal/receiver"
	"github.com/MrFaiman/uniflow/internal/wire"
)

func TestReassemblerCompletesFrame(t *testing.T) {
	r := receiver.NewReassembler(16, time.Second)
	payload := []byte("reassembler payload")
	shards, err := wire.ShardPayload(payload, 10, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	var got []byte
	var ready bool
	for _, shard := range shards[:3] {
		var err error
		got, ready, err = r.AddAndReconstruct(shard, wire.ReconstructPayload)
		if err != nil {
			t.Fatalf("add: %v", err)
		}
	}
	if !ready {
		t.Fatal("expected frame to complete")
	}
	if string(got) != string(payload) {
		t.Fatalf("payload mismatch")
	}
}

func TestReassemblerIgnoresDuplicates(t *testing.T) {
	r := receiver.NewReassembler(16, time.Second)
	payload := bytes.Repeat([]byte("d"), 1300)
	shards, err := wire.ShardPayload(payload, 11, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	for i := 0; i < 3; i++ {
		_, ready, err := r.AddAndReconstruct(shards[i], wire.ReconstructPayload)
		if err != nil {
			t.Fatalf("add: %v", err)
		}
		if i < 2 && ready {
			t.Fatal("frame should not complete before k shards")
		}
	}

	_, ready, err := r.AddAndReconstruct(shards[0], wire.ReconstructPayload)
	if err != nil {
		t.Fatalf("duplicate add: %v", err)
	}
	if ready {
		t.Fatal("duplicate shard should not complete frame again")
	}
}

func TestReassemblerEvictsWhenFull(t *testing.T) {
	r := receiver.NewReassembler(2, time.Second)
	payload := []byte("evict")

	for frameID := uint64(1); frameID <= 3; frameID++ {
		shards, err := wire.ShardPayload(payload, frameID, 0, 600, 2)
		if err != nil {
			t.Fatalf("shard: %v", err)
		}
		_, _, err = r.AddAndReconstruct(shards[0], wire.ReconstructPayload)
		if err != nil {
			t.Fatalf("add: %v", err)
		}
	}

	if r.Inflight() > 2 {
		t.Fatalf("expected inflight <= 2, got %d", r.Inflight())
	}
}

func TestReassemblerTTLExpiry(t *testing.T) {
	r := receiver.NewReassembler(16, 20*time.Millisecond)
	payload := bytes.Repeat([]byte("t"), 1300)
	shards, err := wire.ShardPayload(payload, 20, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	_, _, err = r.AddAndReconstruct(shards[0], wire.ReconstructPayload)
	if err != nil {
		t.Fatalf("add: %v", err)
	}
	if r.Inflight() != 1 {
		t.Fatalf("expected one inflight frame")
	}

	time.Sleep(30 * time.Millisecond)

	shards2, err := wire.ShardPayload(payload, 21, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard2: %v", err)
	}
	_, _, err = r.AddAndReconstruct(shards2[0], wire.ReconstructPayload)
	if err != nil {
		t.Fatalf("add2: %v", err)
	}
	if r.Inflight() != 1 {
		t.Fatalf("expected expired frame to be evicted, inflight=%d", r.Inflight())
	}
}

func TestReassemblerSeparateFrames(t *testing.T) {
	r := receiver.NewReassembler(16, time.Second)

	p1 := []byte("frame-one")
	s1, err := wire.ShardPayload(p1, 1, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard1: %v", err)
	}
	for i := 0; i < 3; i++ {
		_, ready, err := r.AddAndReconstruct(s1[i], wire.ReconstructPayload)
		if err != nil {
			t.Fatalf("add1: %v", err)
		}
		if i == 2 && !ready {
			t.Fatal("frame one should complete")
		}
	}

	p2 := []byte("frame-two")
	s2, err := wire.ShardPayload(p2, 2, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard2: %v", err)
	}
	var got []byte
	for i := 0; i < 3; i++ {
		var err error
		got, _, err = r.AddAndReconstruct(s2[i], wire.ReconstructPayload)
		if err != nil {
			t.Fatalf("add2: %v", err)
		}
	}
	if string(got) != string(p2) {
		t.Fatalf("frame two mismatch")
	}
}
