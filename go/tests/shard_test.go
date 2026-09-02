package tests

import (
	"bytes"
	"testing"

	"github.com/MrFaiman/uniflow/internal/wire"
	"github.com/MrFaiman/uniflow/pb"
)

func TestShardRoundTrip(t *testing.T) {
	payload := bytes.Repeat([]byte("x"), 1626)
	shards, err := wire.ShardPayload(payload, 42, 1, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}
	if len(shards) != 5 {
		t.Fatalf("expected 5 shards, got %d", len(shards))
	}

	got, err := wire.ReconstructPayload(shards)
	if err != nil {
		t.Fatalf("reconstruct: %v", err)
	}
	if !bytes.Equal(payload, got) {
		t.Fatalf("payload mismatch")
	}
}

func TestShardChecksumDetectsFlip(t *testing.T) {
	payload := []byte("checksum test payload")
	shards, err := wire.ShardPayload(payload, 7, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	shards[0].Shard[0] ^= 0xff
	ok, err := wire.VerifyShardChecksum(shards[0])
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if ok {
		t.Fatal("expected checksum failure after flip")
	}
}

func TestShardChecksumDetectsMetadataFlip(t *testing.T) {
	payload := []byte("metadata flip")
	shards, err := wire.ShardPayload(payload, 8, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	shards[0].ShardIndex++
	ok, err := wire.VerifyShardChecksum(shards[0])
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if ok {
		t.Fatal("expected checksum failure after metadata flip")
	}
}

func TestReconstructWithErasedParity(t *testing.T) {
	payload := bytes.Repeat([]byte("a"), 1300)
	shards, err := wire.ShardPayload(payload, 99, 2, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	selected := []*pb.WireShard{shards[0], shards[1], shards[2]}
	got, err := wire.ReconstructPayload(selected)
	if err != nil {
		t.Fatalf("reconstruct: %v", err)
	}
	if !bytes.Equal(payload, got) {
		t.Fatalf("payload mismatch")
	}
}

func TestReconstructWithOneDataShardMissing(t *testing.T) {
	payload := bytes.Repeat([]byte("b"), 1300)
	shards, err := wire.ShardPayload(payload, 100, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	selected := []*pb.WireShard{shards[0], shards[1], shards[4]}
	got, err := wire.ReconstructPayload(selected)
	if err != nil {
		t.Fatalf("reconstruct: %v", err)
	}
	if !bytes.Equal(payload, got) {
		t.Fatalf("payload mismatch")
	}
}

func TestMarshalUnmarshalShard(t *testing.T) {
	payload := []byte("wire marshal")
	shards, err := wire.ShardPayload(payload, 1, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}

	data, err := wire.MarshalShard(shards[0])
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	got, err := wire.UnmarshalShard(data)
	if err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	ok, err := wire.VerifyShardChecksum(got)
	if err != nil || !ok {
		t.Fatalf("checksum failed after marshal cycle")
	}
}

func TestReconstructTooFewShards(t *testing.T) {
	payload := bytes.Repeat([]byte("c"), 1300)
	shards, err := wire.ShardPayload(payload, 2, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}
	_, err = wire.ReconstructPayload([]*pb.WireShard{shards[0], shards[1]})
	if err == nil {
		t.Fatal("expected error with too few shards")
	}
}

func TestShardPayloadEmpty(t *testing.T) {
	shards, err := wire.ShardPayload([]byte{}, 1, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard empty: %v", err)
	}
	got, err := wire.ReconstructPayload(shards)
	if err != nil {
		t.Fatalf("reconstruct: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty payload")
	}
}

func TestWireShardSizeUnderMTU(t *testing.T) {
	payload := bytes.Repeat([]byte{0}, 1626)
	shards, err := wire.ShardPayload(payload, 1, 0, 600, 2)
	if err != nil {
		t.Fatalf("shard: %v", err)
	}
	for i, shard := range shards {
		data, err := wire.MarshalShard(shard)
		if err != nil {
			t.Fatalf("marshal shard %d: %v", i, err)
		}
		if len(data) > 1500 {
			t.Fatalf("shard %d datagram too large: %d", i, len(data))
		}
	}
}
