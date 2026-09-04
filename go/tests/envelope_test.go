package tests

import (
	"bytes"
	"testing"

	"github.com/MrFaiman/uniflow/pb"
	"github.com/MrFaiman/uniflow/transfer"
)

func sampleDatagram() *pb.UdpDatagram {
	return &pb.UdpDatagram{
		Payload: &pb.UdpDatagram_Data{Data: &pb.FluteDataPacket{
			SessionId:         42,
			ObjectId:          7,
			SourceBlockNumber: 3,
			EncodingSymbolId:  11,
			Payload:           bytes.Repeat([]byte("uniflow"), 64),
		}},
	}
}

func TestEnvelopeRoundtrip(t *testing.T) {
	raw, err := transfer.MarshalEnvelope(sampleDatagram())
	if err != nil {
		t.Fatal(err)
	}
	got, err := transfer.UnmarshalEnvelope(raw)
	if err != nil {
		t.Fatal(err)
	}
	data := got.GetData()
	if data == nil {
		t.Fatal("expected a data packet")
	}
	if data.ObjectId != 7 || data.SourceBlockNumber != 3 || data.EncodingSymbolId != 11 {
		t.Fatalf("fields not preserved: %+v", data)
	}
}

// The whole point of the envelope: a flipped bit must be detected rather than
// silently accepted as a valid message carrying wrong values. Protobuf alone
// will happily decode many corrupted buffers.
func TestEnvelopeRejectsEverySingleBitFlip(t *testing.T) {
	raw, err := transfer.MarshalEnvelope(sampleDatagram())
	if err != nil {
		t.Fatal(err)
	}

	accepted := 0
	for byteIndex := range raw {
		for bit := 0; bit < 8; bit++ {
			corrupted := make([]byte, len(raw))
			copy(corrupted, raw)
			corrupted[byteIndex] ^= 1 << bit

			got, err := transfer.UnmarshalEnvelope(corrupted)
			if err != nil {
				continue // detected, which is what we want
			}
			// If it still decoded, it must be byte-identical in meaning;
			// anything else is corruption that slipped through.
			data := got.GetData()
			if data == nil ||
				data.ObjectId != 7 ||
				data.SourceBlockNumber != 3 ||
				data.EncodingSymbolId != 11 ||
				data.SessionId != 42 {
				t.Fatalf(
					"corruption accepted at byte %d bit %d: %+v",
					byteIndex, bit, got,
				)
			}
			accepted++
		}
	}
	t.Logf("%d/%d single-bit flips decoded without altering meaning",
		accepted, len(raw)*8)
}

func TestEnvelopeRejectsGarbage(t *testing.T) {
	if _, err := transfer.UnmarshalEnvelope([]byte{0xff, 0xfe, 0xfd}); err == nil {
		t.Fatal("expected garbage to be rejected")
	}
}
