package transfer

import (
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"io"
)

const sha256Size = sha256.Size

func FileChecksum(data []byte) []byte {
	sum := sha256.Sum256(data)
	return sum[:]
}

// StreamChecksum hashes a file without holding it in memory, then rewinds so
// the caller can go on to read block ranges from the same handle.
func StreamChecksum(file io.ReadSeeker) ([]byte, error) {
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return nil, fmt.Errorf("seek start: %w", err)
	}
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return nil, fmt.Errorf("hash file: %w", err)
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return nil, fmt.Errorf("rewind: %w", err)
	}
	return digest.Sum(nil), nil
}

func checksumMatches(data, expected []byte) bool {
	got := FileChecksum(data)
	if len(expected) != sha256Size {
		return false
	}
	return hmac.Equal(got, expected)
}
