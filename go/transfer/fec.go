package transfer

import (
	"fmt"

	"github.com/xssnick/raptorq"
)

const (
	SymbolSize         = 1024
	MaxSymbolsPerBlock = 1024

	// repairPercent is the extra RaptorQ symbols sent per block, as a
	// percentage of that block's source symbols.
	//
	// There is no ACK, so a block that arrives short is never retried: it
	// simply never decodes and the transfer stalls forever. The margin must
	// therefore exceed the worst-case loss a block can suffer. Under the
	// specified router conditions those losses stack — ~3% dropped, ~3%
	// corrupted (a flipped datagram fails to parse and is discarded), and
	// ~3% misrouted to a Receiver that holds too few of this block's symbols
	// to use them — for roughly 9%, and real loss arrives in bursts rather
	// than evenly spread. The previous 5% could not absorb even the residual
	// jitter of a fault-free run, which made large transfers intermittent.
	repairPercent = 30
)

type BlockPlan struct {
	Index    uint32
	Data     []byte
	SymbolsK uint32
}

type FilePlan struct {
	Blocks         []BlockPlan
	TotalSymbols   uint32
	SourceBlocks   uint32
	SymbolSize     uint32
	OriginalLength int
}

// MaxBlockBytes is how many file bytes one source block covers. It bounds a
// streaming Sender's working set: only one block need be resident at a time.
const MaxBlockBytes = MaxSymbolsPerBlock * SymbolSize

// PlanFileBySize derives the same layout as PlanFile from the file's length
// alone, without holding its contents. It carries no per-block Data, so a
// Sender can read each block on demand instead of loading a whole file (a
// 1 GB transfer would otherwise cost ~1 GB in every one of the three Sender
// processes at once).
func PlanFileBySize(originalLength int) FilePlan {
	totalSymbols := uint32((originalLength + SymbolSize - 1) / SymbolSize)
	if totalSymbols == 0 {
		totalSymbols = 1
	}
	sourceBlocks := (totalSymbols + MaxSymbolsPerBlock - 1) / MaxSymbolsPerBlock
	return FilePlan{
		TotalSymbols:   totalSymbols,
		SourceBlocks:   sourceBlocks,
		SymbolSize:     SymbolSize,
		OriginalLength: originalLength,
	}
}

func PlanFile(data []byte) FilePlan {
	originalLength := len(data)
	totalSymbols := uint32((originalLength + SymbolSize - 1) / SymbolSize)
	if totalSymbols == 0 {
		totalSymbols = 1
	}

	sourceBlocks := (totalSymbols + MaxSymbolsPerBlock - 1) / MaxSymbolsPerBlock
	maxBlockBytes := MaxSymbolsPerBlock * SymbolSize

	blocks := make([]BlockPlan, 0, sourceBlocks)
	for i := uint32(0); i < sourceBlocks; i++ {
		start := int(i) * maxBlockBytes
		end := start + maxBlockBytes
		if start >= originalLength {
			blocks = append(blocks, BlockPlan{
				Index:    i,
				Data:     []byte{},
				SymbolsK: 1,
			})
			continue
		}
		if end > originalLength {
			end = originalLength
		}
		chunk := data[start:end]
		k := uint32((len(chunk) + SymbolSize - 1) / SymbolSize)
		if k == 0 {
			k = 1
		}
		blocks = append(blocks, BlockPlan{
			Index:    i,
			Data:     chunk,
			SymbolsK: k,
		})
	}

	return FilePlan{
		Blocks:         blocks,
		TotalSymbols:   totalSymbols,
		SourceBlocks:   sourceBlocks,
		SymbolSize:     SymbolSize,
		OriginalLength: originalLength,
	}
}

func BlockByteLength(plan FilePlan, blockIndex uint32) int {
	if blockIndex >= plan.SourceBlocks {
		return 0
	}
	maxBlockBytes := MaxSymbolsPerBlock * SymbolSize
	start := int(blockIndex) * maxBlockBytes
	if start >= plan.OriginalLength {
		return 0
	}
	end := start + maxBlockBytes
	if end > plan.OriginalLength {
		end = plan.OriginalLength
	}
	return end - start
}

func EncodeBlock(block BlockPlan) (*raptorq.Encoder, uint32, error) {
	rq := raptorq.NewRaptorQ(SymbolSize)
	enc, err := rq.CreateEncoder(block.Data)
	if err != nil {
		return nil, 0, fmt.Errorf("create encoder block %d: %w", block.Index, err)
	}
	return enc, enc.BaseSymbolsNum(), nil
}

func DecodeBlock(blockLen int, symbols map[uint32][]byte) ([]byte, error) {
	rq := raptorq.NewRaptorQ(SymbolSize)
	dec, err := rq.CreateDecoder(uint32(blockLen))
	if err != nil {
		return nil, fmt.Errorf("create decoder: %w", err)
	}

	for esi, payload := range symbols {
		canTry, err := dec.AddSymbol(esi, payload)
		if err != nil {
			return nil, fmt.Errorf("add symbol %d: %w", esi, err)
		}
		if canTry {
			ok, result, err := dec.Decode()
			if err != nil {
				return nil, fmt.Errorf("decode: %w", err)
			}
			if ok {
				return result, nil
			}
		}
	}
	return nil, fmt.Errorf("insufficient symbols for block len %d", blockLen)
}

// RepairSymbolCount returns how many encoding symbols to transmit for a block
// with the given number of source symbols, rounding the repair margin up so
// even a single-symbol block gets at least one repair symbol.
func RepairSymbolCount(base uint32) uint32 {
	return base + (base*repairPercent+99)/100
}

func OwnsBlock(blockIndex, workerIndex, workerCount uint32) bool {
	if workerCount == 0 {
		return true
	}
	return blockIndex%workerCount == workerIndex
}
