package wire

import (
	"bytes"
	"fmt"
	"hash/crc32"

	"github.com/klauspost/reedsolomon"
	"google.golang.org/protobuf/proto"

	"github.com/MrFaiman/uniflow/pb"
)

var crcTable = crc32.MakeTable(crc32.Castagnoli)

func ShardPayload(payload []byte, frameID uint64, workerIndex uint32, shardSize, parityShards int) ([]*pb.WireShard, error) {
	if shardSize <= 0 {
		return nil, fmt.Errorf("shard size must be positive")
	}
	if parityShards < 0 {
		return nil, fmt.Errorf("parity shards must be non-negative")
	}

	dataShards := (len(payload) + shardSize - 1) / shardSize
	if dataShards == 0 {
		dataShards = 1
	}

	enc, err := reedsolomon.New(dataShards, parityShards)
	if err != nil {
		return nil, fmt.Errorf("create encoder: %w", err)
	}

	padded := make([]byte, dataShards*shardSize)
	copy(padded, payload)

	shards, err := enc.Split(padded)
	if err != nil {
		return nil, fmt.Errorf("split payload: %w", err)
	}
	if err := enc.Encode(shards); err != nil {
		return nil, fmt.Errorf("encode parity: %w", err)
	}

	total := dataShards + parityShards
	out := make([]*pb.WireShard, total)
	for i := 0; i < total; i++ {
		shard := &pb.WireShard{
			FrameId:      frameID,
			WorkerIndex:  workerIndex,
			ShardIndex:   uint32(i),
			DataShards:   uint32(dataShards),
			ParityShards: uint32(parityShards),
			PayloadSize:  uint32(len(payload)),
			Shard:        shards[i],
		}
		checksum, err := ShardChecksum(shard)
		if err != nil {
			return nil, err
		}
		shard.Checksum = checksum
		out[i] = shard
	}

	return out, nil
}

func ReconstructPayload(shards []*pb.WireShard) ([]byte, error) {
	if len(shards) == 0 {
		return nil, fmt.Errorf("no shards")
	}

	first := shards[0]
	dataShards := int(first.DataShards)
	parityShards := int(first.ParityShards)
	total := dataShards + parityShards
	payloadSize := int(first.PayloadSize)
	shardSize := len(first.Shard)
	if shardSize == 0 {
		return nil, fmt.Errorf("empty shard payload")
	}

	enc, err := reedsolomon.New(dataShards, parityShards)
	if err != nil {
		return nil, fmt.Errorf("create decoder: %w", err)
	}

	all := make([][]byte, total)
	present := make([]bool, total)
	for _, shard := range shards {
		idx := int(shard.ShardIndex)
		if idx < 0 || idx >= total {
			return nil, fmt.Errorf("invalid shard index: %d", idx)
		}
		if len(shard.Shard) != shardSize {
			return nil, fmt.Errorf("inconsistent shard size")
		}
		all[idx] = append([]byte(nil), shard.Shard...)
		present[idx] = true
	}

	if err := enc.Reconstruct(all); err != nil {
		return nil, fmt.Errorf("reconstruct shards: %w", err)
	}

	var joined bytes.Buffer
	if err := enc.Join(&joined, all, payloadSize); err != nil {
		return nil, fmt.Errorf("join shards: %w", err)
	}
	return joined.Bytes(), nil
}

func ShardChecksum(shard *pb.WireShard) (uint32, error) {
	copy := proto.Clone(shard).(*pb.WireShard)
	copy.Checksum = 0
	data, err := proto.MarshalOptions{Deterministic: true}.Marshal(copy)
	if err != nil {
		return 0, err
	}
	return crc32.Checksum(data, crcTable), nil
}

func VerifyShardChecksum(shard *pb.WireShard) (bool, error) {
	expected, err := ShardChecksum(shard)
	if err != nil {
		return false, err
	}
	return shard.Checksum == expected, nil
}

func MarshalShard(shard *pb.WireShard) ([]byte, error) {
	return proto.Marshal(shard)
}

func UnmarshalShard(data []byte) (*pb.WireShard, error) {
	shard := &pb.WireShard{}
	if err := proto.Unmarshal(data, shard); err != nil {
		return nil, err
	}
	return shard, nil
}
