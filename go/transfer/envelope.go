package transfer

import (
	"fmt"
	"hash/crc32"

	"github.com/MrFaiman/uniflow/pb"
	"google.golang.org/protobuf/proto"
)

// MarshalEnvelope serializes a datagram and wraps it with a CRC32 of its
// bytes, producing what actually goes on the wire.
//
// Protobuf has no built-in integrity check. A single flipped bit frequently
// still decodes as a structurally valid message, only with a corrupted field
// value — a wrong object_id or source_block_number — which is far worse than
// an outright lost packet because it silently corrupts receiver state. The
// CRC turns that case back into a plain lost packet, which FEC can repair.
func MarshalEnvelope(datagram *pb.UdpDatagram) ([]byte, error) {
	payload, err := proto.Marshal(datagram)
	if err != nil {
		return nil, fmt.Errorf("marshal datagram: %w", err)
	}
	envelope := &pb.UdpEnvelope{
		Crc32:   crc32.ChecksumIEEE(payload),
		Payload: payload,
	}
	raw, err := proto.Marshal(envelope)
	if err != nil {
		return nil, fmt.Errorf("marshal envelope: %w", err)
	}
	return raw, nil
}

// UnmarshalEnvelope reverses MarshalEnvelope, rejecting anything whose CRC
// does not match. Returns an error for both malformed and corrupted packets;
// callers treat either as a lost symbol.
func UnmarshalEnvelope(raw []byte) (*pb.UdpDatagram, error) {
	var envelope pb.UdpEnvelope
	if err := proto.Unmarshal(raw, &envelope); err != nil {
		return nil, fmt.Errorf("unmarshal envelope: %w", err)
	}
	if crc32.ChecksumIEEE(envelope.Payload) != envelope.Crc32 {
		return nil, fmt.Errorf("crc mismatch: packet corrupted in transit")
	}
	var datagram pb.UdpDatagram
	if err := proto.Unmarshal(envelope.Payload, &datagram); err != nil {
		return nil, fmt.Errorf("unmarshal datagram: %w", err)
	}
	return &datagram, nil
}
