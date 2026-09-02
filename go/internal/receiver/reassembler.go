package receiver

import (
	"sync"
	"time"

	"github.com/MrFaiman/uniflow/pb"
)

type frameKey struct {
	workerIndex uint32
	frameID     uint64
}

type frameState struct {
	shards    map[uint32]*pb.WireShard
	dataNeed  int
	createdAt time.Time
}

type Reassembler struct {
	mu         sync.Mutex
	frames     map[frameKey]*frameState
	maxInflight int
	ttl        time.Duration
}

func NewReassembler(maxInflight int, ttl time.Duration) *Reassembler {
	return &Reassembler{
		frames:      make(map[frameKey]*frameState),
		maxInflight: maxInflight,
		ttl:         ttl,
	}
}

func (r *Reassembler) AddAndReconstruct(shard *pb.WireShard, reconstruct func([]*pb.WireShard) ([]byte, error)) ([]byte, bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.evictExpiredLocked(time.Now())

	key := frameKey{
		workerIndex: shard.WorkerIndex,
		frameID:     shard.FrameId,
	}

	state, ok := r.frames[key]
	if !ok {
		if len(r.frames) >= r.maxInflight {
			r.evictOldestLocked()
		}
		state = &frameState{
			shards:    make(map[uint32]*pb.WireShard),
			dataNeed:  int(shard.DataShards),
			createdAt: time.Now(),
		}
		r.frames[key] = state
	}

	if _, exists := state.shards[shard.ShardIndex]; exists {
		return nil, false, nil
	}
	state.shards[shard.ShardIndex] = shard

	if len(state.shards) < state.dataNeed {
		return nil, false, nil
	}

	selected := make([]*pb.WireShard, 0, len(state.shards))
	for _, s := range state.shards {
		selected = append(selected, s)
	}
	delete(r.frames, key)

	payload, err := reconstruct(selected)
	if err != nil {
		return nil, false, err
	}
	return payload, true, nil
}

func (r *Reassembler) Inflight() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.frames)
}

func (r *Reassembler) evictExpiredLocked(now time.Time) {
	for key, state := range r.frames {
		if now.Sub(state.createdAt) > r.ttl {
			delete(r.frames, key)
		}
	}
}

func (r *Reassembler) evictOldestLocked() {
	var oldestKey frameKey
	var oldestTime time.Time
	first := true
	for key, state := range r.frames {
		if first || state.createdAt.Before(oldestTime) {
			oldestKey = key
			oldestTime = state.createdAt
			first = false
		}
	}
	if !first {
		delete(r.frames, oldestKey)
	}
}

func (r *Reassembler) Reset() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.frames = make(map[frameKey]*frameState)
}