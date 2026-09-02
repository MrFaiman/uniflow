package transfer

import (
	"crypto/hmac"
	"crypto/sha256"
)

const sha256Size = sha256.Size

func FileChecksum(data []byte) []byte {
	sum := sha256.Sum256(data)
	return sum[:]
}

func checksumMatches(data, expected []byte) bool {
	got := FileChecksum(data)
	if len(expected) != sha256Size {
		return false
	}
	return hmac.Equal(got, expected)
}
